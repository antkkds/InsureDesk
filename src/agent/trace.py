"""InsureDesk — Execution Trace (Phase 4.6).

ChatGPT: "真实 E2E 不要只看 pass/fail，增加 Execution Trace — 客户环境失败时
这个 trace 会非常重要。"

Timeline (example):
    exec_xxx
    10:01:02 created
    10:01:03 dispatched
    10:01:08 agent received
    10:01:15 browser attached
    10:01:30 portal loaded
    10:02:10 quote calculated
    10:02:12 result returned

Append-only JSONL per execution. Never blocks the command loop.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _now_ms() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]


class ExecutionTracer:
    """Append-only trace writer (thread-safe, never raises)."""

    def __init__(self, trace_dir: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        if trace_dir is None:
            trace_dir = os.environ.get(
                "INSURE_DESK_TRACE_DIR",
                str(Path.home() / ".insuredesk" / "traces"),
            )
        self.trace_dir = Path(trace_dir)
        try:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001 — tracing must never crash
            logger.warning("execution_trace.dir_unavailable: %s — %s", trace_dir, e)

    def log(self, execution_id: str, stage: str, detail: Any = None) -> None:
        """Append one timeline event for an execution (best-effort)."""
        record = {
            "execution_id": execution_id,
            "stage": stage,
            "time": _now_ms(),
            "detail": detail,
        }
        try:
            with self._lock:
                path = self.trace_dir / f"{execution_id}.jsonl"
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001 — tracing must never crash
            logger.warning("execution_trace.write_failed: %s", e)

    def read(self, execution_id: str) -> list[Dict[str, Any]]:
        """Read the full timeline for an execution (for reports/debug)."""
        path = self.trace_dir / f"{execution_id}.jsonl"
        if not path.exists():
            return []
        try:
            with self._lock:
                return [
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
        except Exception as e:  # noqa: BLE001
            logger.warning("execution_trace.read_failed: %s", e)
            return []

    def format_timeline(self, execution_id: str) -> str:
        """Human-readable timeline (Telegram-friendly)."""
        lines = [f"Execution: {execution_id}"]
        for ev in self.read(execution_id):
            lines.append(f"  {ev.get('time', '?')}  {ev.get('stage', '?')}")
        return "\n".join(lines)


# ── Global default tracer ─────────────────────────────────────────────────────

execution_tracer = ExecutionTracer()
