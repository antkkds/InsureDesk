"""InsureDesk — Fill Strategy: ReadOnly.

Skips read-only / display-only fields.
These fields show data but should not be modified.
"""
from __future__ import annotations

from typing import Any

from src.fill.strategies.base import FillStrategy
from src.fill.schema import FieldDefinition


class ReadOnlyStrategy(FillStrategy):
    """Strategy for read-only/display fields — skips them.

    Read-only fields are treated as informational.
    The engine will verify the value matches if verify=True,
    but will never attempt to modify them.
    """

    async def fill(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        # Read-only fields are skipped — they cannot be modified
        # If verify=True, we could check the current value matches
        # but for now, skip silently
        return True
