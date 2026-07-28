"""InsureDesk — Fill Strategy: Lookup.

Fills lookup/search dialog fields common in insurance portals.
Pattern: click search → wait popup → search → select → wait close → verify
"""
from __future__ import annotations

from typing import Any

from src.fill.strategies.base import FillStrategy
from src.fill.schema import FieldDefinition
from src.fill.exceptions import FieldNotFoundError, FillTimeoutError


class LookupStrategy(FillStrategy):
    """Strategy for lookup/search dialog fields."""

    async def fill(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        if value is None:
            return True

        value_str = str(value)

        # Get child selectors from options
        search_btn_sel = field.options.get("search_button", field.selector)
        search_input_sel = field.options.get("search_input", "")
        result_sel = field.options.get("result_item", "")
        confirm_sel = field.options.get("confirm_button", "")

        found = await self._wait_for_selector(browser, search_btn_sel, timeout=field.timeout)
        if not found:
            raise FieldNotFoundError(
                message=f"Lookup field '{field.name}' search button not found",
                field=field.name,
                selector=search_btn_sel,
            )

        try:
            # Click search button to open lookup dialog
            await browser.click(search_btn_sel)

            # Wait for dialog/popup
            await browser.wait_for_selector(
                search_input_sel or result_sel,
                timeout=field.timeout,
            )

            # Type search value if search input is specified
            if search_input_sel:
                await browser.fill(search_input_sel, value_str)
                # Wait briefly for results
                import asyncio
                await asyncio.sleep(0.5)

            # Click the result item
            if result_sel:
                await browser.click(result_sel)

            # Click confirm button if specified
            if confirm_sel:
                await browser.click(confirm_sel)

        except Exception as e:
            raise FillTimeoutError(
                message=f"Lookup operation failed for '{field.name}': {e}",
                field=field.name,
                selector=search_btn_sel,
                original=e if isinstance(e, Exception) else None,
            )

        return True
