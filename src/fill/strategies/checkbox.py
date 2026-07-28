"""InsureDesk — Fill Strategy: Checkbox.

Fills checkbox fields. Reads current state first,
then only clicks if the desired state differs.
"""
from __future__ import annotations

from typing import Any

from src.fill.strategies.base import FillStrategy
from src.fill.schema import FieldDefinition
from src.fill.exceptions import FieldNotFoundError, FillTimeoutError, FillVerificationError


class CheckboxStrategy(FillStrategy):
    """Strategy for checkbox fields.

    Never blindly clicks — reads current state first.
    """

    async def fill(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        if value is None:
            return True

        desired = self._bool_value(value)

        found = await self._wait_for_selector(browser, field.selector, timeout=field.timeout)
        if not found:
            raise FieldNotFoundError(
                message=f"Checkbox '{field.name}' not found",
                field=field.name,
                selector=field.selector,
            )

        # Read current state
        try:
            is_checked = await browser.is_checked(field.selector)
        except Exception:
            # Fallback: check if it has 'checked' attribute
            is_checked = await browser.get_value(field.selector) == "true"

        if is_checked == desired:
            return True  # Already in correct state

        try:
            await browser.click(field.selector)
        except Exception as e:
            raise FillTimeoutError(
                message=f"Failed to click checkbox '{field.name}': {e}",
                field=field.name,
                selector=field.selector,
                original=e if isinstance(e, Exception) else None,
            )

        if field.verify:
            try:
                verified = await browser.is_checked(field.selector)
                if verified != desired:
                    raise FillVerificationError(
                        message=f"Checkbox '{field.name}' not in expected state",
                        field=field.name,
                        selector=field.selector,
                    )
            except FillVerificationError:
                for _ in range(field.retry):
                    await browser.click(field.selector)
                    verified = await browser.is_checked(field.selector)
                    if verified == desired:
                        return True
                raise

        return True

    def _bool_value(self, value: Any) -> bool:
        """Convert various truthy values to boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1", "checked", "on")
        return bool(value)
