"""Portal Workflow Recorder — RecordingEngine.

The main orchestrator for the recording workflow.
Coordinates CaptureEngine, Normalizer, WorkflowSerializer, and ReplayEngine.

High-level flow:
    start_recording() → user interacts with portal → stop_recording()
    → normalize_events() → to_workflow() → save_yaml()
    → replay_workflow()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.recorder.models import RecordedEvent, RecordedStep, RecordingSession, Workflow
from src.portal.recorder.capture import CaptureEngine
from src.portal.recorder.normalizer import Normalizer
from src.portal.recorder.serializer import WorkflowSerializer
from src.portal.recorder.replay import ReplayEngine
from src.portal.recorder.exceptions import (
    CaptureError,
    RecordingNotFoundError,
)
from src.portal.execution.models import ExecutionResult
from src.portal.execution.engine import ExecutionEngine

logger = logging.getLogger("insuredesk.recorder.engine")


class RecordingEngine:
    """High-level orchestrator for workflow recording.

    Usage:
        engine = RecordingEngine(execution_engine)

        # Record
        session = engine.start_recording("great_eastern", "https://...")
        # ... user interacts with portal ...
        engine.stop_recording(session.id)

        # Generate workflow
        workflow = engine.to_workflow(session.id, name="ge_quote")
        filepath = engine.save_workflow(workflow, "portals/ge_quote.yaml")

        # Replay
        result = engine.replay_workflow(workflow)
    """

    def __init__(
        self,
        execution_engine: ExecutionEngine,
        capture: Optional[CaptureEngine] = None,
        normalizer: Optional[Normalizer] = None,
        serializer: Optional[WorkflowSerializer] = None,
        replay: Optional[ReplayEngine] = None,
    ):
        self._capture = capture or CaptureEngine()
        self._normalizer = normalizer or Normalizer()
        self._serializer = serializer or WorkflowSerializer()
        self._replay = replay or ReplayEngine(execution_engine)

    # ── Recording ──

    def start_recording(
        self,
        portal: str,
        url: str = "",
    ) -> RecordingSession:
        """Start a new recording session."""
        return self._capture.start_session(portal=portal, url=url)

    def capture_event(
        self,
        session_id: str,
        event_data: Dict[str, Any],
    ) -> RecordedEvent:
        """Capture a single browser event during recording."""
        return self._capture.capture_event(session_id, event_data)

    def stop_recording(self, session_id: str) -> RecordingSession:
        """Stop recording and return the session."""
        return self._capture.stop_session(session_id)

    # ── Normalization ──

    def normalize_events(
        self,
        session_id: str,
    ) -> List[RecordedStep]:
        """Normalize raw events from a session into steps."""
        session = self._capture.get_session(session_id)
        if session is None:
            raise RecordingNotFoundError(
                f"Recording session '{session_id}' not found"
            )
        return self._normalizer.normalize(session.events)

    # ── Serialization ──

    def to_workflow(
        self,
        session_id: str,
        name: Optional[str] = None,
    ) -> Workflow:
        """Convert a recording session into a Workflow."""
        session = self._capture.get_session(session_id)
        if session is None:
            raise RecordingNotFoundError(
                f"Recording session '{session_id}' not found"
            )
        steps = self._normalizer.normalize(session.events)
        return self._serializer.to_workflow(
            steps, portal=session.portal, name=name,
        )

    def save_workflow(
        self,
        workflow: Workflow,
        filepath: str,
    ) -> str:
        """Save a Workflow to a YAML file."""
        return self._serializer.save_yaml(workflow, filepath)

    def get_session(
        self,
        session_id: str,
    ) -> Optional[RecordingSession]:
        """Get a recording session by ID."""
        return self._capture.get_session(session_id)

    # ── Replay ──

    def replay_workflow(
        self,
        workflow: Workflow,
        data: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Replay a recorded workflow through the execution engine."""
        return self._replay.execute_workflow(workflow, data)

    def replay_workflow_with_resume(
        self,
        workflow: Workflow,
        data: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Replay a workflow with checkpoint resume support."""
        return self._replay.execute_workflow_with_resume(workflow, data)
