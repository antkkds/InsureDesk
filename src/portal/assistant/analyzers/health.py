"""Assistant — Health Analyzer.

Analyzes portal health status, profile versions,
and overall system state.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.portal.assistant.models import (
    AnalysisFinding, AnalysisSource, AnalysisResult,
)
from src.portal.profile.registry import ProfileManager
from src.portal.profile.versioning import VersionManager
from src.portal.drift.detector import DriftDetector
from src.portal.drift.storage import BaselineStorage


class HealthAnalyzer:
    """Analyzes overall portal health from multiple data sources."""

    def __init__(self, profile_manager: Optional[ProfileManager] = None,
                 versioning: Optional[VersionManager] = None,
                 drift_detector: Optional[DriftDetector] = None):
        self._pm = profile_manager or ProfileManager()
        self._versioning = versioning or VersionManager()
        self._drift = drift_detector or DriftDetector()

    def check_health(self, portal_id: str) -> List[AnalysisFinding]:
        """Comprehensive health check for a portal."""
        findings: List[AnalysisFinding] = []

        # 1. Profile status
        profile = self._pm.get(portal_id)
        if profile:
            findings.append(AnalysisFinding(
                severity="info",
                category="profile",
                message=f"Profile '{portal_id}' v{profile.version} loaded",
                source=AnalysisSource.PROFILE,
                confidence=1.0,
            ))
        else:
            findings.append(AnalysisFinding(
                severity="major",
                category="profile",
                message=f"Profile '{portal_id}' not found in registry",
                source=AnalysisSource.PROFILE,
                confidence=1.0,
                suggestion="Load profile using ProfileManager.load()",
            ))

        # 2. Version health
        versions = self._versioning.list_versions(portal_id)
        if not versions:
            findings.append(AnalysisFinding(
                severity="info",
                category="version",
                message=f"No version history for '{portal_id}'",
                source=AnalysisSource.VERSION,
                confidence=1.0,
                suggestion="Create a version snapshot to enable rollback",
            ))
        else:
            active = self._versioning.is_active(portal_id)
            active_ver = self._versioning.get_active_version(portal_id)
            status = "active" if active else "inactive"
            findings.append(AnalysisFinding(
                severity="info" if active else "minor",
                category="version",
                message=f"Profile '{portal_id}' is {status} "
                        f"({len(versions)} versions"
                        f"{f', pinned to {active_ver}' if active_ver else ''})",
                source=AnalysisSource.VERSION,
                confidence=1.0,
            ))

        # 3. Drift status
        try:
            report = self._drift.detect(portal_id)
            if report.actionable_count > 0:
                findings.append(AnalysisFinding(
                    severity="critical" if report.critical_count > 0 else "major",
                    category="drift",
                    message=f"{report.actionable_count} actionable drift events "
                            f"({report.critical_count} critical)",
                    detail=f"Health score: {report.health_score:.0f}/100",
                    source=AnalysisSource.DRIFT,
                    confidence=0.9,
                    suggestion="Run drift detection and update YAML mappings",
                    affected_items=[e.selector_name for e in report.events if e.is_actionable],
                ))
            else:
                findings.append(AnalysisFinding(
                    severity="info",
                    category="drift",
                    message=f"No drift detected (health: {report.health_score:.0f}/100)",
                    source=AnalysisSource.DRIFT,
                    confidence=0.9,
                ))
        except Exception:
            findings.append(AnalysisFinding(
                severity="info",
                category="drift",
                message=f"No baseline captured for '{portal_id}'",
                source=AnalysisSource.DRIFT,
                confidence=1.0,
                suggestion="Run BaselineRecorder.capture_from_yaml() first",
            ))

        return findings

    def summarize_all(self) -> str:
        """Summarize health across all portals with baselines."""
        from src.portal.drift.storage import BaselineStorage
        storage = BaselineStorage()
        portals = storage.list_baselines()

        if not portals:
            return "ℹ️ No portal baselines found"

        lines = []
        for pid in portals:
            try:
                dr = self._drift.detect(pid)
                if dr.actionable_count > 0:
                    lines.append(f"🔴 {pid}: {dr.actionable_count} actionable drift")
                else:
                    lines.append(f"✅ {pid}: healthy ({dr.health_score:.0f}/100)")
            except Exception as e:
                lines.append(f"❓ {pid}: {e}")

        return "\n".join(lines) if lines else "ℹ️ No portals monitored"
