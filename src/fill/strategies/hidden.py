"""InsureDesk — Fill Strategy: Hidden.

Skips hidden/calculated fields.
Useful for:
- Portal-calculated fields
- Session IDs embedded in the page
- Fields with server-side defaults
"""
from __future__ import annotations

from typing import Any

from src.fill.strategies.base import FillStrategy
from src.fill.schema import FieldDefinition


class HiddenStrategy(FillStrategy):
    """Strategy for hidden fields — skips them entirely.

    These fields are typically auto-populated by the portal
    or contain session/internal IDs. No browser interaction needed.
    """

    async def fill(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        # Hidden fields are skipped — no op
        return True
