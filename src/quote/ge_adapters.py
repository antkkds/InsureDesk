"""InsureDesk — Great Eastern Quote Adapters (IFE / EQ).

Concrete QuoteAdapter implementations for GEGLink's eQuotation systems.
- IFE: Fire & Engineering quotations
- EQ: General E-Quotations

These are launched from GEGLinkAdapter via launch_quote().
"""

from __future__ import annotations

from typing import Optional, Dict, Any
import asyncio

from src.browser.driver import BrowserEngine
from src.quote.base import QuoteAdapter
from src.portals.base import SessionMode, ReadOnlyViolationError
from src.quote.models import (
    QuoteRequest, QuoteResult, QuoteDraft,
    QuoteStatus, RiskClass,
)


# ══════════════════════════════════════════════════════════════════
# Base GE Quote Adapter
# ══════════════════════════════════════════════════════════════════

class GEQuoteAdapter(QuoteAdapter):
    """Base adapter for Great Eastern's eQuotation system.

    Shared logic between IFE and EQ quote channels.
    Both live behind the GEGLink Get Quote page iframe.
    """

    QUOTE_BASE_URL = "https://geglink.greateasterngeneral.com"
    QUOTE_IFRAME_SELECTOR = "iframe[src*='agent_home']"

    def __init__(self, engine: Optional[BrowserEngine] = None,
                 mode: SessionMode = SessionMode.READ_WRITE):
        super().__init__(engine)
        self._current_quote_number: str = ""
        self._form_data: dict = {}
        self._mode = mode

    async def _launch_from_iframe(self, channel_type: str) -> bool:
        """Navigate to the quote iframe and click the channel button.

        Flows through:
        1. Navigate to Get Quote page
        2. Wait for iframe to load
        3. Find channel form (IFE or EQ) via JS
        4. Submit the form
        """
        if not self._engine:
            return False

        engine = self._engine

        # Navigate to Get Quote page
        await engine.navigate(f"{self.QUOTE_BASE_URL}/oacportal/group/geglink/get-quote")
        await asyncio.sleep(3)

        # Use JS to find and submit the channel form in the iframe
        js = f"""
        (() => {{
            const iframe = document.querySelector('iframe[src*="agent_home"]');
            if (!iframe) return 'no iframe';
            try {{
                const doc = iframe.contentDocument || iframe.contentWindow.document;
                const forms = doc.querySelectorAll('form');
                for (const form of forms) {{
                    const ch = form.querySelector('input[name="channelType"]');
                    if (ch && ch.value === '{channel_type}') {{
                        form.submit();
                        return 'submitted ' + ch.value;
                    }}
                }}
                return 'channel not found: ' + channel_type;
            }} catch(e) {{
                return 'iframe error: ' + e.message;
            }}
        }})()
        """
        try:
            result = await engine.evaluate(js)
            await asyncio.sleep(3)
            return "submitted" in str(result)
        except Exception:
            return False

    async def health_check(self) -> Dict[str, Any]:
        base = await super().health_check()
        base["current_quote"] = self._current_quote_number or None
        base["mode"] = self._mode.value
        return base

    def _assert_write_permitted(self):
        """Raise ReadOnlyViolationError if in READ_ONLY mode."""
        if self._mode == SessionMode.READ_ONLY:
            raise ReadOnlyViolationError(
                f"Write operation denied: '{self.name}' is in READ_ONLY mode. "
                "Set mode=READ_WRITE to enable write operations."
            )


# ══════════════════════════════════════════════════════════════════
# IFE — Fire & Engineering Quote Adapter
# ══════════════════════════════════════════════════════════════════

class IFEQuoteAdapter(GEQuoteAdapter):
    """Quote adapter for Great Eastern's IFE (Fire & Engineering) system.

    Handles: Fire Insurance, Engineering Insurance quotations.
    """

    @property
    def name(self) -> str:
        return "ife_quote"

    @property
    def channel_type(self) -> str:
        return "IFE"

    async def create_quote(self, request: QuoteRequest) -> QuoteResult:
        if not self._engine:
            return QuoteResult(status=QuoteStatus.ERROR, errors=["No browser engine"])

        ok = await self._launch_from_iframe("IFE")
        if not ok:
            return QuoteResult(
                status=QuoteStatus.ERROR,
                errors=["Failed to launch IFE quote system"],
            )

        # Form filling would go here once we know the IFE form structure
        # await self._fill_fire_details(request)
        # await self._calculate()

        return QuoteResult(
            status=QuoteStatus.DRAFT,
            quote_number="",
            message="IFE quote system launched (form filling TBD)",
        )

    async def calculate(self, request: QuoteRequest) -> QuoteResult:
        self._assert_write_permitted()
        return QuoteResult(
            status=QuoteStatus.CALCULATED,
            message="Calculate TBD - needs IFE form exploration",
        )

    async def save_draft(self, quote_number: str) -> Optional[QuoteDraft]:
        self._assert_write_permitted()
        return QuoteDraft(
            draft_id="",
            quote_number=quote_number,
            channel_type="IFE",
            portal="great_eastern",
            status=QuoteStatus.SAVED,
        )

    async def submit(self, quote_number: str) -> QuoteResult:
        self._assert_write_permitted()
        return QuoteResult(
            status=QuoteStatus.SUBMITTED,
            quote_number=quote_number,
            message="Submit TBD - needs IFE form exploration",
        )


# ══════════════════════════════════════════════════════════════════
# EQ — E-Quotation Adapter
# ══════════════════════════════════════════════════════════════════

class EQQuoteAdapter(GEQuoteAdapter):
    """Quote adapter for Great Eastern's EQ (E-Quotation) system."""

    @property
    def name(self) -> str:
        return "eq_quote"

    @property
    def channel_type(self) -> str:
        return "EQ"

    async def create_quote(self, request: QuoteRequest) -> QuoteResult:
        if not self._engine:
            return QuoteResult(status=QuoteStatus.ERROR, errors=["No browser engine"])

        ok = await self._launch_from_iframe("EQ")
        if not ok:
            return QuoteResult(
                status=QuoteStatus.ERROR,
                errors=["Failed to launch EQ quote system"],
            )

        return QuoteResult(
            status=QuoteStatus.DRAFT,
            quote_number="",
            message="EQ quote system launched (form filling TBD)",
        )

    async def calculate(self, request: QuoteRequest) -> QuoteResult:
        self._assert_write_permitted()
        return QuoteResult(
            status=QuoteStatus.CALCULATED,
            message="Calculate TBD - needs EQ form exploration",
        )

    async def save_draft(self, quote_number: str) -> Optional[QuoteDraft]:
        self._assert_write_permitted()
        return QuoteDraft(
            draft_id="",
            quote_number=quote_number,
            channel_type="EQ",
            portal="great_eastern",
            status=QuoteStatus.SAVED,
        )

    async def submit(self, quote_number: str) -> QuoteResult:
        self._assert_write_permitted()
        return QuoteResult(
            status=QuoteStatus.SUBMITTED,
            quote_number=quote_number,
            message="Submit TBD - needs EQ form exploration",
        )
