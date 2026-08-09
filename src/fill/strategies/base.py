"""InsureDesk — Fill Strategy Base.

Abstract base for all fill strategies.
Each strategy knows how to fill ONE field type.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from src.fill.schema import FieldDefinition
from src.fill.verifier import Verifier
from src.fill.exceptions import (
    FieldNotFoundError,
    FillTimeoutError,
    FillVerificationError,
)


class FillStrategy(ABC):
    """Base class for field fill strategies.

    Each subclass implements fill() for one FieldType.
    """

    def __init__(self, verifier: Optional[Verifier] = None):
        self.verifier = verifier or Verifier()

    @abstractmethod
    async def fill(
        self,
        browser,  # BrowserEngine compatible object
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        """Fill a single field with the given value.

        Args:
            browser: BrowserEngine-like object with interaction methods.
            field: Field definition with selector, type, options.
            value: Value to fill.

        Returns:
            True if successful.

        Raises:
            FieldNotFoundError: If selector not found.
            FillTimeoutError: If fill times out.
            FillVerificationError: If verification fails.
        """
        ...

    async def _wait_for_selector(
        self,
        browser,
        selector: str,
        timeout: int = 10000,
    ) -> bool:
        """Wait for selector to appear on page."""
        try:
            return await browser.wait_for_selector(selector, timeout=timeout)
        except Exception:
            return False

    async def _default_verify(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        """Default verification: read value back and compare."""
        if not field.verify:
            return True

        try:
            return await self.verifier.verify(
                reader=lambda s: browser.get_value(s),
                selector=field.selector,
                expected=value,
                field_name=field.name,
                timeout=field.timeout,
            )
        except FillVerificationError:
            # Re-raise with more context
            raise FillVerificationError(
                message=f"Strategy verification failed for '{field.name}'",
                field=field.name,
                selector=field.selector,
            )
