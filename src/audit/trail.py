"""InsureDesk — Audit: Execution Audit Trail.

Tracks every workflow step with timestamps, actors, and results.
Supports search, filtering, and export for compliance.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.audit.models import (
    AuditCategory,
    AuditEntry,
    AuditLevel,
    AuditQuery,
    ApprovalDecision,
)
from src.audit.protector import SensitiveDataProtector, default_protector

logger = logging.getLogger("insuredesk.audit.trail")


class AuditStore:
    """Persistent audit log storage.

    Stores audit entries in a JSON file. In production, this would
    be replaced with a database-backed store.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self._path = storage_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "audit.json"
        )
        self._entries: List[AuditEntry] = []
        self._approvals: List[ApprovalDecision] = []
        os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
        self._load()

    def append(self, entry: AuditEntry) -> None:
        self._entries.append(entry)
        self._save()

    def append_approval(self, decision: ApprovalDecision) -> None:
        self._approvals.append(decision)
        self._save()

    def query(self, q: AuditQuery) -> List[AuditEntry]:
        results = self._entries[:]
        if q.level:
            results = [e for e in results if e.level == q.level]
        if q.category:
            results = [e for e in results if e.category == q.category]
        if q.action:
            results = [e for e in results if q.action in e.action]
        if q.actor:
            results = [e for e in results if e.actor == q.actor]
        if q.portal_id:
            results = [e for e in results if e.portal_id == q.portal_id]
        if q.workflow_id:
            results = [e for e in results if e.workflow_id == q.workflow_id]
        if q.execution_id:
            results = [e for e in results if e.execution_id == q.execution_id]
        if q.has_error is not None:
            results = [
                e for e in results
                if (e.error is not None) == q.has_error
            ]
        if q.start_time:
            results = [
                e for e in results if e.timestamp >= q.start_time
            ]
        if q.end_time:
            results = [
                e for e in results if e.timestamp <= q.end_time
            ]
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[q.offset:q.offset + q.limit]

    def query_approvals(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[ApprovalDecision]:
        results = self._approvals[:]
        if workflow_id:
            results = [a for a in results if a.workflow_id == workflow_id]
        results.sort(key=lambda a: a.requested_at, reverse=True)
        return results[:limit]

    def recent(self, limit: int = 20) -> List[AuditEntry]:
        return sorted(
            self._entries, key=lambda e: e.timestamp, reverse=True
        )[:limit]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self._approvals.clear()
        self._save()

    def _load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    data = json.load(f)
                self._entries = [
                    AuditEntry(**e) if isinstance(e, dict) else e
                    for e in data.get("entries", [])
                ]
                self._approvals = [
                    ApprovalDecision(**a) if isinstance(a, dict) else a
                    for a in data.get("approvals", [])
                ]
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load audit log: {e}")

    def _save(self) -> None:
        try:
            with open(self._path, "w") as f:
                json.dump(
                    {
                        "entries": [
                            e.__dict__ if hasattr(e, "__dict__") else e
                            for e in self._entries
                        ],
                        "approvals": [
                            a.__dict__ if hasattr(a, "__dict__") else a
                            for a in self._approvals
                        ],
                    },
                    f,
                    indent=2,
                    default=str,
                )
        except OSError as e:
            logger.error(f"Failed to save audit log: {e}")


class ExecutionAudit:
    """High-level audit trail for workflow executions.

    Wraps AuditStore with workflow-specific logging methods.
    """

    def __init__(
        self,
        store: Optional[AuditStore] = None,
        protector: Optional[SensitiveDataProtector] = None,
    ):
        self._store = store or AuditStore()
        self._protector = protector or default_protector

    def log_workflow_start(
        self,
        workflow_id: str,
        portal_id: str,
        actor: str = "system",
    ) -> AuditEntry:
        entry = AuditEntry(
            level=AuditLevel.INFO,
            category=AuditCategory.WORKFLOW,
            action="workflow_started",
            actor=actor,
            portal_id=portal_id,
            workflow_id=workflow_id,
            message=f"Workflow started: {workflow_id} for {portal_id}",
            details={"started_at": datetime.now().isoformat()},
        )
        self._store.append(entry)
        return entry

    def log_step(
        self,
        workflow_id: str,
        portal_id: str,
        step_name: str,
        status: str,
        actor: str = "system",
        duration_ms: float = 0.0,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> AuditEntry:
        level = AuditLevel.ERROR if error else AuditLevel.INFO
        entry = AuditEntry(
            level=level,
            category=AuditCategory.EXECUTION,
            action=f"step_{step_name}",
            actor=actor,
            portal_id=portal_id,
            workflow_id=workflow_id,
            message=f"Step '{step_name}': {status}",
            details={
                "step": step_name,
                "status": status,
                **(details or {}),
            },
            sensitive=False,
            duration_ms=duration_ms,
            error=error,
        )
        self._store.append(entry)
        return entry

    def log_workflow_complete(
        self,
        workflow_id: str,
        portal_id: str,
        status: str,
        total_duration_ms: float = 0.0,
        premium: float = 0.0,
    ) -> AuditEntry:
        entry = AuditEntry(
            level=AuditLevel.INFO,
            category=AuditCategory.WORKFLOW,
            action="workflow_completed",
            actor="system",
            portal_id=portal_id,
            workflow_id=workflow_id,
            message=f"Workflow completed: {status} (premium: RM {premium:,.2f})",
            details={
                "status": status,
                "total_duration_ms": total_duration_ms,
                "premium": premium,
            },
        )
        self._store.append(entry)
        return entry

    def log_workflow_failed(
        self,
        workflow_id: str,
        portal_id: str,
        error: str,
        step: str = "",
    ) -> AuditEntry:
        entry = AuditEntry(
            level=AuditLevel.ERROR,
            category=AuditCategory.WORKFLOW,
            action="workflow_failed",
            actor="system",
            portal_id=portal_id,
            workflow_id=workflow_id,
            message=f"Workflow failed at '{step}': {error}",
            details={"failed_step": step},
            error=error,
        )
        self._store.append(entry)
        return entry

    def log_validation(
        self,
        workflow_id: str,
        portal_id: str,
        passed: bool,
        errors: List[str],
    ) -> AuditEntry:
        entry = AuditEntry(
            level=AuditLevel.INFO if passed else AuditLevel.WARNING,
            category=AuditCategory.VALIDATION,
            action="validation_completed",
            actor="system",
            portal_id=portal_id,
            workflow_id=workflow_id,
            message=f"Validation: {'PASSED' if passed else 'FAILED'} ({len(errors)} errors)",
            details={
                "passed": passed,
                "error_count": len(errors),
            },
            error="; ".join(errors) if errors else None,
        )
        self._store.append(entry)
        return entry

    def log_review(
        self,
        workflow_id: str,
        portal_id: str,
        summary: str,
    ) -> AuditEntry:
        entry = AuditEntry(
            level=AuditLevel.INFO,
            category=AuditCategory.REVIEW,
            action="review_completed",
            actor="system",
            portal_id=portal_id,
            workflow_id=workflow_id,
            message=f"Review completed: {summary[:100]}" if summary else "Review completed",
            details={"summary": summary},
        )
        self._store.append(entry)
        return entry

    def log_approval(
        self,
        workflow_id: str,
        portal_id: str,
        decision: ApprovalDecision,
    ) -> AuditEntry:
        entry = AuditEntry(
            level=AuditLevel.INFO,
            category=AuditCategory.APPROVAL,
            action=f"approval_{decision.decision}",
            actor=decision.approved_by or decision.requested_by,
            portal_id=portal_id,
            workflow_id=workflow_id,
            message=f"Approval '{decision.action}': {decision.decision}",
            details={
                "action": decision.action,
                "decision": decision.decision,
                "reason": decision.reason,
                "approved_by": decision.approved_by,
            },
        )
        self._store.append(entry)
        return entry

    def query(self, q: AuditQuery) -> List[AuditEntry]:
        return self._store.query(q)

    def recent(self, limit: int = 20) -> List[AuditEntry]:
        return self._store.recent(limit)


# Default global audit trail
default_audit = ExecutionAudit()
