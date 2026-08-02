"""InsureDesk — Agent Heartbeat (background thread).

Every 30s POST /api/v1/agent-providers/{instance_id}/heartbeat.

State machine:
    running → heartbeat fail → retry (3x) → offline (keeps trying)

CRITICAL: heartbeat failure must NEVER crash InsureDesk — the agent keeps
running locally; only its online status degrades.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class AgentHeartbeat:
    """Background thread that keeps the UIP-AI registration alive."""

    def __init__(
        self,
        heartbeat_fn: Callable[[], object],
        interval_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._heartbeat_fn = heartbeat_fn
        self._interval = interval_seconds
        self._max_retries = max_retries
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.state = "running"
        self.last_success_at: Optional[float] = None
        self.last_error: str = ""
        self._consecutive_failures = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="agent-heartbeat", daemon=True
        )
        self._thread.start()
        logger.info("agent_heartbeat.started (every %ss)", self._interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("agent_heartbeat.stopped")

    def _run(self) -> None:
        while not self._stop.is_set():
            self._tick()
            self._stop.wait(self._interval)

    def _tick(self) -> None:
        try:
            self._heartbeat_fn()
            self._consecutive_failures = 0
            self.state = "online"
            self.last_success_at = time.time()
            self.last_error = ""
        except Exception as e:  # noqa: BLE001 — never crash the thread
            self._consecutive_failures += 1
            self.last_error = str(e)
            if self._consecutive_failures >= self._max_retries:
                self.state = "offline"
            logger.warning(
                "agent_heartbeat.failed (%d/%d): %s",
                self._consecutive_failures, self._max_retries, e,
            )
