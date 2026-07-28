"""InsureDesk — Portal Drift Detection: Impact Analyzer.

Analyzes drift events to determine which workflows and
portal features are affected by each detected change.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.portal.drift.models import DriftEvent, DriftReport, DriftSeverity

logger = logging.getLogger("insuredesk.drift.analyzer")

# Mapping: selector path prefix -> workflow name
WORKFLOW_MAP: Dict[str, str] = {
    "login": "Login & Authentication",
    "dashboard": "Dashboard & Home",
    "policy_search": "Policy Search",
    "policy_details": "Policy Details",
    "claims": "Claims Management",
    "documents": "Document Upload",
    "renewal": "Policy Renewal",
    "customer": "Customer Search",
    "quotation": "Quotation / New Business",
}


class DriftAnalyzer:
    """Analyzes drift events to determine impacted workflows.

    Uses selector name prefixes to map each selector to
    a business workflow.
    """

    def analyze_report(self, report: DriftReport) -> DriftReport:
        """Enrich a DriftReport with workflow impact analysis.

        Mutates the report's events in-place by adding
        affected_workflow info.

        Args:
            report: DriftReport to analyze.

        Returns:
            Same report with enriched events.
        """
        for event in report.events:
            event.affected_workflows = self._find_workflows(event)
        return report

    def analyze_event(self, event: DriftEvent) -> DriftEvent:
        """Analyze a single drift event for workflow impact."""
        event.affected_workflows = self._find_workflows(event)
        return event

    def _find_workflows(self, event: DriftEvent) -> List[str]:
        """Determine which workflows are affected by a drift event."""
        workflows = []
        for prefix, wf_name in WORKFLOW_MAP.items():
            if event.selector_name.startswith(prefix):
                workflows.append(wf_name)

        # If no direct match, try to infer from first segment
        if not workflows:
            first_seg = event.selector_name.split(".")[0]
            if first_seg in WORKFLOW_MAP:
                workflows.append(WORKFLOW_MAP[first_seg])

        return workflows or ["Unknown"]

    def summary_by_workflow(self, report: DriftReport) -> Dict[str, Any]:
        """Group drift events by affected workflow.

        Returns:
            Dict mapping workflow names to event counts and severity.
        """
        by_workflow: Dict[str, Dict] = {}
        for event in report.events:
            for wf in event.affected_workflows:
                if wf not in by_workflow:
                    by_workflow[wf] = {
                        "total": 0,
                        "critical": 0,
                        "major": 0,
                        "minor": 0,
                        "events": [],
                    }
                by_workflow[wf]["total"] += 1
                by_workflow[wf][event.severity.value] += 1
                by_workflow[wf]["events"].append(event.summary)

        return by_workflow
