"""Portal Execution Engine — Checkpoint Store & Manager.

Checkpoints capture execution state at step boundaries so that
a failed execution can resume from the last checkpoint rather
than restarting from scratch.

The CheckpointStore is a pluggable backend. Two implementations:
- MemoryCheckpointStore: In-memory (for testing/single-run)
- SqliteCheckpointStore: Persistent (for production)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.portal.execution.models import Checkpoint, ExecutionContext, ExecutionPlan
from src.portal.execution.exceptions import CheckpointNotFoundError
from src.portal.execution.models import StepStatus

logger = logging.getLogger("insuredesk.execution.checkpoint")


class CheckpointStore(ABC):
    """Abstract base for checkpoint persistence."""

    @abstractmethod
    def save(self, checkpoint: Checkpoint) -> None: ...

    @abstractmethod
    def load(self, checkpoint_id: str) -> Checkpoint: ...

    @abstractmethod
    def load_latest(self, plan_id: str) -> Optional[Checkpoint]: ...

    @abstractmethod
    def list_for_plan(self, plan_id: str) -> List[Checkpoint]: ...

    @abstractmethod
    def delete(self, checkpoint_id: str) -> None: ...

    @abstractmethod
    def delete_for_plan(self, plan_id: str) -> None: ...


class MemoryCheckpointStore(CheckpointStore):
    """In-memory checkpoint storage (for testing)."""

    def __init__(self) -> None:
        self._checkpoints: Dict[str, Checkpoint] = {}
        self._lock = threading.Lock()

    def save(self, checkpoint: Checkpoint) -> None:
        with self._lock:
            self._checkpoints[checkpoint.id] = checkpoint

    def load(self, checkpoint_id: str) -> Checkpoint:
        with self._lock:
            ckpt = self._checkpoints.get(checkpoint_id)
            if ckpt is None:
                raise CheckpointNotFoundError(
                    f"Checkpoint '{checkpoint_id}' not found"
                )
            return ckpt

    def load_latest(self, plan_id: str) -> Optional[Checkpoint]:
        with self._lock:
            plan_ckpts = [
                c for c in self._checkpoints.values() if c.plan_id == plan_id
            ]
            if not plan_ckpts:
                return None
            return max(plan_ckpts, key=lambda c: c.created_at)

    def list_for_plan(self, plan_id: str) -> List[Checkpoint]:
        with self._lock:
            return sorted(
                [c for c in self._checkpoints.values() if c.plan_id == plan_id],
                key=lambda c: c.created_at,
            )

    def delete(self, checkpoint_id: str) -> None:
        with self._lock:
            self._checkpoints.pop(checkpoint_id, None)

    def delete_for_plan(self, plan_id: str) -> None:
        with self._lock:
            self._checkpoints = {
                k: v for k, v in self._checkpoints.items() if v.plan_id != plan_id
            }


class SqliteCheckpointStore(CheckpointStore):
    """Persistent checkpoint storage using SQLite."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    context TEXT NOT NULL,
                    variables TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ckpt_plan
                ON checkpoints(plan_id)
            """)
            conn.commit()

    def save(self, checkpoint: Checkpoint) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO checkpoints
                   (id, plan_id, step_index, context, variables, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    checkpoint.id,
                    checkpoint.plan_id,
                    checkpoint.step_index,
                    json.dumps(checkpoint.context),
                    json.dumps(checkpoint.variables),
                    checkpoint.created_at.isoformat(),
                    json.dumps(checkpoint.metadata),
                ),
            )
            conn.commit()

    def load(self, checkpoint_id: str) -> Checkpoint:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,)
            ).fetchone()
            if row is None:
                raise CheckpointNotFoundError(
                    f"Checkpoint '{checkpoint_id}' not found"
                )
            return self._row_to_checkpoint(row)

    def load_latest(self, plan_id: str) -> Optional[Checkpoint]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE plan_id = ? ORDER BY created_at DESC LIMIT 1",
                (plan_id,),
            ).fetchone()
            return self._row_to_checkpoint(row) if row else None

    def list_for_plan(self, plan_id: str) -> List[Checkpoint]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM checkpoints WHERE plan_id = ? ORDER BY created_at",
                (plan_id,),
            ).fetchall()
            return [self._row_to_checkpoint(r) for r in rows]

    def delete(self, checkpoint_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM checkpoints WHERE id = ?", (checkpoint_id,)
            )
            conn.commit()

    def delete_for_plan(self, plan_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM checkpoints WHERE plan_id = ?", (plan_id,)
            )
            conn.commit()

    @staticmethod
    def _row_to_checkpoint(row: sqlite3.Row) -> Checkpoint:
        return Checkpoint(
            id=row[0],
            plan_id=row[1],
            step_index=row[2],
            context=json.loads(row[3]),
            variables=json.loads(row[4]),
            created_at=datetime.fromisoformat(row[5]),
            metadata=json.loads(row[6]),
        )


class CheckpointManager:
    """High-level checkpoint operations used by ExecutionEngine."""

    def __init__(self, store: CheckpointStore):
        self._store = store

    def save_checkpoint(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
    ) -> Checkpoint:
        """Create and save a checkpoint from current execution state."""
        checkpoint = Checkpoint(
            plan_id=plan.id,
            step_index=plan.current_step_index,
            context={
                "portal": plan.portal,
                "current_step_id": context.current_step_id,
                "session_id": context.session_id,
            },
            variables=dict(context.variables),
            metadata={
                "plan_name": plan.name,
                "completed_steps": [
                    s.name for s in plan.steps
                    if s.status.value in ("success", "skipped")
                ],
            },
        )
        self._store.save(checkpoint)
        logger.info("Checkpoint saved: %s (step %d)", checkpoint.id, checkpoint.step_index)
        return checkpoint

    def load_latest(self, plan_id: str) -> Optional[Checkpoint]:
        """Load the most recent checkpoint for a plan."""
        return self._store.load_latest(plan_id)

    def restore_context(
        self, checkpoint: Checkpoint, plan: ExecutionPlan
    ) -> ExecutionContext:
        """Restore an ExecutionContext from a checkpoint."""
        context = ExecutionContext(
            plan_id=checkpoint.plan_id,
            portal=checkpoint.context.get("portal", ""),
            session_id=checkpoint.context.get("session_id", ""),
            current_step_id=checkpoint.context.get("current_step_id"),
            variables=dict(checkpoint.variables),
        )
        plan.current_step_index = checkpoint.step_index
        # Mark completed steps as SUCCESS
        for step in plan.steps[:checkpoint.step_index]:
            if step.status == StepStatus.PENDING:
                step.status = StepStatus.SUCCESS
        return context

    def clear_for_plan(self, plan_id: str) -> None:
        """Remove all checkpoints for a plan."""
        self._store.delete_for_plan(plan_id)
