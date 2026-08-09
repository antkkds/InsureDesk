"""InsureDesk Quote Tools — CalculateQuoteTool.

Executes a read-only quote calculation on an insurance portal.
This is the primary tool for UIP-AI to get premium quotes.

READ_ONLY guarantee: This tool NEVER submits or issues policies.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.tools.base import ToolBase
from src.tools.models import ToolExecutionResult
from src.tools.quote.validator import QuoteValidator
from src.portal.quote_executor import QuoteExecutor, _parse_premium

logger = logging.getLogger("insuredesk.tools.quote.calculate")


class CalculateQuoteTool(ToolBase):
    """Calculate an insurance quote on a real portal.

    This tool is READ_ONLY — it never submits or issues policies.
    It navigates the portal, fills the quote form, clicks Calculate,
    and extracts the premium.

    Usage (via BridgeServer):
        POST /api/v1/execute
        {
            "tool": "calculate_quote",
            "arguments": {
                "portal": "great_eastern",
                "product": "IFE",
                "customer": {"name": "...", "ic": "..."},
                "risk": {"sum_insured": 100000}
            }
        }
    """

    name = "calculate_quote"
    description = (
        "Calculate an insurance premium quote. "
        "READ_ONLY — never submits or issues policies. "
        "Requires: portal, product, customer info, risk details."
    )

    def __init__(self, executor: Optional[QuoteExecutor] = None):
        self._executor = executor

    @property
    def executor(self) -> QuoteExecutor:
        """Get or create a QuoteExecutor."""
        if self._executor is None:
            self._executor = QuoteExecutor()
        return self._executor

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        """Execute a quote calculation.

        Args:
            arguments: Must contain 'portal' and 'product'.
                Optional: 'customer' dict, 'risk' dict.
            context: Optional context with 'form_engine' for browser access.

        Returns:
            ToolExecutionResult with quote result data.
        """
        # ── Validation Phase (Phase 4B) ──
        validator = QuoteValidator()
        validation = validator.validate(arguments)
        if not validation.valid:
            return ToolExecutionResult.fail(
                error=f"Quote validation failed: {validation.errors[0].message}",
                error_code="validation_error",
                error_context={
                    "validation": validation.to_dict(),
                },
            )

        portal = arguments.get("portal", "")
        product = arguments.get("product", "")

        # Provide FormEngine from context if available
        form_engine = None
        if context:
            form_engine = context.get("form_engine")

        executor = QuoteExecutor(form_engine)

        try:
            result: Dict[str, Any] = await executor.calculate(arguments)
        except Exception as e:
            logger.exception(f"Quote calculation failed: {e}")
            return ToolExecutionResult.fail(
                error=f"Quote calculation error: {e}",
                error_code="calculation_error",
            )

        if result.get("success"):
            return ToolExecutionResult.ok(data=result)
        else:
            return ToolExecutionResult.fail(
                error=result.get("error", "Quote failed"),
                error_code=result.get("error_code", "quote_error"),
            )
