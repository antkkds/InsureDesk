"""InsureDesk — Fill Strategy: Angular Material Autocomplete.

Handles GEARS-style mat-autocomplete fields:
    #condition (NEW REGISTERED / USED), #idType (NRIC/Passport), #place (state)

Interaction (verified against live GEARS 2026-08):
    1. Some fields start disabled (Angular binds disabled on the input
       itself) → removeAttribute('disabled') first
    2. focus the input → type the value (triggers mat-option filtering)
    3. wait for mat-option to appear
    4. click the matching option with a NATIVE click
       (JS el.click() does NOT update the Angular model — verified)
    5. read-back verify: the input value must equal the chosen label

Registered via FillEngine.register_strategy() — this is an ACTION-LAYER
concern, deliberately NOT part of PortalDriver protocol (ChatGPT review:
keep retry/verification/fallback out of driver primitives).
"""
from __future__ import annotations

from typing import Any

from src.fill.strategies.base import FillStrategy
from src.fill.schema import FieldDefinition
from src.fill.exceptions import (
    FieldNotFoundError,
    FillTimeoutError,
    FillVerificationError,
)


class AutocompleteStrategy(FillStrategy):
    """Fill an Angular Material autocomplete field.

    Options:
        autocomplete: true                  (required to trigger this strategy)
        autocomplete_option: "mat-option"   (selector for option panel items)
        match_mode: "contains" | "exact"    (default contains)
    """

    async def fill(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> bool:
        if value is None:
            return True

        value_str = str(value).strip()
        if not value_str:
            return True

        # 1. Enable if disabled
        if field.options.get("force_enable"):
            await self._enable_input(browser, field)

        # 2. Focus + type
        try:
            await browser.click(field.selector)
        except Exception as e:
            raise FillTimeoutError(
                message=f"Failed to focus autocomplete '{field.name}': {e}",
                field=field.name,
                selector=field.selector,
            )

        try:
            await browser.fill(field.selector, value_str)
        except Exception as e:
            raise FillTimeoutError(
                message=f"Failed to type autocomplete '{field.name}': {e}",
                field=field.name,
                selector=field.selector,
            )

        # 3. Wait for mat-option panel
        option_sel = field.options.get("autocomplete_option", "mat-option")
        found = await self._wait_for_selector(browser, option_sel, timeout=field.timeout)
        if not found:
            raise FieldNotFoundError(
                message=f"Autocomplete '{field.name}': no '{option_sel}' appeared after typing",
                field=field.name,
                selector=field.selector,
            )

        # 4. Native click the matching option (JS click does NOT update Angular)
        await self._click_option(browser, field, option_sel, value_str)

        # 5. Read-back verification
        if field.verify:
            await self._verify(browser, field, value_str)

        return True

    # -- helpers -------------------------------------------------------

    async def _enable_input(self, browser, field: FieldDefinition) -> None:
        """Remove disabled attribute via JS (Angular binds it on the input)."""
        try:
            sel = field.selector.lstrip("#")
            await browser.evaluate(
                f"""(() => {{
                    const el = document.getElementById('{sel}');
                    if (el) el.removeAttribute('disabled');
                    return true;
                }})()"""
            )
        except Exception as e:
            raise FillTimeoutError(
                message=f"Failed to enable autocomplete '{field.name}': {e}",
                field=field.name,
                selector=field.selector,
            )

    async def _click_option(
        self,
        browser,
        field: FieldDefinition,
        option_sel: str,
        value_str: str,
    ) -> None:
        """Native-click the mat-option whose text matches the value.

        ⚠️ MUST use Playwright native click (browser.click with a text
        selector). JS el.click() does NOT update the Angular model —
        verified against live GEARS (skill: geglink-portal-login).
        """
        match_mode = field.options.get("match_mode", "contains")
        # Enumerate options to confirm a match exists (selector inlined —
        # BrowserEngine.evaluate takes a single script argument)
        try:
            options_info = await browser.evaluate(
                f"""(() => {{
                    const opts = Array.from(document.querySelectorAll('{option_sel}'));
                    return opts.map((o, i) => ({{i, text: (o.innerText || '').trim()}}));
                }})()"""
            )
        except Exception:
            options_info = []

        target = None
        for o in options_info:
            text = o.get("text", "")
            if match_mode == "exact":
                if text == value_str:
                    target = o
                    break
            else:
                if value_str.lower() in text.lower():
                    target = o
                    break

        if target is None:
            raise FieldNotFoundError(
                message=f"Autocomplete '{field.name}': no option matching '{value_str}' "
                        f"(options: {[o.get('text','') for o in options_info][:5]})",
                field=field.name,
                selector=field.selector,
            )

        # Native Playwright click via text selector (escaped).
        # mat-option text is unique enough; fall back to nth-index selector.
        text = target["text"]
        try:
            await browser.click(
                f'{option_sel}:has-text("{text}")',
                timeout=field.timeout,
            )
        except Exception as e:
            # Fallback: click by index using CSS nth-child
            idx = target["i"] + 1
            try:
                await browser.click(
                    f"{option_sel}:nth-child({idx})",
                    timeout=field.timeout,
                )
            except Exception as e2:
                raise FillTimeoutError(
                    message=f"Failed to native-click autocomplete option '{field.name}': {e} / {e2}",
                    field=field.name,
                    selector=field.selector,
                )

    async def _verify(self, browser, field: FieldDefinition, value_str: str) -> None:
        """Verify the input now holds the selected value."""
        try:
            actual = await browser.get_attribute(field.selector, "value")
        except Exception:
            actual = ""
        if not actual or value_str.lower() not in str(actual).lower():
            raise FillVerificationError(
                message=f"Autocomplete '{field.name}' read-back '{actual}' != '{value_str}'",
                field=field.name,
                selector=field.selector,
            )
