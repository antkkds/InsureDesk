"""InsureDesk — Fill Strategy: Text.

Fills text input fields.
"""
from __future__ import annotations

from typing import Any, Optional

from src.fill.strategies.base import FillStrategy
from src.fill.schema import FieldDefinition
from src.fill.exceptions import FillTimeoutError, FillVerificationError


class TextStrategy(FillStrategy):
    """Strategy for <input type="text"> fields."""

    async def fill(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        if value is None:
            return True  # Nothing to fill

        value_str = str(value)

        # Apply max_length
        if field.max_length and len(value_str) > field.max_length:
            value_str = value_str[:field.max_length]

        # Wait for element
        found = await self._wait_for_selector(
            browser, field.selector, timeout=field.timeout
        )
        if not found:
            from src.fill.exceptions import FieldNotFoundError
            raise FieldNotFoundError(
                message=f"Text field '{field.name}' not found",
                field=field.name,
                selector=field.selector,
            )

        try:
            # Click to focus
            await browser.click(field.selector)

            # Clear existing content
            if field.clear_first:
                try:
                    await browser.fill(field.selector, "")
                except Exception:
                    pass

            # Type the value
            await browser.fill(field.selector, value_str)
        except Exception as e:
            raise FillTimeoutError(
                message=f"Failed to fill text field '{field.name}': {e}",
                field=field.name,
                selector=field.selector,
                original=e if isinstance(e, Exception) else None,
            )

        # Verify
        if field.verify:
            try:
                await self._default_verify(browser, field, value_str)
            except FillVerificationError:
                # Retry once
                for _ in range(field.retry):
                    try:
                        await browser.fill(field.selector, value_str)
                        await self._default_verify(browser, field, value_str)
                        return True
                    except FillVerificationError:
                        continue
                raise

        return True
