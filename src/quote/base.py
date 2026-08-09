"""InsureDesk — Quote Adapter Base.

Abstract base for all insurance quote engines.
Concrete implementations handle portal-specific quote flows.

Flow:
    PortalAdapter (e.g. GEGLinkAdapter)
        ↓ launch_quote()
    QuoteAdapter
        ↓ create_quote() → calculate() → save_draft() → submit()
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod

from src.browser.driver import BrowserEngine
from src.quote.models import QuoteRequest, QuoteResult, QuoteDraft, QuoteStatus


class QuoteAdapter(ABC):
    """Base class for insurance quote engine adapters.

    Each portal's quote system (IFE, EQ, etc.) implements this.
    PortalAdapter launches the quote system, QuoteAdapter handles the rest.

    Args:
        engine: BrowserEngine instance (shared from PortalAdapter)
    """

    def __init__(self, engine: Optional[BrowserEngine] = None):
        self._engine = engine

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter name, e.g. 'ife_quote', 'eq_quote'."""
        ...

    @property
    @abstractmethod
    def channel_type(self) -> str:
        """Channel type code, e.g. 'IFE', 'EQ'."""
        ...

    def set_engine(self, engine: BrowserEngine):
        """Set or update the browser engine reference."""
        self._engine = engine

    @abstractmethod
    async def create_quote(self, request: QuoteRequest) -> QuoteResult:
        """Create a new quotation.

        Navigates to the quote form, fills in details,
        and returns the quote result.

        Args:
            request: Quote request details.

        Returns:
            QuoteResult with calculated premium.
        """
        ...

    @abstractmethod
    async def calculate(self, request: QuoteRequest) -> QuoteResult:
        """Calculate premium for a quote request.

        May be called after create_quote() to recalculate
        with modified parameters.

        Args:
            request: Quote request details.

        Returns:
            QuoteResult with calculated premiums.
        """
        ...

    @abstractmethod
    async def save_draft(self, quote_number: str) -> Optional[QuoteDraft]:
        """Save the current quote as a draft.

        Args:
            quote_number: Quote number from a previous create_quote().

        Returns:
            QuoteDraft reference if saved successfully.
        """
        ...

    @abstractmethod
    async def submit(self, quote_number: str) -> QuoteResult:
        """Submit the quote for processing.

        Args:
            quote_number: Quote number to submit.

        Returns:
            Final QuoteResult after submission.
        """
        ...

    async def health_check(self) -> Dict[str, Any]:
        """Check if the quote system is accessible.

        Returns:
            Dict with status info.
        """
        return {
            "adapter": self.name,
            "channel_type": self.channel_type,
            "status": "unknown",
            "engine_connected": self._engine is not None,
        }
