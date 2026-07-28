"""Portal Validation Adapter — bridges browser session state to validation engine.

Captures portal-level validation signals (error messages on page,
disabled buttons, field-level errors) and feeds them to the
PortalValidationRule as portal_state.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.validation.models import ValidationContext, ValidationResult

logger = logging.getLogger("insuredesk.validation.portal_adapter")


class PortalValidationAdapter:
    """Captures portal-level state for validation engine.

    This adapter checks the browser page for:
    - Error messages displayed on the page
    - Disabled submit buttons
    - Field-level validation errors
    - Session expiry indicators
    - Portal-specific response messages

    In Sprint 4.2, this is a data collection layer.
    The actual DOM inspection will be implemented when integrated
    with the browser session in a later sprint.
    """

    def __init__(self):
        self._checks: Dict[str, Any] = {}

    def collect_portal_state(
        self,
        portal: str,
        page_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Collect portal state for validation.

        Args:
            portal: Portal name
            page_state: Raw page state from browser session (optional)

        Returns:
            Dict with portal state suitable for ValidationContext.portal_state
        """
        if page_state is None:
            page_state = {}

        portal_state = {
            "portal": portal,
            "errors": page_state.get("errors", []),
            "warnings": page_state.get("warnings", []),
            "has_error_display": page_state.get("has_error_display", False),
            "submit_enabled": page_state.get("submit_enabled", True),
            "session_valid": page_state.get("session_valid", True),
            "found_errors": [],
        }

        # Check for common error indicators
        error_text = page_state.get("error_text", "")
        if error_text:
            portal_state["found_errors"].append(error_text)

        # Check for specific portal error patterns
        if portal == "great_eastern":
            portal_state.update(self._check_great_eastern(page_state))
        elif portal == "aia":
            portal_state.update(self._check_aia(page_state))

        return portal_state

    def create_context(
        self,
        portal: str,
        action: str,
        customer: Optional[Dict[str, Any]] = None,
        quote: Optional[Dict[str, Any]] = None,
        form_data: Optional[Dict[str, Any]] = None,
        page_state: Optional[Dict[str, Any]] = None,
    ) -> ValidationContext:
        """Create a fully populated ValidationContext including portal state."""
        portal_state = self.collect_portal_state(portal, page_state)
        return ValidationContext(
            portal=portal,
            action=action,
            customer=customer or {},
            quote=quote or {},
            form_data=form_data or {},
            portal_state=portal_state,
        )

    @staticmethod
    def _check_great_eastern(
        page_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Great Eastern-specific portal checks."""
        checks: Dict[str, Any] = {}
        error_text = (page_state.get("error_text", "") or "").lower()

        if "medical question" in error_text:
            checks["medical_question_required"] = True
            checks["found_errors"] = checks.get("found_errors", []) + [
                "Medical questionnaire required"
            ]

        if "session" in error_text and ("expired" in error_text or "timeout" in error_text):
            checks["session_valid"] = False
            checks["found_errors"] = checks.get("found_errors", []) + [
                "Session expired"
            ]

        return checks

    @staticmethod
    def _check_aia(page_state: Dict[str, Any]) -> Dict[str, Any]:
        """AIA-specific portal checks."""
        checks: Dict[str, Any] = {}
        error_text = (page_state.get("error_text", "") or "").lower()

        if "declaration" in error_text:
            checks["declaration_required"] = True
            checks["found_errors"] = checks.get("found_errors", []) + [
                "Declaration required"
            ]

        return checks
