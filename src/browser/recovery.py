"""InsureDesk — Session Recovery Manager.

Provides auto-recovery for browser sessions that have expired or encountered
transient errors. Wraps BrowserFoundation to add execute_with_recovery().

Recovery Pipeline:
    Action → Exception
      ↓
    RecoveryManager.execute_with_recovery()
      ↓
    1. identify_current_page()
    2. Need Login? → login()
    3. PDPA? → accept_pdpa()
    4. Modal/Overlay? → dismiss()
    5. Retry original action
      ↓
    Success or RecoveryFailed

Usage:
    recovery = RecoveryManager(browser, portal_adapter)
    await recovery.execute_with_recovery(
        action=lambda: browser.safe_click("#search"),
        page_check=lambda url: "login" not in url,
    )
"""

from __future__ import annotations

from typing import Optional, Callable, Awaitable, TypeVar, Any
import asyncio
import logging

from src.browser.foundation import (
    BrowserFoundation,
    SessionExpired,
    RecoveryFailed,
    VerificationFailed,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RecoveryManager:
    """Auto-recovery for browser sessions.

    Wraps a BrowserFoundation + adapter's page detection logic.
    On failure, runs recovery pipeline before giving up.

    Args:
        browser: BrowserFoundation instance
        is_logged_in: Callable that returns True if session is valid
        relogin: Callable that performs re-login (async)
        accept_pdpa: Optional callable for PDPA terms
    """

    def __init__(
        self,
        browser: BrowserFoundation,
        is_logged_in: Callable[[], Awaitable[bool]],
        relogin: Optional[Callable[[], Awaitable[bool]]] = None,
        accept_pdpa: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        self._browser = browser
        self._is_logged_in = is_logged_in
        self._relogin = relogin
        self._accept_pdpa = accept_pdpa
        self._stats: dict[str, int] = {
            "recoveries": 0,
            "relogins": 0,
            "pdpa_accepted": 0,
            "overlays_dismissed": 0,
            "failed": 0,
        }

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    @property
    def browser(self) -> BrowserFoundation:
        return self._browser

    async def execute_with_recovery(
        self,
        action: Callable[[], Awaitable[T]],
        max_recoveries: int = 2,
        page_check: Optional[Callable[[], Awaitable[bool]]] = None,
    ) -> T:
        """Execute an action with automatic session recovery.

        Pipeline:
            1. Try action
            2. On failure → check session
            3. If expired → relogin
            4. Check PDPA → accept
            5. Check overlays → dismiss
            6. Retry action

        Args:
            action: The async action to execute.
            max_recoveries: Max recovery attempts before raising.
            page_check: Optional function to verify page state after recovery.

        Returns:
            The action's return value.

        Raises:
            RecoveryFailed: Recovery exhausted or impossible.
            Original exception: If recovery is not applicable.
        """
        for attempt in range(max_recoveries + 1):
            try:
                return await action()
            except Exception as e:
                if attempt >= max_recoveries:
                    self._stats["failed"] += 1
                    raise RecoveryFailed(
                        f"Action failed after {max_recoveries} recovery attempts",
                        context={
                            "error": str(e)[:200],
                            "attempts": max_recoveries,
                            "recoveries": self._stats["recoveries"],
                        },
                    ) from e

                logger.info(
                    "Recovery attempt %d/%d: %s",
                    attempt + 1, max_recoveries, str(e)[:100],
                )

                # Phase 1: Check login state
                if not await self._is_logged_in():
                    self._stats["recoveries"] += 1
                    if self._relogin:
                        logger.info("Session expired — re-logging in...")
                        ok = await self._relogin()
                        if not ok:
                            raise RecoveryFailed("Re-login failed")
                        self._stats["relogins"] += 1
                        await asyncio.sleep(1)
                    else:
                        raise SessionExpired(
                            "Session expired and no relogin handler provided"
                        )

                # Phase 2: Check PDPA
                if self._accept_pdpa:
                    try:
                        current_url = await self._browser.get_url()
                        if "pdpa" in current_url.lower() or "terms" in current_url.lower():
                            await self._accept_pdpa()
                            self._stats["pdpa_accepted"] += 1
                            await asyncio.sleep(1)
                    except Exception:
                        pass

                # Phase 3: Dismiss overlays
                try:
                    dismissed = await self._browser.dismiss_overlay()
                    if dismissed:
                        self._stats["overlays_dismissed"] += 1
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                # Phase 4: Verify page state
                if page_check:
                    try:
                        ok = await page_check()
                        if not ok:
                            logger.warning("Page check failed after recovery")
                    except Exception:
                        pass

                # Continue loop → retry action

        # Should not reach here
        raise RecoveryFailed("Recovery exhausted (unexpected exit)")

    async def safe_execute(
        self,
        action: Callable[[], Awaitable[T]],
        max_recoveries: int = 2,
        page_check: Optional[Callable[[], Awaitable[bool]]] = None,
    ) -> Optional[T]:
        """Safe version of execute_with_recovery that returns None on failure.

        Usage:
            result = await recovery.safe_execute(
                action=lambda: browser.safe_click("#btn"),
            )
            if result is None:
                # Handle failure gracefully
        """
        try:
            return await self.execute_with_recovery(
                action=action,
                max_recoveries=max_recoveries,
                page_check=page_check,
            )
        except RecoveryFailed:
            return None
        except Exception as e:
            logger.error("Unhandled error in safe_execute: %s", e)
            return None
