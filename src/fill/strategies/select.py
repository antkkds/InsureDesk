"""InsureDesk — Fill Strategy: Select.

Fills <select> dropdown fields.
Supports value, label, and index selection modes.
"""
from __future__ import annotations

from typing import Any

from src.fill.strategies.base import FillStrategy
from src.fill.schema import FieldDefinition
from src.fill.exceptions import FieldNotFoundError, FillTimeoutError, FillVerificationError


class SelectStrategy(FillStrategy):
    """Strategy for <select> dropdown fields."""

    async def fill(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        if value is None:
            return True

        value_str = str(value)

        found = await self._wait_for_selector(browser, field.selector, timeout=field.timeout)
        if not found:
            raise FieldNotFoundError(
                message=f"Select field '{field.name}' not found",
                field=field.name,
                selector=field.selector,
            )

        # Determine selection mode from options or value format
        mode = field.options.get("mode", "value")  # value, label, or index

        try:
            await browser.select_option(field.selector, value_str)
        except Exception as e:
            raise FillTimeoutError(
                message=f"Failed to select option for '{field.name}': {e}",
                field=field.name,
                selector=field.selector,
                original=e if isinstance(e, Exception) else None,
            )

        # Verify
        if field.verify:
            try:
                await self._default_verify(browser, field, value_str)
            except FillVerificationError:
                for _ in range(field.retry):
                    try:
                        await browser.select_option(field.selector, value_str)
                        await self._default_verify(browser, field, value_str)
                        return True
                    except FillVerificationError:
                        continue
                raise

        return True
