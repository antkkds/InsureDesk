"""Portal Workflow Recorder.

Records user browser interactions and converts them into
reusable Workflow YAML definitions for the ExecutionEngine.

Architecture:
    RecordingEngine
        ├── CaptureEngine (CDP events)
        ├── Normalizer (events → steps)
        ├── WorkflowSerializer (steps → YAML)
        └── ReplayEngine (YAML → ExecutionEngine)
"""

from __future__ import annotations

from src.portal.recorder.models import (
    RecordedEvent,
    RecordedStep,
    RecordingSession,
    Workflow,
    WorkflowStep,
    EventType,
)
from src.portal.recorder.engine import RecordingEngine
from src.portal.recorder.capture import CaptureEngine
from src.portal.recorder.normalizer import Normalizer
from src.portal.recorder.selector import SelectorGenerator
from src.portal.recorder.serializer import WorkflowSerializer
from src.portal.recorder.replay import ReplayEngine
from src.portal.recorder.exceptions import (
    RecorderError,
    CaptureError,
    SelectorGenerationError,
    NormalizationError,
    SerializationError,
    ReplayError,
    RecordingNotFoundError,
)

__all__ = [
    "RecordedEvent",
    "RecordedStep",
    "RecordingSession",
    "Workflow",
    "WorkflowStep",
    "EventType",
    "RecordingEngine",
    "CaptureEngine",
    "Normalizer",
    "SelectorGenerator",
    "WorkflowSerializer",
    "ReplayEngine",
    "RecorderError",
    "CaptureError",
    "SelectorGenerationError",
    "NormalizationError",
    "SerializationError",
    "ReplayError",
    "RecordingNotFoundError",
]
