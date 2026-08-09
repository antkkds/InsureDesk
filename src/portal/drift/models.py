"""InsureDesk — Portal Drift Detection Data Models.

Models for detecting, reporting, and suggesting fixes
for portal UI changes that break automation workflows.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DriftSeverity(Enum):
    """Severity of a detected drift."""
    CRITICAL = "critical"      # Selector changed — workflow will fail
    MAJOR = "major"            # Selector changed but alternative exists
    MINOR = "minor"            # Attribute change, no functional impact
    INFO = "info"              # New element appeared
    RESOLVED = "resolved"      # Previously detected drift is resolved


class DriftType(Enum):
    """Type of drift detected."""
    SELECTOR_MISSING = "selector_missing"        # Element not found
    SELECTOR_CHANGED = "selector_changed"        # Different element at path
    ATTRIBUTE_CHANGED = "attribute_changed"      # Text/attr value changed
    ELEMENT_ADDED = "element_added"             # New element in page
    ELEMENT_REMOVED = "element_removed"         # Element missing
    PAGE_STRUCTURE = "page_structure"           # Major DOM structure change
    LOGIN_FLOW = "login_flow"                   # Login flow changed
    NAVIGATION = "navigation"                   # Navigation path changed
    TIMEOUT_CHANGED = "timeout_changed"         # Load time increased


@dataclass
class BaselineSelector:
    """A selector's baseline state for drift comparison.

    Stores all attributes and metadata needed to detect
    when a portal element has changed.
    """
    name: str                                    # Logical name (e.g. 'login.username')
    selector: str                                # The CSS/XPath selector
    tag: str = ""                                # HTML tag
    text: str = ""                               # Text content (trimmed)
    attributes: Dict[str, str] = field(default_factory=dict)
    page_url: str = ""                           # URL where captured
    position: Optional[Dict[str, int]] = None    # x, y position
    is_interactive: bool = True                  # Is it clickable/input?
    hash: str = ""                               # Hash of element structure

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "selector": self.selector,
            "tag": self.tag,
            "text": self.text,
            "attributes": self.attributes,
            "page_url": self.page_url,
            "position": self.position,
            "is_interactive": self.is_interactive,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaselineSelector:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BaselineSnapshot:
    """A complete baseline snapshot of a portal's UI state.

    Captured by visiting each portal page and recording all
    interactive elements and their selectors.
    """
    portal_id: str                               # 'great_eastern', 'aia', etc.
    id: str = field(default_factory=lambda: f"bl_{uuid.uuid4().hex[:8]}")
    timestamp: datetime = field(default_factory=datetime.now)
    version: str = "1.0"
    selectors: Dict[str, BaselineSelector] = field(default_factory=dict)
    pages: Dict[str, str] = field(default_factory=dict)  # page_name -> url
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def selector_count(self) -> int:
        return len(self.selectors)

    def find_selector(self, name: str) -> Optional[BaselineSelector]:
        return self.selectors.get(name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portal_id": self.portal_id,
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "selectors": {k: v.to_dict() for k, v in self.selectors.items()},
            "pages": self.pages,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaselineSnapshot:
        selectors = {}
        for k, v in data.get("selectors", {}).items():
            selectors[k] = BaselineSelector.from_dict(v)
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(
            portal_id=data["portal_id"],
            id=data.get("id", f"bl_{uuid.uuid4().hex[:8]}"),
            timestamp=data.get("timestamp", datetime.now()),
            version=data.get("version", "1.0"),
            selectors=selectors,
            pages=data.get("pages", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DriftEvent:
    """A single drift event — one selector that changed."""
    selector_name: str                           # e.g. 'login.username'
    baseline_selector: str                       # Original selector
    drift_type: DriftType = DriftType.SELECTOR_CHANGED
    severity: DriftSeverity = DriftSeverity.MAJOR
    current_selector: Optional[str] = None       # New selector (if found)
    confidence: float = 0.0                      # Detection confidence (0-1)
    description: str = ""                        # Human-readable description
    tag: str = ""                                # HTML tag
    text_before: str = ""                        # Previous text content
    text_after: str = ""                         # Current text content
    attributes_before: Dict[str, str] = field(default_factory=dict)
    attributes_after: Dict[str, str] = field(default_factory=dict)
    suggested_selector: Optional[str] = None     # Auto-suggested fix
    affected_workflows: List[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: f"de_{uuid.uuid4().hex[:8]}")

    @property
    def is_actionable(self) -> bool:
        """Whether this drift needs human action."""
        return self.severity in (DriftSeverity.CRITICAL, DriftSeverity.MAJOR)

    @property
    def summary(self) -> str:
        """One-line summary."""
        return (
            f"[{self.severity.value.upper()}] {self.selector_name}: "
            f"{self.description[:100]}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selector_name": self.selector_name,
            "baseline_selector": self.baseline_selector,
            "current_selector": self.current_selector,
            "drift_type": self.drift_type.value,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "description": self.description,
            "tag": self.tag,
            "text_before": self.text_before,
            "text_after": self.text_after,
            "suggested_selector": self.suggested_selector,
            "affected_workflows": self.affected_workflows,
            "is_actionable": self.is_actionable,
            "id": self.id,
        }


@dataclass
class DriftReport:
    """Complete drift detection report for a portal."""
    portal_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: f"dr_{uuid.uuid4().hex[:8]}")
    events: List[DriftEvent] = field(default_factory=list)
    baseline_version: str = ""
    current_version: str = ""
    total_selectors_checked: int = 0
    total_selectors_changed: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def critical_count(self) -> int:
        return sum(1 for e in self.events if e.severity == DriftSeverity.CRITICAL)

    @property
    def major_count(self) -> int:
        return sum(1 for e in self.events if e.severity == DriftSeverity.MAJOR)

    @property
    def actionable_count(self) -> int:
        return sum(1 for e in self.events if e.is_actionable)

    @property
    def health_score(self) -> float:
        """Score 0-100: 100 = no drift, 0 = all broken."""
        if not self.total_selectors_checked:
            return 100.0
        weight = {
            DriftSeverity.CRITICAL: 10,
            DriftSeverity.MAJOR: 5,
            DriftSeverity.MINOR: 2,
            DriftSeverity.INFO: 0.5,
        }
        penalty = sum(
            weight.get(e.severity, 1) for e in self.events
        )
        return max(0, 100 - (penalty / self.total_selectors_checked * 100))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portal_id": self.portal_id,
            "timestamp": self.timestamp.isoformat(),
            "id": self.id,
            "events": [e.to_dict() for e in self.events],
            "baseline_version": self.baseline_version,
            "current_version": self.current_version,
            "total_selectors_checked": self.total_selectors_checked,
            "total_selectors_changed": self.total_selectors_changed,
            "critical_count": self.critical_count,
            "major_count": self.major_count,
            "actionable_count": self.actionable_count,
            "health_score": self.health_score,
        }
