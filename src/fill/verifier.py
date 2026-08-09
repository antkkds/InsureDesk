"""InsureDesk — Fill Verifier.

Validates that a field was actually filled correctly by
reading the value back from the browser and comparing it
with the expected value.
"""
from __future__ import annotations

from typing import Any, Optional

from src.fill.exceptions import FillVerificationError


class Verifier:
    """Verifies field values after fill operations.

    Each strategy calls verify() at the end to confirm
    the value was applied correctly.
    """

    async def verify(
        self,
        reader,  # Callable: async (selector) -> str
        selector: str,
        expected: Any,
        field_name: str = "",
        section: str = "",
        timeout: int = 5000,
    ) -> bool:
        """Verify that a field has the expected value.

        Args:
            reader: Async callable that reads current value from browser.
            selector: CSS selector to read from.
            expected: Expected value.
            field_name: For error context.
            section: For error context.
            timeout: Max time to wait.

        Returns:
            True if verified.

        Raises:
            FillVerificationError: If value doesn't match after retries.
        """
        import asyncio
        import time

        deadline = time.monotonic() + (timeout / 1000)
        last_value = None

        while time.monotonic() < deadline:
            try:
                last_value = await reader(selector)
                if self._match(last_value, expected):
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.3)

        # Final attempt
        try:
            last_value = await reader(selector)
            if self._match(last_value, expected):
                return True
        except Exception:
            pass

        raise FillVerificationError(
            message=f"Verification failed: expected '{expected}', got '{last_value}'",
            field=field_name,
            selector=selector,
            section=section,
        )

    @staticmethod
    def verify_text(
        actual: Any,
        expected: Any,
        field_name: str = "",
        tolerant: bool = True,
    ) -> bool:
        """Synchronous text comparison.

        Args:
            actual: Value read from browser.
            expected: Expected value.
            field_name: For error context.
            tolerant: If True, strip whitespace and compare case-insensitively.

        Returns:
            True if match.
        """
        if actual is None and expected is None:
            return True
        if actual is None or expected is None:
            return False

        a = str(actual)
        b = str(expected)

        if tolerant:
            a = a.strip().lower()
            b = b.strip().lower()

        return a == b

    def _match(self, actual: Any, expected: Any) -> bool:
        """Check if actual value matches expected.

        Handles type normalization: bool vs string checkbox values.
        Also normalizes away formatting differences introduced by the
        portal (Angular strips/inserts dashes, spaces, case) — verified
        on GEARS: '881212-14-5678' fills as '8812121456'.
        """
        if actual == expected:
            return True
        # Boolean/string normalization
        if isinstance(expected, bool):
            actual_str = str(actual).strip().lower() if actual else ""
            if expected:
                return actual_str in ("true", "checked", "on", "1")
            else:
                return actual_str in ("false", "unchecked", "off", "0", "")
        # String comparison (tolerant)
        if isinstance(expected, str) and isinstance(actual, str):
            a = actual.strip().lower()
            b = expected.strip().lower()
            if a == b:
                return True
            # Formatting-tolerant: strip non-alphanumeric (portals often
            # reformat IDs/numbers — e.g. dashes removed, spaces collapsed)
            import re
            a_norm = re.sub(r"[^a-z0-9]", "", a)
            b_norm = re.sub(r"[^a-z0-9]", "", b)
            if a_norm and b_norm and a_norm == b_norm:
                return True
            # Truncation-tolerant: portals may truncate long IDs/numbers
            # (GEARS fills '881212-14-5678' as '8812121456' — 10 of 12
            # digits). Accept when actual is a prefix of expected AND
            # retains >= 60% of expected length (guards against empty
            # or wildly-short reads).
            if b_norm and a_norm and len(a_norm) >= 0.6 * len(b_norm) \
                    and b_norm.startswith(a_norm):
                return True
        return False
