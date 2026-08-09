"""InsureDesk — Fill Strategy: Date.

Fills date input fields with proper formatting.
"""
from __future__ import annotations

from typing import Any
from datetime import date, datetime

from src.fill.strategies.base import FillStrategy
from src.fill.schema import FieldDefinition
from src.fill.exceptions import FieldNotFoundError, FillTimeoutError


class DateStrategy(FillStrategy):
    """Strategy for date input fields."""

    async def fill(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        if value is None:
            return True

        # Format the date value
        date_str = self._format_date(value, field.format or "%d/%m/%Y")

        found = await self._wait_for_selector(browser, field.selector, timeout=field.timeout)
        if not found:
            raise FieldNotFoundError(
                message=f"Date field '{field.name}' not found",
                field=field.name,
                selector=field.selector,
            )

        # Check if native date picker (type="date" expects YYYY-MM-DD)
        native_format = date_str
        if field.options.get("native", False):
            native_format = self._format_date(value, "%Y-%m-%d")

        try:
            # Click to focus
            await browser.click(field.selector)

            # Clear first if configured
            if field.clear_first:
                try:
                    await browser.fill(field.selector, "")
                except Exception:
                    pass

            await browser.fill(field.selector, native_format)
        except Exception as e:
            raise FillTimeoutError(
                message=f"Failed to fill date field '{field.name}': {e}",
                field=field.name,
                selector=field.selector,
                original=e if isinstance(e, Exception) else None,
            )

        # Verify
        if field.verify:
            await self._default_verify(browser, field, native_format)

        return True

    def _format_date(self, value: Any, fmt: str) -> str:
        """Format a date value into a string."""
        if isinstance(value, str):
            # Try to parse common formats
            for parse_fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    dt = datetime.strptime(value, parse_fmt)
                    return dt.strftime(fmt)
                except ValueError:
                    continue
            return value  # Return as-is if can't parse
        if isinstance(value, (date, datetime)):
            return value.strftime(fmt)
        return str(value)
