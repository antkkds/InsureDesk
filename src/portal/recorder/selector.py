"""Portal Workflow Recorder — Selector Generator.

Generates stable CSS selectors for DOM elements from CDP events.
Prioritizes selectors that are resilient to page changes.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from src.portal.recorder.exceptions import SelectorGenerationError

logger = logging.getLogger("insuredesk.recorder.selector")

# HTML tags that are useful for selector generation
MEANINGFUL_TAGS = {"input", "select", "button", "a", "textarea", "label"}

# Attributes to prefer for stable selectors
STABLE_ATTRS = ["id", "data-testid", "data-test", "aria-label",
                "data-cy", "data-test-id", "placeholder", "title"]


class SelectorGenerator:
    """Generates stable CSS selectors from element metadata.

    Priority order for selector generation:
    1. id (most stable)
    2. data-testid / data-test / data-cy
    3. name
    4. aria-label
    5. placeholder
    6. tag + class combination
    7. tag + nth-child (least stable, fallback)

    Usage:
        gen = SelectorGenerator()
        selector = gen.generate(tag="input", attributes={"name": "username"})
        # → "input[name='username']"
    """

    def generate(
        self,
        tag: Optional[str] = None,
        attributes: Optional[Dict[str, str]] = None,
        text: Optional[str] = None,
        position: Optional[Dict[str, int]] = None,
    ) -> str:
        """Generate a CSS selector from element metadata.

        Args:
            tag: HTML tag name
            attributes: Element attributes dict
            text: Element text content
            position: x,y coordinates

        Returns:
            A CSS selector string

        Raises:
            SelectorGenerationError: If no stable selector can be generated
        """
        attrs = attributes or {}

        # 1. By id
        if attrs.get("id"):
            return f"#{self._escape_css(attrs['id'])}"

        # 2. By data-testid or similar
        for stable_attr in STABLE_ATTRS:
            if stable_attr in attrs and attrs[stable_attr]:
                val = self._escape_css(attrs[stable_attr])
                return f"[{stable_attr}='{val}']"

        # 3. By tag + name
        if attrs.get("name"):
            name = self._escape_css(attrs["name"])
            if tag:
                return f"{tag}[name='{name}']"
            return f"[name='{name}']"

        # 4. By aria-label
        if attrs.get("aria-label"):
            label = self._escape_css(attrs["aria-label"])
            if tag:
                return f"{tag}[aria-label='{label}']"
            return f"[aria-label='{label}']"

        # 5. By placeholder
        if attrs.get("placeholder"):
            placeholder = self._escape_css(attrs["placeholder"])
            if tag:
                return f"{tag}[placeholder='{placeholder}']"
            return f"[placeholder='{placeholder}']"

        # 6. By tag + class
        if tag and attrs.get("class"):
            cls = self._clean_class(attrs["class"])
            if cls:
                return f"{tag}{cls}"

        # 7. By tag + type
        if tag and attrs.get("type"):
            return f"{tag}[type='{attrs['type']}']"

        # 8. Fallback: tag only (if meaningful)
        if tag and tag.lower() in MEANINGFUL_TAGS:
            return tag

        raise SelectorGenerationError(
            f"Cannot generate stable selector for tag={tag}, attrs={attrs}"
        )

    def generate_from_event(self, event_data: Dict[str, Any]) -> str:
        """Generate selector from a captured event dict."""
        return self.generate(
            tag=event_data.get("tag_name"),
            attributes=event_data.get("attributes", {}),
            text=event_data.get("text"),
            position=event_data.get("position"),
        )

    @staticmethod
    def _escape_css(value: str) -> str:
        """Escape special CSS characters in attribute values."""
        return value.replace("'", "\\'").replace("\"", "\\\"")

    @staticmethod
    def _clean_class(class_str: str) -> str:
        """Convert a class attribute to a CSS class selector."""
        if not class_str:
            return ""
        # Take first meaningful class (skip utility classes)
        classes = class_str.split()
        meaningful = [c for c in classes if not c.startswith(("_", "ng-", "css-"))]
        if meaningful:
            return "." + meaningful[0]
        return "." + classes[0] if classes else ""
