"""Portal Workflow Recorder — Data Models.

Captures user browser interactions and converts them into
reusable Workflow YAML definitions for the ExecutionEngine.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field as data_field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType:
    """Raw CDP event types captured during recording."""
    CLICK = "click"
    INPUT = "input"
    SELECT = "select"
    NAVIGATE = "navigate"
    WAIT = "wait"
    UPLOAD = "upload"
    SUBMIT = "submit"
    HOVER = "hover"
    SCROLL = "scroll"

    @classmethod
    def all(cls) -> List[str]:
        return [v for k, v in vars(cls).items() if not k.startswith("_") and isinstance(v, str)]


@dataclass
class RecordedEvent:
    """A raw browser event captured via CDP."""

    id: str = data_field(
        default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}"
    )
    type: str = ""
    timestamp: datetime = data_field(default_factory=datetime.now)
    url: str = ""
    selector: Optional[str] = None
    tag_name: Optional[str] = None
    value: Any = None
    text: Optional[str] = None
    position: Optional[Dict[str, int]] = None  # x, y
    metadata: Dict[str, Any] = data_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp.isoformat(),
            "url": self.url,
            "selector": self.selector,
            "tag_name": self.tag_name,
            "value": self.value,
            "text": self.text,
        }


@dataclass
class RecordedStep:
    """A normalized business step derived from one or more RecordedEvents."""

    id: str = data_field(
        default_factory=lambda: f"step_{uuid.uuid4().hex[:8]}"
    )
    action: str = ""
    target: Optional[str] = None
    value: Any = None
    selector: Optional[str] = None
    url: str = ""
    wait_after_ms: int = 500
    metadata: Dict[str, Any] = data_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "target": self.target,
            "value": self.value,
            "selector": self.selector,
        }


@dataclass
class WorkflowStep:
    """A step in the final Workflow YAML definition.

    Designed to be serialized directly to YAML for ExecutionEngine.
    """

    action: str = ""
    parameters: Dict[str, Any] = data_field(default_factory=dict)
    wait_after_ms: int = 500
    retry_policy: Optional[Dict[str, Any]] = None
    checkpoint: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = {"action": self.action, "parameters": dict(self.parameters)}
        if self.wait_after_ms != 500:
            d["wait_after_ms"] = self.wait_after_ms
        if self.retry_policy:
            d["retry_policy"] = self.retry_policy
        if not self.checkpoint:
            d["checkpoint"] = False
        return d


@dataclass
class Workflow:
    """Complete workflow definition.

    The primary output of the Workflow Recorder.
    Designed for YAML serialization and ExecutionEngine consumption.
    """

    id: str = data_field(
        default_factory=lambda: f"wf_{uuid.uuid4().hex[:12]}"
    )
    name: str = ""
    portal: str = ""
    version: str = "1.0"
    steps: List[WorkflowStep] = data_field(default_factory=list)
    metadata: Dict[str, Any] = data_field(default_factory=dict)
    created_at: datetime = data_field(default_factory=datetime.now)
    total_steps: int = 0

    def add_step(self, step: WorkflowStep) -> None:
        self.steps.append(step)
        self.total_steps = len(self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow": {
                "name": self.name,
                "portal": self.portal,
                "version": self.version,
                "steps": [s.to_dict() for s in self.steps],
            }
        }

    @property
    def step_count(self) -> int:
        return len(self.steps)


@dataclass
class RecordingSession:
    """Tracks the state of an active recording session."""

    id: str = data_field(
        default_factory=lambda: f"rec_{uuid.uuid4().hex[:12]}"
    )
    portal: str = ""
    url: str = ""
    events: List[RecordedEvent] = data_field(default_factory=list)
    is_active: bool = False
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None

    def start(self) -> None:
        self.is_active = True
        self.started_at = datetime.now()

    def stop(self) -> None:
        self.is_active = False
        self.stopped_at = datetime.now()

    def add_event(self, event: RecordedEvent) -> None:
        self.events.append(event)

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def duration_seconds(self) -> float:
        if self.started_at and self.stopped_at:
            return (self.stopped_at - self.started_at).total_seconds()
        return 0.0
