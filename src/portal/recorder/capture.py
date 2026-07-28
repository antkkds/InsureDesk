"""Portal Workflow Recorder — Capture Engine.

Captures browser events via CDP during user interaction with a portal.
Produces RecordedEvent objects for later normalization.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from src.portal.recorder.models import (
    EventType,
    RecordedEvent,
    RecordingSession,
)
from src.portal.recorder.selector import SelectorGenerator
from src.portal.recorder.exceptions import CaptureError

logger = logging.getLogger("insuredesk.recorder.capture")


class CaptureEngine:
    """Captures browser events during user portal interaction.

    In Sprint 4.4, this works in two modes:
    1. Live CDP mode (future): Attaches to Chrome and listens for events
    2. Manual mode (Sprint 4.4): Accepts programmatic event submissions

    Usage:
        engine = CaptureEngine()
        session = engine.start_session(portal="great_eastern", url="...")

        # Simulate or capture events
        engine.capture_event(session, {"type": "click", "tag_name": "button", ...})

        # Stop and get recorded events
        events = engine.stop_session(session.id)
    """

    def __init__(self, selector_generator: Optional[SelectorGenerator] = None):
        self._selector_gen = selector_generator or SelectorGenerator()
        self._sessions: Dict[str, RecordingSession] = {}
        self._event_listeners: List[Callable] = []

    def start_session(
        self,
        portal: str,
        url: str = "",
    ) -> RecordingSession:
        """Start a new recording session.

        Args:
            portal: Portal name being recorded
            url: Starting URL

        Returns:
            The new RecordingSession
        """
        session = RecordingSession(portal=portal, url=url)
        session.start()
        self._sessions[session.id] = session
        logger.info("Recording session started: %s (portal=%s)", session.id, portal)
        return session

    def capture_event(
        self,
        session_id: str,
        event_data: Dict[str, Any],
    ) -> RecordedEvent:
        """Capture a single browser event.

        Args:
            session_id: Recording session ID
            event_data: Event data dict with at minimum {"type": "click|input|..."}

        Returns:
            The recorded event

        Raises:
            CaptureError: If session not found or event data invalid
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise CaptureError(f"Recording session '{session_id}' not found")

        if not session.is_active:
            raise CaptureError(f"Recording session '{session_id}' is not active")

        event_type = event_data.get("type", "")
        if event_type not in EventType.all():
            raise CaptureError(f"Unknown event type: {event_type}")

        # Generate selector if not provided
        selector = event_data.get("selector")
        if not selector:
            try:
                selector = self._selector_gen.generate_from_event(event_data)
            except Exception:
                pass

        event = RecordedEvent(
            type=event_type,
            url=event_data.get("url", session.url),
            selector=selector,
            tag_name=event_data.get("tag_name"),
            value=event_data.get("value"),
            text=event_data.get("text"),
            position=event_data.get("position"),
            metadata=event_data.get("metadata", {}),
        )
        session.add_event(event)

        # Notify listeners
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception as e:
                logger.warning("Event listener failed: %s", e)

        return event

    def stop_session(self, session_id: str) -> RecordingSession:
        """Stop a recording session and return the captured data.

        Args:
            session_id: Session to stop

        Returns:
            The completed RecordingSession with all events

        Raises:
            CaptureError: If session not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise CaptureError(f"Recording session '{session_id}' not found")

        session.stop()
        logger.info(
            "Recording session stopped: %s (%d events, %.1fs)",
            session_id, session.event_count, session.duration_seconds,
        )
        return session

    def get_session(self, session_id: str) -> Optional[RecordingSession]:
        """Get a recording session by ID."""
        return self._sessions.get(session_id)

    def add_event_listener(self, listener: Callable) -> None:
        """Register a listener that fires on each captured event."""
        self._event_listeners.append(listener)

    def clear_sessions(self) -> None:
        """Clear all stored sessions."""
        self._sessions.clear()
