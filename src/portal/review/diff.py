"""Portal Review Engine — Diff Engine.

Compares before/after data snapshots to detect field-level changes.
Supports nested dict comparison and produces structured Change objects.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from src.portal.review.models import Change, ChangeType

logger = logging.getLogger("insuredesk.review.diff")

# Fields to ignore when computing diffs (internal/technical)
IGNORED_FIELDS: Set[str] = {"execution_id", "plan_id", "session_id", "timestamp"}


class DiffEngine:
    """Computes field-level diffs between before/after data dicts.

    Usage:
        engine = DiffEngine()
        changes = engine.compute_diff(before_data, after_data)
    """

    def compute_diff(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        prefix: str = "",
    ) -> List[Change]:
        """Compare two dicts and return all field-level changes.

        Args:
            before: Snapshot before execution
            after: Snapshot after execution
            prefix: Key prefix for nested paths (used in recursion)

        Returns:
            List of Change objects
        """
        changes: List[Change] = []
        all_keys = set(before.keys()) | set(after.keys())

        for key in all_keys:
            if key in IGNORED_FIELDS:
                continue

            full_path = f"{prefix}.{key}" if prefix else key
            before_val = before.get(key)
            after_val = after.get(key)

            # Both are dicts → recursive comparison
            if isinstance(before_val, dict) and isinstance(after_val, dict):
                changes.extend(self.compute_diff(before_val, after_val, full_path))
                continue

            # Created
            if key not in before and key in after:
                changes.append(Change(
                    field=full_path,
                    before=None,
                    after=after_val,
                    change_type=ChangeType.CREATED.value,
                    source="portal",
                    reason="Field created during execution",
                ))
                continue

            # Removed
            if key in before and key not in after:
                changes.append(Change(
                    field=full_path,
                    before=before_val,
                    after=None,
                    change_type=ChangeType.REMOVED.value,
                    source="portal",
                    reason="Field removed during execution",
                ))
                continue

            # Updated or unchanged
            if before_val != after_val:
                change_type = self._classify_change(before_val, after_val, full_path)
                changes.append(Change(
                    field=full_path,
                    before=before_val,
                    after=after_val,
                    change_type=change_type,
                    source=self._determine_source(change_type),
                    reason=self._generate_reason(change_type, full_path),
                ))

        return changes

    def has_changes(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
    ) -> bool:
        """Quick check if there are any changes between two dicts."""
        return len(self.compute_diff(before, after)) > 0

    def get_changed_fields(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
    ) -> List[str]:
        """Return list of field paths that changed."""
        return [c.field for c in self.compute_diff(before, after)]

    def _classify_change(
        self,
        before_val: Any,
        after_val: Any,
        field: str,
    ) -> str:
        """Classify the type of change."""
        # Normalization: same value, different format
        if isinstance(before_val, str) and isinstance(after_val, str):
            b_clean = before_val.strip().lower()
            a_clean = after_val.strip().lower()
            if b_clean == a_clean:
                return ChangeType.NORMALIZED.value

        return ChangeType.UPDATED.value

    @staticmethod
    def _determine_source(change_type: str) -> str:
        if change_type == ChangeType.AUTO_FIXED.value:
            return "auto_fix"
        if change_type == ChangeType.NORMALIZED.value:
            return "portal"
        return "portal"

    @staticmethod
    def _generate_reason(change_type: str, field: str) -> str:
        reasons = {
            ChangeType.CREATED.value: f"Field '{field}' was created",
            ChangeType.REMOVED.value: f"Field '{field}' was removed",
            ChangeType.UPDATED.value: f"Field '{field}' was modified",
            ChangeType.NORMALIZED.value: f"Field '{field}' was normalized by portal",
            ChangeType.AUTO_FIXED.value: f"Field '{field}' was auto-corrected",
        }
        return reasons.get(change_type, f"Field '{field}' changed")
