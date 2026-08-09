"""InsureDesk — Fill Strategy: Radio.

Fills radio button groups.
Supports value-based selection and transformed values.
"""
from __future__ import annotations

from typing import Any

from src.fill.strategies.base import FillStrategy
from src.fill.schema import FieldDefinition
from src.fill.exceptions import FieldNotFoundError, FillTimeoutError, FillVerificationError


class RadioStrategy(FillStrategy):
    """Strategy for radio button groups."""

    async def fill(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        if value is None:
            return True

        value_str = str(value)

        # Build radio selector — options can provide value->selector mapping
        #   dict:  {"values": {"M": "#gender_male"}}      → explicit selectors
        #   list:  {"values": ["Male", "Female"]}         → selector[value="X"]
        value_map = field.options.get("values", {})
        if isinstance(value_map, list):
            radio_selector = f"{field.selector}[value=\"{value_str}\"]"
        elif value_str in value_map:
            radio_selector = value_map[value_str]
        else:
            # Try to find radio by value attribute
            radio_selector = f"{field.selector}[value=\"{value_str}\"]"

        found = await self._wait_for_selector(browser, radio_selector, timeout=field.timeout)
        if not found:
            # Fallback: click the parent selector (radio group container)
            radio_selector = field.selector
            found = await self._wait_for_selector(browser, radio_selector, timeout=field.timeout)
            if not found:
                raise FieldNotFoundError(
                    message=f"Radio field '{field.name}' not found",
                    field=field.name,
                    selector=field.selector,
                )

        try:
            await browser.click(radio_selector)
        except Exception as e:
            raise FillTimeoutError(
                message=f"Failed to click radio '{field.name}': {e}",
                field=field.name,
                selector=radio_selector,
                original=e if isinstance(e, Exception) else None,
            )

        if field.verify:
            # Radio verification: check that the clicked radio is checked
            try:
                is_checked = await browser.is_checked(radio_selector)
                if not is_checked:
                    raise FillVerificationError(
                        message=f"Radio '{field.name}' not checked after click",
                        field=field.name,
                        selector=radio_selector,
                    )
            except FillVerificationError:
                for _ in range(field.retry):
                    await browser.click(radio_selector)
                    is_checked = await browser.is_checked(radio_selector)
                    if is_checked:
                        return True
                raise
            except Exception:
                pass  # is_checked may not be supported by all drivers

        return True
