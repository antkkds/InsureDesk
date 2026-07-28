"""InsureDesk — Portal Drift Detection: Suggestions Engine.

Suggests updated selectors and fixes for detected drift events.
Leverages the existing SelectorGenerator to propose alternatives.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from src.portal.drift.models import DriftEvent, DriftReport, DriftSeverity

logger = logging.getLogger("insuredesk.drift.suggestions")


class SuggestionEngine:
    """Generates fix suggestions for drift events.

    For each actionable drift event, suggests:
    1. Accept the new selector (auto-update)
    2. Alternative selector strategies
    3. Escalate if the page structure changed significantly
    """

    def suggest_for_event(self, event: DriftEvent) -> Dict[str, str]:
        """Generate fix suggestion for a single drift event.

        Args:
            event: A drift event.

        Returns:
            Dict with 'type', 'action', 'description', and 'new_selector'.
        """
        if not event.is_actionable:
            return {
                "type": "info",
                "action": "monitor",
                "description": "No action needed — informational only.",
                "new_selector": event.current_selector or "",
            }

        # Critical: selector missing
        if event.drift_type.value == "selector_missing":
            return {
                "type": "critical",
                "action": "recapture",
                "description": (
                    f"Element '{event.selector_name}' no longer found. "
                    f"Run Capture Mode to identify the new selector."
                ),
                "new_selector": "",
            }

        # Changed selector — suggest the new one if available
        if event.suggested_selector:
            return {
                "type": "update",
                "action": "update_yaml",
                "description": (
                    f"Update selector in YAML from "
                    f"'{event.baseline_selector}' to "
                    f"'{event.suggested_selector}'"
                ),
                "new_selector": event.suggested_selector,
            }

        # Fallback
        return {
            "type": "investigate",
            "action": "manual_review",
            "description": (
                f"Selector '{event.selector_name}' changed. "
                f"Manual review recommended."
            ),
            "new_selector": event.current_selector or "",
        }

    def suggest_for_report(self, report: DriftReport) -> List[Dict]:
        """Generate suggestions for all actionable events in a report.

        Returns:
            List of suggestion dicts sorted by severity.
        """
        suggestions = []
        for event in report.events:
            suggestion = self.suggest_for_event(event)
            suggestion["selector_name"] = event.selector_name
            suggestion["severity"] = event.severity.value
            suggestion["confidence"] = str(event.confidence)
            suggestions.append(suggestion)

        # Sort: critical first, then major, then rest
        severity_order = {"critical": 0, "major": 1, "minor": 2, "info": 3}
        suggestions.sort(key=lambda s: severity_order.get(s["severity"], 99))
        return suggestions
