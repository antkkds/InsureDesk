"""Tests for Angular Material AutocompleteStrategy.

Covers the GEARS mat-autocomplete interaction:
    focus → type → wait mat-option → NATIVE click → read-back verify

Uses MockBrowser (test double) with mat-option simulation.
"""
from __future__ import annotations

import pytest

from src.fill.schema import FieldDefinition, FieldType
from src.fill.strategies.autocomplete import AutocompleteStrategy
from src.fill.exceptions import (
    FieldNotFoundError,
    FillVerificationError,
)
from tests.mock_browser import MockBrowser


class MockAutocompleteBrowser(MockBrowser):
    """MockBrowser + simulated mat-option panel."""

    def __init__(self):
        super().__init__()
        self.option_texts: dict[str, list[str]] = {}   # selector -> option texts
        self.native_clicks: list[tuple[str, str]] = []  # (selector, text)
        self.js_clicks_blocked = False
        self.disabled_inputs: set[str] = set()

    def register_options(self, input_sel: str, options: list[str]):
        self.option_texts[input_sel] = options

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        if selector == "mat-option":
            return any(self.option_texts.values())
        return await super().wait_for_selector(selector, timeout)

    async def evaluate(self, script: str) -> object:
        # Simulate enumerating mat-options for the target input
        if "querySelectorAll" in script and "mat-option" in script:
            import re
            m = re.search(r"querySelectorAll\('([^']+)'\)", script)
            sel = m.group(1) if m else ""
            # find the input whose panel this is (we key by the input selector)
            typed = getattr(self, "_last_typed_input", "")
            texts = self.option_texts.get(typed or "", [])
            return [{"i": i, "text": t} for i, t in enumerate(texts)]
        if "removeAttribute" in script:
            # find which id to enable
            import re
            m = re.search(r"getElementById\('([^']+)'\)", script)
            if m:
                self.disabled_inputs.discard("#" + m.group(1))
                return True
        return None

    async def click(self, selector: str, timeout: int = 10000) -> bool:
        # Native click path — record the text selector used
        if ":has-text(" in selector:
            import re
            m = re.search(r':has-text\("([^"]+)"\)', selector)
            text = m.group(1) if m else "?"
            self.native_clicks.append((selector, text))
            # Simulate Angular model update on native click
            # (unless angular_model_broken — Angular commits the WRONG model)
            typed = getattr(self, "_last_typed_input", "")
            if typed:
                if getattr(self, "angular_model_broken", False):
                    self.values[typed] = "WRONG_VALUE"
                else:
                    self.values[typed] = text
            return True
        return await super().click(selector, timeout)

    async def fill(self, selector: str, value: str, delay_ms: int = 50) -> bool:
        self._last_typed_input = selector
        return await super().fill(selector, value, delay_ms)


def _field(name: str, selector: str, **opts) -> FieldDefinition:
    options = {"autocomplete": True, "autocomplete_option": "mat-option"}
    options.update(opts)
    return FieldDefinition(
        name=name, selector=selector, type=FieldType.TEXT, options=options,
    )


class TestAutocompleteStrategy:
    @pytest.mark.asyncio
    async def test_selects_matching_option_native_click(self):
        browser = MockAutocompleteBrowser()
        browser.register_selector("#condition", found=True, visible=True)
        browser.register_options("#condition", ["NEW REGISTERED", "USED"])

        field = _field("condition", "#condition")
        ok = await AutocompleteStrategy().fill(browser, field, "USED")

        assert ok is True
        assert browser.values.get("#condition") == "USED"
        # Must have used native click (has-text selector), not JS
        assert any(":has-text(" in s for s, _ in browser.native_clicks)

    @pytest.mark.asyncio
    async def test_enables_disabled_input_first(self):
        browser = MockAutocompleteBrowser()
        browser.register_selector("#condition", found=True, visible=True)
        browser.register_options("#condition", ["NEW REGISTERED", "USED"])
        browser.disabled_inputs.add("#condition")

        field = _field("condition", "#condition", force_enable=True)
        await AutocompleteStrategy().fill(browser, field, "USED")

        assert "#condition" not in browser.disabled_inputs

    @pytest.mark.asyncio
    async def test_no_option_match_raises(self):
        browser = MockAutocompleteBrowser()
        browser.register_selector("#condition", found=True, visible=True)
        browser.register_options("#condition", ["NEW REGISTERED"])

        field = _field("condition", "#condition")
        with pytest.raises(FieldNotFoundError):
            await AutocompleteStrategy().fill(browser, field, "RACECAR")

    @pytest.mark.asyncio
    async def test_verify_fails_when_readback_mismatch(self):
        browser = MockAutocompleteBrowser()
        browser.register_selector("#condition", found=True, visible=True)
        browser.register_options("#condition", ["NEW REGISTERED", "USED"])
        browser.angular_model_broken = True  # simulate Angular not updating

        field = _field("condition", "#condition")
        with pytest.raises(FillVerificationError):
            await AutocompleteStrategy().fill(browser, field, "USED")

    @pytest.mark.asyncio
    async def test_no_options_appear_raises(self):
        browser = MockAutocompleteBrowser()
        browser.register_selector("#condition", found=True, visible=True)
        # no options registered → wait_for_selector("mat-option") False

        field = _field("condition", "#condition")
        with pytest.raises(FieldNotFoundError):
            await AutocompleteStrategy().fill(browser, field, "USED")

    @pytest.mark.asyncio
    async def test_none_value_skipped(self):
        browser = MockAutocompleteBrowser()
        field = _field("condition", "#condition")
        assert await AutocompleteStrategy().fill(browser, field, None) is True


class TestTextStrategyDelegation:
    @pytest.mark.asyncio
    async def test_text_strategy_delegates_autocomplete(self):
        """Field with options.autocomplete must go through AutocompleteStrategy."""
        from src.fill.strategies.text import TextStrategy

        browser = MockAutocompleteBrowser()
        browser.register_selector("#condition", found=True, visible=True)
        browser.register_options("#condition", ["NEW REGISTERED", "USED"])

        field = _field("condition", "#condition")
        ok = await TextStrategy().fill(browser, field, "USED")

        assert ok is True
        assert browser.values.get("#condition") == "USED"
        assert any(":has-text(" in s for s, _ in browser.native_clicks)

    @pytest.mark.asyncio
    async def test_text_strategy_normal_path_unchanged(self):
        """Plain text fields (no autocomplete) still use normal fill."""
        from src.fill.strategies.text import TextStrategy

        browser = MockBrowser()
        browser.register_selector("#name", found=True, visible=True)
        field = FieldDefinition(
            name="name", selector="#name", type=FieldType.TEXT,
        )
        ok = await TextStrategy().fill(browser, field, "John")
        assert ok is True
        assert browser.filled.get("#name") == "John"
