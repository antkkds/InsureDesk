"""InsureDesk — Assistant Session Runtime.

Manages multi-step insurance assistant sessions.
Insurance workflows are NOT single API calls — they span multiple
interactions (request info → calculate → review → approve → submit).

Each session tracks:
- Identity: session_id, customer_id, task type
- State: where in the workflow the session is
- Memory: collected data, pending actions, context
- Lifecycle: start → pause → resume → complete/cancel

Usage:
    from src.runtime.session_runtime import SessionRuntime, SessionState

    runtime = SessionRuntime()
    session = runtime.create_session(customer_id="C001", task="fire_quote")
    # ... some processing ...
    runtime.pause_session(session.id, reason="Need building info")
    # ... user provides info ...
    runtime.resume_session(session.id, context={"occupation": "factory"})
    result = runtime.complete_session(session.id)
"""

from __future__ import annotations

import uuid
import json
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, Any, List


# ══════════════════════════════════════════════════════════════════
# Session State
# ══════════════════════════════════════════════════════════════════


class SessionState(Enum):
    """Lifecycle states for an assistant session."""
    IDLE = "idle"                       # Created, no action yet
    PROCESSING = "processing"           # Tool/action in progress
    WAITING_FOR_INPUT = "waiting"       # Paused, waiting for user info
    COMPLETED = "completed"             # Successfully finished
    CANCELLED = "cancelled"             # Cancelled by user
    ERROR = "error"                     # Failed


# ══════════════════════════════════════════════════════════════════
# Session Data Model
# ══════════════════════════════════════════════════════════════════


@dataclass
class SessionData:
    """Full session state and context."""
    # Identity
    id: str = ""
    customer_id: str = ""
    task: str = ""                      # e.g. "fire_quote", "claim_inquiry"

    # State
    state: SessionState = SessionState.IDLE
    previous_state: Optional[SessionState] = None

    # Timeline
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None

    # Context memory (key-value store for collected data)
    collected_data: Dict[str, Any] = field(default_factory=dict)

    # Pending actions (what needs to happen next)
    pending_actions: List[Dict[str, Any]] = field(default_factory=list)

    # Completed actions log
    action_log: List[Dict[str, Any]] = field(default_factory=list)

    # Waiting reason (why session is paused)
    waiting_reason: str = ""

    # Error tracking
    error_message: str = ""
    retry_count: int = 0

    # Tool call history
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["state"] = self.state.value
        result["previous_state"] = self.previous_state.value if self.previous_state else None
        return result

    def set_state(self, new_state: SessionState) -> None:
        self.previous_state = self.state
        self.state = new_state
        self.updated_at = datetime.utcnow().isoformat()


# ══════════════════════════════════════════════════════════════════
# Session Runtime
# ══════════════════════════════════════════════════════════════════


class SessionRuntime:
    """Manages assistant session lifecycle.

    Sessions are identified by UUID and tracked in memory.
    Each session holds its own state, memory, and action log.

    Usage:
        runtime = SessionRuntime()
        s = runtime.create_session(customer_id="C001", task="fire_quote")
        runtime.set_data(s.id, "proposer_name", "Tiong Hoe Hung")
        runtime.pause(s.id, reason="Need occupation")
        runtime.resume(s.id, data={"occupation": "factory"})
        runtime.log_action(s.id, "calculate_quote", {"result": "RM 3,200"})
        result = runtime.complete(s.id)
    """

    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}

    # ── CRUD ───────────────────────────────────────────────────

    def create_session(self,
                       customer_id: str = "",
                       task: str = "",
                       initial_data: Optional[Dict[str, Any]] = None,
                       ) -> SessionData:
        """Create a new assistant session.

        Args:
            customer_id: Customer identifier.
            task: Task description (e.g. "fire_quote", "claim_inquiry").
            initial_data: Optional initial context data.

        Returns:
            The new SessionData.
        """
        now = datetime.utcnow().isoformat()
        session = SessionData(
            id=_new_id(),
            customer_id=customer_id,
            task=task,
            state=SessionState.IDLE,
            created_at=now,
            updated_at=now,
            collected_data=initial_data or {},
        )
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Optional[SessionData]:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def list_sessions(self,
                      state_filter: Optional[SessionState] = None,
                      customer_id: Optional[str] = None,
                      limit: int = 50,
                      ) -> List[SessionData]:
        """List sessions, optionally filtered.

        Args:
            state_filter: Only return sessions in this state.
            customer_id: Only return sessions for this customer.
            limit: Max sessions to return.

        Returns:
            List of SessionData, newest first.
        """
        sessions = list(self._sessions.values())

        if state_filter:
            sessions = [s for s in sessions if s.state == state_filter]
        if customer_id:
            sessions = [s for s in sessions if s.customer_id == customer_id]

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions[:limit]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns True if found."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def count(self) -> int:
        """Number of active sessions."""
        return len(self._sessions)

    # ── State Transitions ─────────────────────────────────────

    def start(self, session_id: str) -> SessionData:
        """Move session from IDLE to PROCESSING."""
        session = self._require_session(session_id)
        if session.state != SessionState.IDLE:
            raise ValueError(
                f"Cannot start session '{session_id}': "
                f"current state is {session.state.value} (expected: idle)"
            )
        session.set_state(SessionState.PROCESSING)
        return session

    def pause(self, session_id: str, reason: str = "") -> SessionData:
        """Pause a session to wait for user input.

        Args:
            session_id: Session to pause.
            reason: Why the session is waiting (e.g. "Need occupation").

        Returns:
            Updated SessionData.
        """
        session = self._require_session(session_id)
        if session.state not in (SessionState.PROCESSING, SessionState.IDLE):
            raise ValueError(
                f"Cannot pause session '{session_id}': "
                f"current state is {session.state.value}"
            )
        session.waiting_reason = reason
        session.set_state(SessionState.WAITING_FOR_INPUT)
        return session

    def resume(self, session_id: str,
               data: Optional[Dict[str, Any]] = None) -> SessionData:
        """Resume a paused session with new data.

        Args:
            session_id: Session to resume.
            data: New data to merge into collected_data.

        Returns:
            Updated SessionData.
        """
        session = self._require_session(session_id)
        if session.state != SessionState.WAITING_FOR_INPUT:
            raise ValueError(
                f"Cannot resume session '{session_id}': "
                f"current state is {session.state.value} (expected: waiting)"
            )

        # Merge new data
        if data:
            session.collected_data.update(data)

        session.waiting_reason = ""
        session.set_state(SessionState.PROCESSING)
        return session

    def complete(self, session_id: str) -> SessionData:
        """Mark a session as completed."""
        session = self._require_session(session_id)
        session.completed_at = datetime.utcnow().isoformat()
        session.set_state(SessionState.COMPLETED)
        return session

    def cancel(self, session_id: str, reason: str = "") -> SessionData:
        """Cancel a session."""
        session = self._require_session(session_id)
        session.error_message = reason
        session.set_state(SessionState.CANCELLED)
        return session

    def mark_error(self, session_id: str, error: str) -> SessionData:
        """Mark a session as errored."""
        session = self._require_session(session_id)
        session.error_message = error
        session.retry_count += 1
        session.set_state(SessionState.ERROR)
        return session

    # ── Data Management ───────────────────────────────────────

    def set_data(self, session_id: str, key: str, value: Any) -> SessionData:
        """Store a value in the session's collected_data."""
        session = self._require_session(session_id)
        session.collected_data[key] = value
        session.updated_at = datetime.utcnow().isoformat()
        return session

    def get_data(self, session_id: str, key: str, default: Any = None) -> Any:
        """Retrieve a value from the session's collected_data."""
        session = self._require_session(session_id)
        return session.collected_data.get(key, default)

    def get_all_data(self, session_id: str) -> Dict[str, Any]:
        """Get all collected data for a session."""
        session = self._require_session(session_id)
        return dict(session.collected_data)

    # ── Action Logging ────────────────────────────────────────

    def log_action(self, session_id: str,
                   action: str,
                   details: Optional[Dict[str, Any]] = None) -> SessionData:
        """Log an action taken during the session."""
        session = self._require_session(session_id)
        entry = {
            "action": action,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        session.action_log.append(entry)
        session.updated_at = datetime.utcnow().isoformat()
        return session

    def log_tool_call(self, session_id: str,
                      tool_name: str,
                      parameters: Dict[str, Any],
                      result: Any = None,
                      duration_ms: float = 0.0,
                      error: Optional[str] = None) -> SessionData:
        """Log a tool call made during the session."""
        session = self._require_session(session_id)
        entry = {
            "tool": tool_name,
            "parameters": parameters,
            "result": result,
            "duration_ms": round(duration_ms, 2),
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
        }
        session.tool_calls.append(entry)
        session.updated_at = datetime.utcnow().isoformat()
        return session

    def add_pending_action(self, session_id: str,
                           action: str,
                           params: Optional[Dict[str, Any]] = None) -> SessionData:
        """Add a pending action that needs to happen next."""
        session = self._require_session(session_id)
        session.pending_actions.append({
            "action": action,
            "params": params or {},
            "added_at": datetime.utcnow().isoformat(),
        })
        return session

    def clear_pending_actions(self, session_id: str) -> SessionData:
        """Clear all pending actions."""
        session = self._require_session(session_id)
        session.pending_actions.clear()
        return session

    # ── Helpers ───────────────────────────────────────────────

    def _require_session(self, session_id: str) -> SessionData:
        """Get session or raise KeyError."""
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Session '{session_id}' not found")
        return session


def _new_id() -> str:
    """Generate a short, human-readable session ID."""
    short_uuid = uuid.uuid4().hex[:12]
    date_part = datetime.utcnow().strftime("%y%m%d")
    return f"S{date_part}-{short_uuid}"


# ══════════════════════════════════════════════════════════════════
# Session Context Builder
# ══════════════════════════════════════════════════════════════════

class SessionContextBuilder:
    """Build context for LLM prompts from session data.

    Generates a structured context string that tells the LLM
    what has happened so far and what needs to happen next.
    """

    @staticmethod
    def build_context(session: SessionData) -> str:
        """Build a prompt context string from session data.

        Args:
            session: The SessionData to build context from.

        Returns:
            A structured string for LLM injection.
        """
        lines = [
            f"## Session Context",
            f"Session ID: {session.id}",
            f"Task: {session.task}",
            f"Customer: {session.customer_id}",
            f"State: {session.state.value}",
            "",
        ]

        if session.collected_data:
            lines.append("### Collected Data")
            for key, value in session.collected_data.items():
                lines.append(f"- {key}: {value}")
            lines.append("")

        if session.pending_actions:
            lines.append("### Pending Actions")
            for pa in session.pending_actions:
                lines.append(f"- {pa['action']}: {json.dumps(pa['params'])}")
            lines.append("")

        if session.action_log:
            lines.append("### Action Log (last 5)")
            for entry in session.action_log[-5:]:
                lines.append(f"- {entry['timestamp'][:19]}: {entry['action']}")
            lines.append("")

        if session.waiting_reason:
            lines.append(f"### Waiting For")
            lines.append(session.waiting_reason)
            lines.append("")

        return "\n".join(lines)
