"""Portal Profile Intelligence — Profile Comparator.

Compares two PortalProfile configurations and produces a structured diff.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.profile.models import PortalProfile, ProfileDiff

logger = logging.getLogger("insuredesk.profile.comparator")


class ProfileComparator:
    """Compares two portal profiles and generates a structured diff.

    Usage:
        comparator = ProfileComparator()
        diff = comparator.compare(old_profile, new_profile)
    """

    def compare(
        self,
        old_profile: PortalProfile,
        new_profile: PortalProfile,
    ) -> ProfileDiff:
        """Compare two profiles and return the differences.

        Args:
            old_profile: The older/ baseline profile
            new_profile: The newer/ updated profile

        Returns:
            ProfileDiff with added, removed, and modified items
        """
        diff = ProfileDiff(
            old_version=old_profile.version,
            new_version=new_profile.version,
        )

        # Compare top-level fields
        scalar_fields = ["name", "portal", "version", "schema_version", "adapter"]
        for field in scalar_fields:
            old_val = getattr(old_profile, field, None)
            new_val = getattr(new_profile, field, None)
            if old_val != new_val:
                diff.modified.append({
                    "path": field,
                    "old": old_val,
                    "new": new_val,
                    "type": "changed",
                })

        # Compare workflows
        self._compare_dicts(
            old_profile.workflows,
            new_profile.workflows,
            "workflows",
            diff,
        )

        # Compare mappings
        self._compare_dicts(
            old_profile.mappings,
            new_profile.mappings,
            "mappings",
            diff,
        )

        # Compare validation rules
        self._compare_dicts(
            old_profile.validation_rules,
            new_profile.validation_rules,
            "validation_rules",
            diff,
        )

        return diff

    def _compare_dicts(
        self,
        old: Dict[str, Any],
        new: Dict[str, Any],
        prefix: str,
        diff: ProfileDiff,
    ) -> None:
        """Compare two dicts and populate the diff."""
        old_keys = set(old.keys())
        new_keys = set(new.keys())

        for key in new_keys - old_keys:
            diff.added.append(f"{prefix}.{key}")

        for key in old_keys - new_keys:
            diff.removed.append(f"{prefix}.{key}")

        for key in old_keys & new_keys:
            if old[key] != new[key]:
                diff.modified.append({
                    "path": f"{prefix}.{key}",
                    "type": "changed",
                })
