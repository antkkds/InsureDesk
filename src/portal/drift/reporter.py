"""InsureDesk — Portal Drift Detection: Reporter.

Generates human-readable drift reports with severity,
impact analysis, and suggested fixes.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from src.portal.drift.models import DriftReport, DriftSeverity, DriftEvent
from src.portal.drift.analyzer import DriftAnalyzer
from src.portal.drift.suggestions import SuggestionEngine

logger = logging.getLogger("insuredesk.drift.reporter")


class DriftReporter:
    """Generates human-readable reports from drift detection results.

    Leverages the Review Engine's formatter for consistent output style.
    """

    def __init__(self, analyzer: Optional[DriftAnalyzer] = None,
                 suggestions: Optional[SuggestionEngine] = None):
        self._analyzer = analyzer or DriftAnalyzer()
        self._suggestions = suggestions or SuggestionEngine()

    def generate_report(self, report: DriftReport) -> str:
        """Generate a complete human-readable drift report.

        Args:
            report: The DriftReport to format.

        Returns:
            Formatted report string.
        """
        # Analyze and add suggestions
        self._analyzer.analyze_report(report)

        lines: List[str] = []
        lines.append("=" * 60)
        lines.append(f"PORTAL DRIFT REPORT: {report.portal_id.upper()}")
        lines.append("=" * 60)
        lines.append(f"Health Score: {report.health_score:.1f}/100")
        lines.append(f"Checked: {report.total_selectors_checked} selectors")
        lines.append(f"Changed: {report.total_selectors_changed}")
        lines.append(f"Critical: {report.critical_count}")
        lines.append(f"Major: {report.major_count}")
        lines.append(f"Actionable: {report.actionable_count}")
        lines.append(f"Timestamp: {report.timestamp.isoformat()}")
        lines.append("")

        # Workflow impact summary
        wf_summary = self._analyzer.summary_by_workflow(report)
        if wf_summary:
            lines.append("─" * 40)
            lines.append("WORKFLOW IMPACT")
            lines.append("─" * 40)
            for wf_name, info in sorted(wf_summary.items()):
                icon = "🔴" if info["critical"] else "🟡" if info["major"] else "🟢"
                lines.append(
                    f"  {icon} {wf_name}: "
                    f"{info['critical']} critical, "
                    f"{info['major']} major, "
                    f"{info['minor']} minor"
                )
            lines.append("")

        # Detailed events
        if report.events:
            lines.append("─" * 40)
            lines.append("DETAILED FINDINGS")
            lines.append("─" * 40)
            for event in report.events:
                lines.append(self._format_event(event))
                lines.append("")

        # Suggestions
        suggestions = self._suggestions.suggest_for_report(report)
        if suggestions:
            lines.append("─" * 40)
            lines.append("SUGGESTED ACTIONS")
            lines.append("─" * 40)
            for s in suggestions:
                icon = "🔴" if s["severity"] == "critical" else "🟡" if s["severity"] == "major" else "ℹ️"
                lines.append(f"  {icon} [{s['severity'].upper()}] {s['selector_name']}")
                lines.append(f"     {s['description']}")
                if s.get("new_selector"):
                    lines.append(f"     → {s['new_selector']}")
                lines.append("")

        lines.append("=" * 60)
        lines.append("END OF REPORT")
        lines.append("=" * 60)

        return "\n".join(lines)

    def _format_event(self, event: DriftEvent) -> str:
        """Format a single drift event."""
        severity_icons = {
            DriftSeverity.CRITICAL: "🔴",
            DriftSeverity.MAJOR: "🟡",
            DriftSeverity.MINOR: "🟢",
            DriftSeverity.INFO: "ℹ️",
            DriftSeverity.RESOLVED: "✅",
        }
        icon = severity_icons.get(event.severity, "❓")

        lines = [
            f"  {icon} {event.selector_name} "
            f"(confidence: {event.confidence:.0%})",
            f"     {event.description}",
        ]

        if event.affected_workflows:
            wfs = ", ".join(event.affected_workflows)
            lines.append(f"     Workflows: {wfs}")

        if event.suggested_selector:
            lines.append(f"     Suggested: {event.suggested_selector}")

        return "\n".join(lines)

    def summary_text(self, report: DriftReport) -> str:
        """One-line summary for quick status."""
        return (
            f"{report.portal_id}: health={report.health_score:.0f}/100, "
            f"{report.actionable_count} actionable "
            f"({report.critical_count} critical)"
        )
