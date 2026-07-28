"""InsureDesk — Portal Drift Detection: Baseline Recorder.

Captures a portal's current UI state as a BaselineSnapshot
by extracting selectors and element metadata from portal YAML mapping
and (optionally) from live browser inspection.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from src.portal.drift.models import BaselineSnapshot, BaselineSelector
from src.portal.drift.storage import BaselineStorage
from src.portal.drift.exceptions import CaptureError
from src.portal.mapping import load_portal_mapping, get_selector

logger = logging.getLogger("insuredesk.drift.baseline")


class BaselineRecorder:
    """Recorder that captures a portal's baseline state.

    Two capture modes:
    1. From YAML mapping — extracts selectors from the portal YAML config
    2. From live browser — (future) uses Inspector to capture live elements

    Usage:
        recorder = BaselineRecorder()
        snapshot = recorder.capture_from_yaml("great_eastern")
        recorder.save(snapshot)
    """

    def __init__(self, storage: Optional[BaselineStorage] = None):
        self._storage = storage or BaselineStorage()

    def capture_from_yaml(self, portal_id: str) -> BaselineSnapshot:
        """Capture baseline from portal YAML mapping.

        Extracts all selectors defined in the portal config
        and builds a BaselineSnapshot.

        Args:
            portal_id: Portal identifier (e.g. 'great_eastern').

        Returns:
            BaselineSnapshot with all selectors from the YAML.

        Raises:
            CaptureError: If portal mapping cannot be loaded.
        """
        mapping = load_portal_mapping(portal_id)
        if not mapping:
            raise CaptureError(portal_id, "Portal mapping not found")

        snapshot = BaselineSnapshot(
            portal_id=portal_id,
            version="1.0",
            pages={
                "login": mapping.login_url or "",
                "base": mapping.base_url or "",
            },
            metadata={
                "name": mapping.name,
                "short_name": mapping.short_name,
                "source": "yaml",
                "captured_by": "BaselineRecorder",
            },
        )

        # Extract flat selectors from nested dict
        selectors = self._flatten_selectors(mapping.selectors)
        for name, sel_value in selectors.items():
            bs = self._build_baseline_selector(name, sel_value)
            snapshot.selectors[name] = bs

        logger.info(
            f"Captured {len(snapshot.selectors)} selectors "
            f"from YAML for {portal_id}"
        )
        return snapshot

    def _flatten_selectors(self, selectors: dict,
                           prefix: str = "") -> Dict[str, str]:
        """Flatten nested selector dict into dot-separated paths."""
        result: Dict[str, str] = {}
        for key, value in selectors.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                # Could be nested section or a dict-valued selector
                has_sub_selector = any(
                    isinstance(v, str) and ("#" in v or "." in v or "[" in v)
                    for v in value.values()
                )
                if has_sub_selector:
                    # This is a group of selectors
                    sub = self._flatten_selectors(value, full_key)
                    result.update(sub)
                else:
                    # Deep nesting or metadata — try one more level
                    sub = self._flatten_selectors(value, full_key)
                    result.update(sub)
            elif isinstance(value, str):
                result[full_key] = value
        return result

    def _build_baseline_selector(self, name: str,
                                  selector: str) -> BaselineSelector:
        """Build a BaselineSelector from a selector string."""
        # Generate a simple hash from the selector itself
        content_hash = hashlib.md5(selector.encode()).hexdigest()[:12]
        return BaselineSelector(
            name=name,
            selector=selector,
            hash=content_hash,
        )

    def save(self, snapshot: BaselineSnapshot) -> str:
        """Save the baseline snapshot to storage."""
        return self._storage.save_baseline(snapshot)

    def load(self, portal_id: str) -> BaselineSnapshot:
        """Load the current baseline for a portal."""
        return self._storage.load_baseline(portal_id)

    def has_baseline(self, portal_id: str) -> bool:
        """Check if a baseline exists."""
        return self._storage.has_baseline(portal_id)
