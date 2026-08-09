"""Portal Profile Intelligence — Data Models.

Core data structures for managing, analyzing, and comparing
InsureDesk Portal Profile configurations (YAML files).

Note: These are PORTAL CONFIGURATIONS (technical YAML), NOT
UIP-AI Blueprints (industry templates). The boundary is strict.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field as data_field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ProfileStatus(Enum):
    """Overall health status of a portal profile."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class HealthCategory(Enum):
    """Categories for health checks."""
    COVERAGE = "coverage"
    COMPLETENESS = "completeness"
    VALIDITY = "validity"
    CONSISTENCY = "consistency"
    UP_TO_DATE = "up_to_date"


@dataclass
class PortalProfile:
    """Represents a complete portal profile configuration.

    A PortalProfile describes how InsureDesk automates a specific
    insurance portal. It's the central configuration unit.
    """

    id: str = ""
    name: str = ""
    portal: str = ""
    version: str = "1.0"
    schema_version: str = "1.0"
    workflows: Dict[str, Any] = data_field(default_factory=dict)
    mappings: Dict[str, Any] = data_field(default_factory=dict)
    validation_rules: Dict[str, Any] = data_field(default_factory=dict)
    adapter: str = ""
    metadata: Dict[str, Any] = data_field(default_factory=dict)
    created_at: datetime = data_field(default_factory=datetime.now)
    updated_at: datetime = data_field(default_factory=datetime.now)

    @property
    def workflow_count(self) -> int:
        return len(self.workflows)

    @property
    def mapping_count(self) -> int:
        return len(self.mappings)

    @property
    def validation_count(self) -> int:
        return len(self.validation_rules)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "portal": self.portal,
            "version": self.version,
            "schema_version": self.schema_version,
            "workflow_count": self.workflow_count,
            "mapping_count": self.mapping_count,
            "validation_count": self.validation_count,
            "adapter": self.adapter,
        }


@dataclass
class ProfileVersion:
    """Tracks a specific version of a portal profile."""

    profile_id: str = ""
    version: str = ""
    schema_version: str = ""
    created_at: datetime = data_field(default_factory=datetime.now)
    changes: List[str] = data_field(default_factory=list)
    source: str = "manual"  # 'manual', 'auto_upgrade', 'migration'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "schema_version": self.schema_version,
            "changes": self.changes,
            "source": self.source,
        }


@dataclass
class ProfileDiff:
    """Result of comparing two portal profile versions."""

    old_version: str = ""
    new_version: str = ""
    added: List[str] = data_field(default_factory=list)
    removed: List[str] = data_field(default_factory=list)
    modified: List[Dict[str, Any]] = data_field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)

    @property
    def change_count(self) -> int:
        return len(self.added) + len(self.removed) + len(self.modified)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "old_version": self.old_version,
            "new_version": self.new_version,
            "added": self.added,
            "removed": self.removed,
            "modified": self.modified,
            "change_count": self.change_count,
        }


@dataclass
class HealthIssue:
    """A single health issue detected in a portal profile."""

    category: str = ""
    severity: str = "warning"  # 'info', 'warning', 'error'
    message: str = ""
    field: Optional[str] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
            "suggestion": self.suggestion,
        }


@dataclass
class ProfileHealth:
    """Health assessment of a portal profile."""

    profile_id: str = ""
    score: int = 100  # 0-100
    status: str = "healthy"
    issues: List[HealthIssue] = data_field(default_factory=list)
    checks: Dict[str, bool] = data_field(default_factory=dict)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def add_issue(self, issue: HealthIssue) -> None:
        self.issues.append(issue)
        if issue.severity == "error":
            self.score -= 25
        elif issue.severity == "warning":
            self.score -= 10
        self.score = max(0, min(100, self.score))
        self.status = self._determine_status()

    def _determine_status(self) -> str:
        if self.error_count > 0:
            return ProfileStatus.CRITICAL.value
        if self.warning_count >= 3:
            return ProfileStatus.WARNING.value
        if self.score >= 80:
            return ProfileStatus.HEALTHY.value
        if self.score >= 50:
            return ProfileStatus.WARNING.value
        return ProfileStatus.CRITICAL.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "score": self.score,
            "status": self.status,
            "issues": [i.to_dict() for i in self.issues],
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "checks": self.checks,
        }
