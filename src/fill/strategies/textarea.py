"""InsureDesk — Fill Strategy: TextArea.

Fills multiline textarea fields.
Same as TextStrategy but targets <textarea> elements.
"""
from __future__ import annotations

from typing import Any

from src.fill.strategies.base import FillStrategy
from src.fill.schema import FieldDefinition
from src.fill.exceptions import FieldNotFoundError, FillTimeoutError, FillVerificationError


class TextAreaStrategy(FillStrategy):
    """Strategy for <textarea> multiline fields."""

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
                message=f"Textarea field '{field.name}' not found",
                field=field.name,
                selector=field.selector,
            )

        try:
            await browser.click(field.selector)

            if field.clear_first:
                try:
                    await browser.fill(field.selector, "")
                except Exception:
                    pass

            await browser.fill(field.selector, value_str)
        except Exception as e:
            raise FillTimeoutError(
                message=f"Failed to fill textarea '{field.name}': {e}",
                field=field.name,
                selector=field.selector,
                original=e if isinstance(e, Exception) else None,
            )

        if field.verify:
            try:
                await self._default_verify(browser, field, value_str)
            except FillVerificationError:
                for _ in range(field.retry):
                    try:
                        await browser.fill(field.selector, value_str)
                        await self._default_verify(browser, field, value_str)
                        return True
                    except FillVerificationError:
                        continue
                raise

        return True
