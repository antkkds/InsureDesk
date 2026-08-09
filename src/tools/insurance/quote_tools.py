"""InsureDesk — Quote Tools.

LLM-callable tools that wrap MockQuoteAdapter (and eventually real PortalQuoteAdapter).
Each tool exposes one quote operation as a typed, documented function.

Available tools:
- list_products: Show available product codes
- create_quote: Create a new quotation
- calculate_quote: Calculate premium for a quote request
- compare_quotes: Compare premiums across multiple risk classes
- save_draft_quote: Save a quote as draft
- get_quote_status: Check status of a quote
"""

from __future__ import annotations

from typing import Optional, List as TypingList

from src.tools.base import ToolBase
from src.tools.models import ToolExecutionResult
from src.quote.mock import MockQuoteAdapter
from src.quote.models import QuoteRequest, QuoteItem
from src.portals.base import SessionMode


# ══════════════════════════════════════════════════════════════════
# Shared adapter instance (singleton per session)
# ══════════════════════════════════════════════════════════════════

_SHARED_ADAPTER: Optional[MockQuoteAdapter] = None


def _get_adapter(mode: str = "read_write") -> MockQuoteAdapter:
    """Get or create the shared MockQuoteAdapter instance.

    Using a shared adapter ensures quote numbers increment
    sequentially and drafts persist across tool calls.
    """
    global _SHARED_ADAPTER
    session_mode = SessionMode.READ_WRITE if mode == "read_write" else SessionMode.READ_ONLY

    if _SHARED_ADAPTER is None:
        _SHARED_ADAPTER = MockQuoteAdapter(mode=session_mode)
        _SHARED_ADAPTER.reset()

    return _SHARED_ADAPTER


def reset_shared_adapter():
    """Reset the shared adapter (for testing)."""
    global _SHARED_ADAPTER
    _SHARED_ADAPTER = None


# ══════════════════════════════════════════════════════════════════
# Tool: list_products
# ══════════════════════════════════════════════════════════════════

class ListProducts(ToolBase):
    """List available insurance product codes."""

    @property
    def name(self) -> str:
        return "list_products"

    @property
    def description(self) -> str:
        return "List all available insurance product codes (e.g. FIRE, MOTOR, PA)."

    async def execute(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolExecutionResult:
        adapter = _get_adapter()
        products = adapter.config.product_codes
        multipliers = adapter.config.risk_multipliers
        return ToolExecutionResult.ok(            data={
                "products": [
                    {
                        "code": code,
                        "risk_multiplier": multipliers.get(code.lower().replace(" ", "_"), 2.0),
                    }
                    for code in products
                ],
                "count": len(products),
                "base_premium": adapter.config.base_premium,
            },
        )


# ══════════════════════════════════════════════════════════════════
# Tool: create_quote
# ══════════════════════════════════════════════════════════════════

class CreateQuote(ToolBase):
    """Create a new insurance quotation."""

    @property
    def name(self) -> str:
        return "create_quote"

    @property
    def description(self) -> str:
        return (
            "Create a new insurance quotation. "
            "Provide proposer details, risk class, and items to insure. "
            "Returns a quote number and initial draft status."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "proposer_name": {
                    "type": "string",
                    "description": "Full name of the policy proposer.",
                },
                "risk_class": {
                    "type": "string",
                    "description": "Risk class (e.g. fire, motor, medical, travel).",
                    "enum": ["fire", "engineering", "motor", "marine",
                             "personal_accident", "medical", "travel", "liability"],
                },
                "sum_insured": {
                    "type": "number",
                    "description": "Total sum insured amount in MYR.",
                },
                "item_description": {
                    "type": "string",
                    "description": "Description of the item/asset being insured.",
                    "default": "",
                },
                "proposer_ic": {
                    "type": "string",
                    "description": "IC/Passport number of proposer.",
                    "default": "",
                },
                "proposer_email": {
                    "type": "string",
                    "description": "Email address of proposer.",
                    "default": "",
                },
            },
            "required": ["proposer_name", "risk_class", "sum_insured"],
        }

    async def execute(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolExecutionResult:
        adapter = _get_adapter()

        request = QuoteRequest(
            portal="mock",
            adapter="mock_quote",
            channel_type="MOCK",
            proposer_name=arguments.get("proposer_name", ""),
            proposer_ic=arguments.get("proposer_ic", ""),
            proposer_email=arguments.get("proposer_email", ""),
            risk_class=arguments.get("risk_class", "fire"),
            items=[
                QuoteItem(
                    description=arguments.get("item_description", f"{arguments.get('risk_class', 'risk')} insurance"),
                    sum_insured=arguments.get("sum_insured", 100000),
                    risk_class=arguments.get("risk_class", "fire"),
                )
            ],
        )

        result = await adapter.create_quote(request)
        return ToolExecutionResult.ok(            data={
                "quote_number": result.quote_number,
                "status": result.status.value,
                "proposer_name": request.proposer_name,
                "risk_class": request.risk_class,
                "sum_insured": request.items[0].sum_insured if request.items else 0,
            },
        )


# ══════════════════════════════════════════════════════════════════
# Tool: calculate_quote
# ══════════════════════════════════════════════════════════════════

class CalculateQuote(ToolBase):
    """Calculate premium for an insurance quotation."""

    @property
    def name(self) -> str:
        return "calculate_quote"

    @property
    def description(self) -> str:
        return (
            "Calculate the premium for a quotation. "
            "Must be called after create_quote. "
            "Returns gross premium, taxes, stamp duty, and total premium."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "proposer_name": {
                    "type": "string",
                    "description": "Full name of the policy proposer.",
                },
                "risk_class": {
                    "type": "string",
                    "description": "Risk class.",
                    "enum": ["fire", "engineering", "motor", "marine",
                             "personal_accident", "medical", "travel", "liability"],
                },
                "sum_insured": {
                    "type": "number",
                    "description": "Sum insured amount in MYR.",
                },
                "item_description": {
                    "type": "string",
                    "description": "Description of the item being insured.",
                    "default": "",
                },
            },
            "required": ["proposer_name", "risk_class", "sum_insured"],
        }

    async def execute(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolExecutionResult:
        adapter = _get_adapter()

        request = QuoteRequest(
            portal="mock",
            adapter="mock_quote",
            channel_type="MOCK",
            proposer_name=arguments.get("proposer_name", ""),
            risk_class=arguments.get("risk_class", "fire"),
            items=[
                QuoteItem(
                    description=arguments.get("item_description", f"{arguments.get('risk_class', 'risk')} insurance"),
                    sum_insured=arguments.get("sum_insured", 100000),
                    risk_class=arguments.get("risk_class", "fire"),
                )
            ],
        )

        result = await adapter.calculate(request)
        return ToolExecutionResult.ok(            data={
                "quote_number": result.quote_number,
                "status": result.status.value,
                "gross_premium": result.gross_premium,
                "net_premium": result.net_premium,
                "tax_amount": result.tax_amount,
                "stamp_duty": result.stamp_duty,
                "total_premium": result.total_premium,
                "breakdown": result.breakdown,
                "message": result.message,
            },
        )


# ══════════════════════════════════════════════════════════════════
# Tool: compare_quotes
# ══════════════════════════════════════════════════════════════════

class CompareQuotes(ToolBase):
    """Compare insurance premiums across multiple risk classes."""

    @property
    def name(self) -> str:
        return "compare_quotes"

    @property
    def description(self) -> str:
        return (
            "Compare insurance premiums for the same sum insured across "
            "multiple risk classes. Returns side-by-side comparison."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "proposer_name": {
                    "type": "string",
                    "description": "Proposer name for the comparison.",
                },
                "sum_insured": {
                    "type": "number",
                    "description": "Sum insured amount in MYR.",
                },
                "risk_classes": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["fire", "engineering", "motor", "marine",
                                 "personal_accident", "medical", "travel", "liability"],
                    },
                    "description": "List of risk classes to compare (default: all products).",
                },
            },
            "required": ["proposer_name", "sum_insured"],
        }

    async def execute(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolExecutionResult:
        adapter = _get_adapter()
        risk_classes = arguments.get("risk_classes") or [
            "fire", "engineering", "motor", "personal_accident", "travel"
        ]

        comparisons = []
        for rc in risk_classes:
            request = QuoteRequest(
                portal="mock",
                adapter="mock_quote",
                channel_type="MOCK",
                proposer_name=arguments.get("proposer_name", "Test"),
                risk_class=rc,
                items=[
                    QuoteItem(
                        description=f"{rc} insurance",
                        sum_insured=arguments.get("sum_insured", 100000),
                        risk_class=rc,
                    )
                ],
            )
            result = await adapter.calculate(request)
            comparisons.append({
                "risk_class": rc,
                "total_premium": result.total_premium,
                "gross_premium": result.gross_premium,
                "net_premium": result.net_premium,
                "quote_number": result.quote_number,
                "status": result.status.value,
            })

        # Sort by total premium ascending
        comparisons.sort(key=lambda x: x["total_premium"])

        return ToolExecutionResult.ok(            data={
                "comparisons": comparisons,
                "count": len(comparisons),
                "lowest_premium": comparisons[0] if comparisons else None,
                "highest_premium": comparisons[-1] if comparisons else None,
            },
        )


# ══════════════════════════════════════════════════════════════════
# Tool: save_draft_quote
# ══════════════════════════════════════════════════════════════════

class SaveDraftQuote(ToolBase):
    """Save a quote as draft."""

    @property
    def name(self) -> str:
        return "save_draft_quote"

    @property
    def description(self) -> str:
        return "Save an existing quote as a draft for later retrieval."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "quote_number": {
                    "type": "string",
                    "description": "Quote number to save as draft.",
                },
            },
            "required": ["quote_number"],
        }

    async def execute(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolExecutionResult:
        adapter = _get_adapter()
        quote_number = arguments.get("quote_number", "")
        result = await adapter.save_draft(quote_number)

        if result is None:
            return ToolExecutionResult.fail(error=f"Quote '{quote_number}' not found or could not be saved.",
            )

        return ToolExecutionResult.ok(            data={
                "quote_number": result.quote_number,
                "status": result.status.value,
                "created_at": result.created_at.isoformat() if hasattr(result, "created_at") else "",
                "data": result.data,
            },
        )


# ══════════════════════════════════════════════════════════════════
# Tool: get_quote_status
# ══════════════════════════════════════════════════════════════════

class GetQuoteStatus(ToolBase):
    """Check the status of a quote."""

    @property
    def name(self) -> str:
        return "get_quote_status"

    @property
    def description(self) -> str:
        return "Get the current status and details of a quote by quote number."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "quote_number": {
                    "type": "string",
                    "description": "Quote number to look up.",
                },
            },
            "required": ["quote_number"],
        }

    async def execute(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolExecutionResult:
        adapter = _get_adapter()
        quote_number = arguments.get("quote_number", "")

        # Check drafts first
        draft = adapter._drafts.get(quote_number)
        if draft:
            return ToolExecutionResult.ok(                data={
                    "quote_number": draft.quote_number,
                    "status": draft.status.value,
                    "created_at": draft.created_at.isoformat() if hasattr(draft, "created_at") else "",
                },
            )

        # Check active quote
        if adapter._active_quote and adapter._active_quote.get("quote_number") == quote_number:
            return ToolExecutionResult.ok(                data={
                    "quote_number": quote_number,
                    "status": "active",
                },
            )

        return ToolExecutionResult.ok(            data={
                "quote_number": quote_number,
                "status": "not_found",
            },
        )


# ══════════════════════════════════════════════════════════════════
# Registration helper
# ══════════════════════════════════════════════════════════════════

def register_all_quote_tools(registry):
    """Register all quote tools in the given registry.

    Args:
        registry: ToolRegistry instance.
    """
    tools = [
        ListProducts(),
        CreateQuote(),
        CalculateQuote(),
        CompareQuotes(),
        SaveDraftQuote(),
        GetQuoteStatus(),
    ]
    registry.register_all(tools)
    return tools
