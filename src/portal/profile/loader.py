"""Portal Profile Intelligence — Profile Loader.

Loads PortalProfile from YAML files and saves profiles back to disk.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.portal.profile.models import PortalProfile
from src.portal.profile.exceptions import ProfileLoadError
from src.portal.profile.schema import CURRENT_SCHEMA_VERSION

logger = logging.getLogger("insuredesk.profile.loader")

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


class ProfileLoader:
    """Loads and saves PortalProfile configurations from YAML.

    Usage:
        loader = ProfileLoader()
        profile = loader.load("portals/profiles/great_eastern.yaml")
        loader.save(profile, "portals/profiles/great_eastern.yaml")
        profiles = loader.load_directory("portals/profiles/")
    """

    def load(self, path: str) -> PortalProfile:
        """Load a PortalProfile from a YAML file.

        Args:
            path: Path to YAML file

        Returns:
            PortalProfile instance

        Raises:
            ProfileLoadError: If file cannot be read or parsed
        """
        if yaml is None:
            raise ProfileLoadError("PyYAML is required. Install with: pip install pyyaml")

        path = os.path.expanduser(path)
        if not os.path.exists(path):
            raise ProfileLoadError(f"Profile file not found: {path}")

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception as e:
            raise ProfileLoadError(f"Failed to parse YAML: {e}")

        if not data:
            raise ProfileLoadError(f"Empty profile file: {path}")

        profile = PortalProfile(
            id=data.get("id", ""),
            name=data.get("name", ""),
            portal=data.get("portal", ""),
            version=data.get("version", "1.0"),
            schema_version=data.get("schema_version", "1.0"),
            workflows=data.get("workflows", {}),
            mappings=data.get("mappings", {}),
            validation_rules=data.get("validation_rules", {}),
            adapter=data.get("adapter", ""),
            metadata=data.get("metadata", {}),
        )
        logger.info("Loaded profile: %s (v%s) from %s", profile.id, profile.version, path)
        return profile

    def save(self, profile: PortalProfile, path: str) -> str:
        """Save a PortalProfile to a YAML file.

        Args:
            profile: Profile to save
            path: Output file path

        Returns:
            Absolute path to saved file
        """
        if yaml is None:
            raise ProfileLoadError("PyYAML is required")

        path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        profile.updated_at = datetime.now()
        profile.schema_version = CURRENT_SCHEMA_VERSION

        data = {
            "id": profile.id,
            "name": profile.name,
            "portal": profile.portal,
            "version": profile.version,
            "schema_version": profile.schema_version,
            "adapter": profile.adapter,
            "workflows": profile.workflows,
            "mappings": profile.mappings,
            "validation_rules": profile.validation_rules,
            "metadata": {
                **profile.metadata,
                "updated_at": profile.updated_at.isoformat(),
            },
        }

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        logger.info("Saved profile: %s (v%s) to %s", profile.id, profile.version, path)
        return os.path.abspath(path)

    def load_directory(self, directory: str) -> List[PortalProfile]:
        """Load all YAML profiles from a directory.

        Args:
            directory: Directory containing profile YAML files

        Returns:
            List of loaded PortalProfile instances
        """
        directory = os.path.expanduser(directory)
        if not os.path.isdir(directory):
            raise ProfileLoadError(f"Directory not found: {directory}")

        profiles = []
        for filename in sorted(os.listdir(directory)):
            if filename.endswith((".yaml", ".yml")):
                try:
                    profile = self.load(os.path.join(directory, filename))
                    profiles.append(profile)
                except ProfileLoadError as e:
                    logger.warning("Skipping %s: %s", filename, e)

        return profiles
