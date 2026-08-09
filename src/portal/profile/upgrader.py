"""Portal Profile Intelligence — Profile Upgrader.

Handles automatic schema upgrades for PortalProfile configurations.
Migrates profiles from older schema versions to the latest.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.profile.models import PortalProfile, ProfileVersion
from src.portal.profile.schema import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_VERSIONS,
)
from src.portal.profile.exceptions import ProfileUpgradeError

logger = logging.getLogger("insuredesk.profile.upgrader")


class ProfileUpgrader:
    """Upgrades PortalProfile configurations to newer schema versions.

    Usage:
        upgrader = ProfileUpgrader()
        upgraded_profile, version_log = upgrader.upgrade(profile)
    """

    def upgrade(
        self,
        profile: PortalProfile,
        target_version: Optional[str] = None,
    ) -> tuple[PortalProfile, ProfileVersion]:
        """Upgrade a profile to the target schema version.

        Args:
            profile: The profile to upgrade
            target_version: Target schema version (default: latest)

        Returns:
            Tuple of (upgraded profile, version record)

        Raises:
            ProfileUpgradeError: If upgrade is not possible
        """
        target = target_version or CURRENT_SCHEMA_VERSION

        if profile.schema_version == target:
            logger.info("Profile '%s' is already at schema %s", profile.id, target)
            return profile, ProfileVersion(
                profile_id=profile.id,
                version=profile.version,
                schema_version=target,
                changes=[],
                source="no_change",
            )

        # Collect migration steps
        changes: List[str] = []
        current = profile.schema_version

        # If upgrading from 1.0 → 2.0
        if current == "1.0" and target == "2.0":
            profile.schema_version = "2.0"
            if not profile.adapter:
                profile.adapter = ""
            if profile.validation_rules is None:
                profile.validation_rules = {}
            if profile.metadata is None:
                profile.metadata = {"upgraded_from": "1.0"}
            else:
                profile.metadata["upgraded_from"] = "1.0"

            changes = SCHEMA_VERSIONS.get("2.0", {}).get("changes", [])
            logger.info("Upgraded profile '%s' from 1.0 to 2.0", profile.id)

        else:
            raise ProfileUpgradeError(
                f"Cannot upgrade from schema {current} to {target}: "
                f"no migration path available"
            )

        version_record = ProfileVersion(
            profile_id=profile.id,
            version=profile.version,
            schema_version=target,
            changes=changes,
            source="auto_upgrade",
        )

        return profile, version_record
