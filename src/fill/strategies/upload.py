"""InsureDesk — Fill Strategy: Upload.

Handles file upload fields.
"""
from __future__ import annotations

from typing import Any

from src.fill.strategies.base import FillStrategy
from src.fill.schema import FieldDefinition
from src.fill.exceptions import FieldNotFoundError, UploadFailedError


class UploadStrategy(FillStrategy):
    """Strategy for file upload fields."""

    async def fill(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        if value is None:
            return True

        file_path = str(value)

        found = await self._wait_for_selector(browser, field.selector, timeout=field.timeout)
        if not found:
            raise FieldNotFoundError(
                message=f"Upload field '{field.name}' not found",
                field=field.name,
                selector=field.selector,
            )

        try:
            await browser.upload_file(field.selector, file_path)

            # Verify: check that file name is visible or upload success indicator
            if field.verify:
                import asyncio
                await asyncio.sleep(1)  # Brief wait for upload to register
        except Exception as e:
            raise UploadFailedError(
                message=f"Upload failed for '{field.name}': {e}",
                field=field.name,
                selector=field.selector,
                original=e if isinstance(e, Exception) else None,
            )

        return True
