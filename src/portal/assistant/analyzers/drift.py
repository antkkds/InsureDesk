"""Assistant — Drift Analyzer.

Analyzes drift detection results to answer
"why did X fail?" type questions.
"""
from __future__ import annotations

from typing import List, Optional

from src.portal.assistant.models import (
    AnalysisFinding, AnalysisSource, AnalysisResult,
    QueryIntent,
)
from src.portal.drift.detector import DriftDetector
from src.portal.drift.storage import BaselineStorage


class DriftAnalyzer:
    """Analyzes drift data to explain workflow failures."""

    def __init__(self, detector: Optional[DriftDetector] = None,
                 storage: Optional[BaselineStorage] = None):
        self._detector = detector or DriftDetector(storage=storage)

    def analyze_portal(self, portal_id: str,
                        workflow_name: Optional[str] = None) -> List[AnalysisFinding]:
        """Analyze drift for a portal and produce findings."""
        from src.portal.drift.exceptions import BaselineNotFoundError

        findings: List[AnalysisFinding] = []

        try:
            report = self._detector.detect(portal_id)
        except BaselineNotFoundError:
            findings.append(AnalysisFinding(
                severity="info",
                category="drift",
                message=f"No baseline snapshot for '{portal_id}'. Run baseline capture first.",
                source=AnalysisSource.DRIFT,
                confidence=1.0,
            ))
            return findings

        for event in report.events:
            # Filter by workflow if specified
            if workflow_name and workflow_name not in " ".join(event.affected_workflows).lower():
                continue

            if not event.is_actionable:
                continue

            finding = AnalysisFinding(
                severity=event.severity.value,
                category=f"drift_{event.drift_type.value}",
                message=(
                    f"Selector '{event.selector_name}' changed: "
                    f"{event.description}"
                ),
                detail=(
                    f"Baseline: {event.baseline_selector} → "
                    f"Current: {event.current_selector or 'MISSING'}"
                ),
                source=AnalysisSource.DRIFT,
                confidence=event.confidence,
                suggestion=f"Update YAML mapping for '{event.selector_name}'",
                affected_items=event.affected_workflows,
            )
            findings.append(finding)

        return findings

    def summarize_drift(self, portal_id: str) -> str:
        """One-line summary of drift status."""
        try:
            report = self._detector.detect(portal_id)
            if not report.events:
                return f"✅ {portal_id}: No drift detected"
            return (
                f"{'🔴' if report.actionable_count > 0 else '🟢'} "
                f"{portal_id}: {report.actionable_count} actionable "
                f"({report.critical_count} critical) — "
                f"health score {report.health_score:.0f}/100"
            )
        except Exception as e:
            return f"❌ {portal_id}: {e}"
