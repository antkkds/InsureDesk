"""Mock BrowserSession for Fill Engine tests."""
from __future__ import annotations

from typing import Any, Optional


class MockBrowser:
    """Mock BrowserEngine for testing fill strategies.

    Records all interactions for verification.
    """

    def __init__(self):
        self.clicked: list[str] = []
        self.filled: dict[str, str] = {}
        self.selected: dict[str, str] = {}
        self.checked: dict[str, bool] = {}
        self.uploaded: dict[str, str] = {}
        self.selectors_found: set[str] = set()
        self.visible_selectors: set[str] = set()
        self.values: dict[str, str] = {}
        self.wait_selector_results: dict[str, bool] = {}
        self.navigated: list[str] = []

    async def navigate(self, url: str) -> bool:
        """Record navigation (PortalDriver protocol compatibility)."""
        self.navigated.append(url)
        return True

    async def fill_text(self, selector: str, value: str) -> bool:
        """Alias for fill (PortalDriver protocol method name)."""
        return await self.fill(selector, value)

    def register_selector(self, selector: str, found: bool = True, visible: bool = True):
        """Register a selector as existing on the page."""
        if found:
            self.selectors_found.add(selector)
        if visible:
            self.visible_selectors.add(selector)

    def register_value(self, selector: str, value: str):
        """Set the current value of a field."""
        self.values[selector] = value

    def register_checkbox(self, selector: str, checked: bool):
        """Set checkbox state."""
        self.checked[selector] = checked

    async def click(self, selector: str, timeout: int = 10000) -> bool:
        self.clicked.append(selector)
        # Toggle checkbox state if this selector has one
        if selector in self.checked:
            self.checked[selector] = not self.checked[selector]
        return selector in self.selectors_found

    async def fill(self, selector: str, value: str, delay_ms: int = 50) -> bool:
        self.filled[selector] = value
        self.values[selector] = value
        return selector in self.selectors_found

    async def select_option(self, selector: str, value: str) -> bool:
        self.selected[selector] = value
        self.values[selector] = value
        return selector in self.selectors_found

    async def is_checked(self, selector: str) -> bool:
        return self.checked.get(selector, False)

    async def set_checked(self, selector: str, checked: bool) -> bool:
        self.checked[selector] = checked
        if checked:
            self.clicked.append(f"check:{selector}")
        else:
            self.clicked.append(f"uncheck:{selector}")
        return selector in self.selectors_found

    async def upload_file(self, selector: str, file_path: str) -> bool:
        self.uploaded[selector] = file_path
        return selector in self.selectors_found

    async def get_text(self, selector: str) -> str:
        return self.values.get(selector, "")

    async def get_value(self, selector: str) -> str:
        return self.values.get(selector, "")

    async def get_attribute(self, selector: str, attr: str) -> Optional[str]:
        if attr == "checked":
            return "true" if self.checked.get(selector, False) else None
        return None

    async def is_visible(self, selector: str) -> bool:
        return selector in self.visible_selectors

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        result = self.wait_selector_results.get(selector)
        if result is not None:
            return result
        return selector in self.selectors_found

    async def evaluate(self, script: str) -> Any:
        return None

    async def screenshot(self, path: Optional[str] = None) -> Optional[bytes]:
        return None

    async def get_cookies(self):
        return []

    async def set_cookies(self, cookies):
        pass
