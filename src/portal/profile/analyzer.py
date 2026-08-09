"""Portal Profile Intelligence — Profile Analyzer.

Analyzes PortalProfile configurations for completeness, coverage,
and potential improvements.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.profile.models import PortalProfile, ProfileHealth, HealthIssue
from src.portal.profile.validator import ProfileValidator
from src.portal.profile.schema import RECOMMENDED_FIELDS

logger = logging.getLogger("insuredesk.profile.analyzer")


class ProfileAnalyzer:
    """Analyzes portal profiles for quality and completeness.

    Usage:
        analyzer = ProfileAnalyzer()
        health = analyzer.analyze(profile)
        suggestions = analyzer.suggest_improvements(profile)
    """

    def __init__(self, validator: Optional[ProfileValidator] = None):
        self._validator = validator or ProfileValidator()

    def analyze(self, profile: PortalProfile) -> ProfileHealth:
        """Perform a full health analysis on a profile.

        Args:
            profile: The profile to analyze

        Returns:
            ProfileHealth with score, status, and issues
        """
        health = ProfileHealth(profile_id=profile.id)

        # 1. Schema version check
        checks = {}
        from src.portal.profile.schema import CURRENT_SCHEMA_VERSION as CUR_VER
        if profile.schema_version:
            version_parts = profile.schema_version.split(".")
            current_parts = [int(x) for x in CUR_VER.split(".")]
            checks["up_to_date"] = version_parts == current_parts
            if not checks["up_to_date"]:
                health.add_issue(HealthIssue(
                    category="up_to_date",
                    severity="warning",
                    message=f"Schema version {profile.schema_version} is not current",
                    suggestion="Upgrade to latest schema version",
                ))

        # 2. Required fields
        checks["has_required_fields"] = bool(profile.id and profile.name and profile.portal)
        if not checks["has_required_fields"]:
            health.add_issue(HealthIssue(
                category="completeness",
                severity="error",
                message="Missing required fields (id, name, or portal)",
            ))

        # 3. Recommended fields
        for field in RECOMMENDED_FIELDS:
            value = getattr(profile, field, None)
            if value is None or (isinstance(value, (dict, list)) and not value):
                health.add_issue(HealthIssue(
                    category="completeness",
                    severity="warning",
                    message=f"Recommended field '{field}' is missing or empty",
                    field=field,
                ))

        # 4. Workflow coverage
        checks["has_workflows"] = len(profile.workflows) > 0
        checks["has_mappings"] = len(profile.mappings) > 0
        checks["has_validation"] = len(profile.validation_rules) > 0

        if not checks["has_workflows"]:
            health.add_issue(HealthIssue(
                category="coverage",
                severity="error",
                message="No workflows defined",
                suggestion="Add at least one workflow (e.g. create_quote)",
            ))

        if not checks["has_mappings"]:
            health.add_issue(HealthIssue(
                category="coverage",
                severity="warning",
                message="No field mappings defined",
                suggestion="Add field mappings for form filling",
            ))

        if not checks["has_validation"]:
            health.add_issue(HealthIssue(
                category="coverage",
                severity="warning",
                message="No validation rules defined",
                suggestion="Add validation rules for data quality checks",
            ))

        # 5. Adapter check
        checks["has_adapter"] = bool(profile.adapter)
        if not checks["has_adapter"]:
            health.add_issue(HealthIssue(
                category="completeness",
                severity="warning",
                message="No adapter specified",
                suggestion="Specify a portal adapter class",
            ))

        health.checks = checks
        health.status = health._determine_status()
        return health

    def suggest_improvements(self, profile: PortalProfile) -> List[str]:
        """Generate human-readable improvement suggestions."""
        suggestions: List[str] = []
        health = self.analyze(profile)

        for issue in health.issues:
            if issue.suggestion:
                suggestions.append(f"[{issue.severity.upper()}] {issue.message}")
                suggestions.append(f"  → {issue.suggestion}")

        return suggestions
