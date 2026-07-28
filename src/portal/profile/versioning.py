"""InsureDesk — Multi Portal Profile: Version Manager.

Version history, rollback, activate/deactivate profiles.
Stores version snapshots as JSON files alongside portal profiles.
"""
from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.portal.profile.models import PortalProfile
from src.portal.profile.exceptions import ProfileNotFoundError
from src.portal.profile.loader import ProfileLoader

logger = logging.getLogger("insuredesk.profile.versioning")

DEFAULT_VERSIONS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "versions"


class VersionManager:
    """Manages version history for portal profiles.

    Each profile can have multiple version snapshots stored as JSON.
    Supports: create, list, diff, rollback, activate/deactivate.

    Usage:
        vm = VersionManager()
        vm.create_version(profile, "Added AXA workflow")
        versions = vm.list_versions("great_eastern")
        restored = vm.rollback("great_eastern", version_id)
    """

    def __init__(self, versions_dir: Optional[str] = None,
                 loader: Optional[ProfileLoader] = None):
        self._versions_dir = Path(versions_dir or DEFAULT_VERSIONS_DIR)
        self._versions_dir.mkdir(parents=True, exist_ok=True)
        self._loader = loader or ProfileLoader()

    # ── Version CRUD ──

    def create_version(self, profile: PortalProfile,
                       description: str = "") -> Dict[str, Any]:
        """Create a version snapshot of a profile.

        Args:
            profile: The profile to snapshot.
            description: Human-readable change description.

        Returns:
            Version metadata dict.
        """
        version_id = f"v{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now()

        version_data = {
            "version_id": version_id,
            "profile_id": profile.id,
            "profile_name": profile.name,
            "portal": profile.portal,
            "version": profile.version,
            "schema_version": profile.schema_version,
            "timestamp": timestamp.isoformat(),
            "description": description,
            "profile_snapshot": {
                "workflows": profile.workflows,
                "mappings": profile.mappings,
                "selectors": getattr(profile, 'selectors', {}),
                "config": getattr(profile, 'config', {}),
            },
        }

        # Save version file
        path = self._version_path(profile.id, version_id)
        with open(path, "w") as f:
            json.dump(version_data, f, indent=2, default=str)

        logger.info(
            f"Created version {version_id} for '{profile.id}' "
            f"({description or 'no description'})"
        )
        return version_data

    def load_version(self, profile_id: str,
                     version_id: str) -> Optional[Dict[str, Any]]:
        """Load a specific version snapshot."""
        path = self._version_path(profile_id, version_id)
        if not path.exists():
            return None
        with open(path, "r") as f:
            return json.load(f)

    def list_versions(self, profile_id: str) -> List[Dict[str, Any]]:
        """List all versions for a profile, newest first."""
        versions = []
        version_dir = self._profile_versions_dir(profile_id)
        if not version_dir.exists():
            return versions

        for f in sorted(version_dir.glob("*.json"), reverse=True):
            try:
                with open(f, "r") as fh:
                    data = json.load(fh)
                versions.append({
                    "version_id": data["version_id"],
                    "timestamp": data["timestamp"],
                    "description": data.get("description", ""),
                    "version": data.get("version", "?"),
                })
            except (json.JSONDecodeError, KeyError):
                continue

        return versions

    def delete_version(self, profile_id: str, version_id: str) -> bool:
        """Delete a version snapshot."""
        path = self._version_path(profile_id, version_id)
        if path.exists():
            path.unlink()
            return True
        return False

    # ── Rollback ──

    def rollback(self, profile_id: str, version_id: str) -> PortalProfile:
        """Rollback a profile to a previous version.

        Restores the profile snapshot from the version and
        returns a PortalProfile with the old state.

        Args:
            profile_id: Profile to rollback.
            version_id: Version to restore.

        Returns:
            PortalProfile with restored state.

        Raises:
            ProfileNotFoundError: If version doesn't exist.
        """
        version_data = self.load_version(profile_id, version_id)
        if version_data is None:
            raise ProfileNotFoundError(
                f"Version '{version_id}' not found for profile '{profile_id}'"
            )

        snapshot = version_data.get("profile_snapshot", {})
        profile = PortalProfile(
            id=profile_id,
            name=version_data.get("profile_name", profile_id),
            portal=version_data.get("portal", ""),
            version=version_data.get("version", "1.0"),
            workflows=snapshot.get("workflows", {}),
            mappings=snapshot.get("mappings", {}),
        )

        logger.info(f"Rolled back '{profile_id}' to version {version_id}")
        return profile

    def compare_versions(self, profile_id: str,
                         version_a: str,
                         version_b: str) -> Dict[str, Any]:
        """Compare two versions and return differences."""
        data_a = self.load_version(profile_id, version_a)
        data_b = self.load_version(profile_id, version_b)

        if not data_a or not data_b:
            raise ProfileNotFoundError("One or both versions not found")

        snap_a = data_a.get("profile_snapshot", {})
        snap_b = data_b.get("profile_snapshot", {})

        changes = []

        # Compare workflows
        wf_a = set(snap_a.get("workflows", {}).keys())
        wf_b = set(snap_b.get("workflows", {}).keys())
        for added in wf_b - wf_a:
            changes.append({"type": "workflow_added", "name": added})
        for removed in wf_a - wf_b:
            changes.append({"type": "workflow_removed", "name": removed})
        for common in wf_a & wf_b:
            if snap_a["workflows"][common] != snap_b["workflows"][common]:
                changes.append({"type": "workflow_changed", "name": common})

        # Compare mappings
        map_a = set(snap_a.get("mappings", {}).keys())
        map_b = set(snap_b.get("mappings", {}).keys())
        for added in map_b - map_a:
            changes.append({"type": "mapping_added", "name": added})
        for removed in map_a - map_b:
            changes.append({"type": "mapping_removed", "name": removed})

        return {
            "profile_id": profile_id,
            "version_a": version_a,
            "version_b": version_b,
            "changes": changes,
            "change_count": len(changes),
        }

    # ── Activate / Deactivate ──

    def activate(self, profile_id: str, version_id: Optional[str] = None) -> None:
        """Mark a profile (or specific version) as active.

        Writes an 'active' marker file.

        Args:
            profile_id: Profile to activate.
            version_id: Optional specific version to pin.
        """
        marker = {
            "profile_id": profile_id,
            "active_version": version_id,
            "activated_at": datetime.now().isoformat(),
        }
        path = self._profile_versions_dir(profile_id) / "ACTIVE.json"
        with open(path, "w") as f:
            json.dump(marker, f, indent=2)
        logger.info(f"Activated profile '{profile_id}' (version: {version_id or 'latest'})")

    def deactivate(self, profile_id: str) -> None:
        """Mark a profile as inactive."""
        path = self._profile_versions_dir(profile_id) / "ACTIVE.json"
        if path.exists():
            path.unlink()
        logger.info(f"Deactivated profile '{profile_id}'")

    def is_active(self, profile_id: str) -> bool:
        """Check if a profile is marked as active."""
        path = self._profile_versions_dir(profile_id) / "ACTIVE.json"
        return path.exists()

    def get_active_version(self, profile_id: str) -> Optional[str]:
        """Get the active version ID for a profile."""
        path = self._profile_versions_dir(profile_id) / "ACTIVE.json"
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                return json.load(f).get("active_version")
        except (json.JSONDecodeError, KeyError):
            return None

    # ── Migration History ──

    def log_migration(self, profile_id: str, from_version: str,
                      to_version: str, description: str) -> Dict[str, Any]:
        """Record a migration event in the migration history."""
        entry = {
            "migration_id": f"m{uuid.uuid4().hex[:8]}",
            "profile_id": profile_id,
            "from_version": from_version,
            "to_version": to_version,
            "timestamp": datetime.now().isoformat(),
            "description": description,
        }

        history = self._load_migration_history(profile_id)
        history.append(entry)

        path = self._profile_versions_dir(profile_id) / "migrations.json"
        with open(path, "w") as f:
            json.dump(history, f, indent=2, default=str)

        return entry

    def get_migration_history(self, profile_id: str) -> List[Dict[str, Any]]:
        """Get migration history for a profile."""
        return self._load_migration_history(profile_id)

    # ── Health Monitoring ──

    def monitor_all(self, profiles: List[PortalProfile]) -> Dict[str, Any]:
        """Health monitoring across all profiles.

        Checks each profile for:
        - Has active version
        - Has version history
        - Schema version currency

        Args:
            profiles: List of profiles to check.

        Returns:
            Summary dict with per-profile stats.
        """
        results = {}
        for profile in profiles:
            versions = self.list_versions(profile.id)
            active = self.is_active(profile.id)
            active_ver = self.get_active_version(profile.id)
            migrations = len(self._load_migration_history(profile.id))

            results[profile.id] = {
                "name": profile.name,
                "version": profile.version,
                "active": active,
                "active_version": active_ver,
                "version_count": len(versions),
                "latest_version": versions[0]["version_id"] if versions else None,
                "latest_timestamp": versions[0]["timestamp"] if versions else None,
                "migration_count": migrations,
                "needs_update": versions and versions[0]["version"] != profile.version,
            }

        return results

    # ── Internal ──

    def _version_path(self, profile_id: str, version_id: str) -> Path:
        return self._profile_versions_dir(profile_id) / f"{version_id}.json"

    def _profile_versions_dir(self, profile_id: str) -> Path:
        path = self._versions_dir / profile_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load_migration_history(self, profile_id: str) -> List[Dict[str, Any]]:
        path = self._profile_versions_dir(profile_id) / "migrations.json"
        if not path.exists():
            return []
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError):
            return []
