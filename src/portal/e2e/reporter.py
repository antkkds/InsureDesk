"""InsureDesk — Production E2E Validation: Reporter.

Generates human-readable E2E validation summary reports.
"""
from __future__ import annotations

from typing import Dict, List

from src.portal.e2e.models import (
    E2EReport, E2EScenario, E2EStatus, ScenarioType, StepStatus,
)


class E2EReporter:
    """Generates E2E validation reports."""

    def generate_report(self, report: E2EReport) -> str:
        """Generate a complete human-readable E2E validation report."""
        lines: List[str] = []
        lines.append("=" * 60)
        lines.append(f"PRODUCTION E2E VALIDATION REPORT")
        lines.append("=" * 60)
        lines.append(f"Portal: {report.portal_id}")
        lines.append(f"Scenarios: {report.passed_count}/{report.total_scenarios} passed")
        lines.append(f"Steps: {report.passed_steps}/{report.total_steps} passed")
        lines.append(f"Duration: {report.total_duration:.1f}s")
        lines.append(f"Success Rate: {report.success_rate:.0f}%")
        lines.append("")

        if report.scenarios:
            lines.append("─" * 40)
            lines.append("SCENARIO RESULTS")
            lines.append("─" * 40)
            for sc in report.scenarios:
                lines.append(self._format_scenario(sc))
                lines.append("")

        lines.append("=" * 60)
        lines.append("END OF REPORT")
        lines.append("=" * 60)
        return "\n".join(lines)

    def summary_text(self, report: E2EReport) -> str:
        """One-line summary."""
        return (
            f"E2E: {report.passed_count}/{report.total_scenarios} scenarios passed "
            f"({report.passed_steps}/{report.total_steps} steps, "
            f"{report.success_rate:.0f}%)"
        )

    def _format_scenario(self, scenario: E2EScenario) -> str:
        """Format a single scenario result."""
        icons = {
            E2EStatus.PASSED: "✅",
            E2EStatus.FAILED: "❌",
            E2EStatus.ERROR: "💥",
            E2EStatus.SKIPPED: "⏭️",
            E2EStatus.PARTIAL: "⚠️",
        }
        icon = icons.get(scenario.status, "❓")

        lines = [
            f"  {icon} [{scenario.type.value}] {scenario.name}",
            f"     Status: {scenario.status.value}",
            f"     Steps: {scenario.passed_steps}/{scenario.total_steps}",
            f"     Duration: {scenario.total_duration:.1f}s",
        ]

        if scenario.error:
            lines.append(f"     Error: {scenario.error}")

        # Show failed steps
        for step in scenario.steps:
            if step.status in (StepStatus.FAILED, StepStatus.ERROR):
                lines.append(f"     ❌ Step '{step.name}': {step.error or 'failed'}")

        return "\n".join(lines)
