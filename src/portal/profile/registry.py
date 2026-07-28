"""Portal Profile Intelligence — Registry & Manager.

ProfileRegistry: Central registry of known PortalProfile instances.
ProfileManager: High-level orchestrator for profile operations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.profile.models import (
    PortalProfile,
    ProfileDiff,
    ProfileHealth,
    ProfileVersion,
)
from src.portal.profile.loader import ProfileLoader
from src.portal.profile.validator import ProfileValidator
from src.portal.profile.analyzer import ProfileAnalyzer
from src.portal.profile.comparator import ProfileComparator
from src.portal.profile.upgrader import ProfileUpgrader
from src.portal.profile.versioning import VersionManager
from src.portal.profile.exceptions import ProfileNotFoundError

logger = logging.getLogger("insuredesk.profile.registry")


class ProfileRegistry:
    """In-memory registry of portal profiles.

    Usage:
        registry = ProfileRegistry()
        registry.register(profile)
        profile = registry.get("great_eastern")
    """

    def __init__(self):
        self._profiles: Dict[str, PortalProfile] = {}

    def register(self, profile: PortalProfile) -> None:
        self._profiles[profile.id] = profile

    def unregister(self, profile_id: str) -> None:
        self._profiles.pop(profile_id, None)

    def get(self, profile_id: str) -> Optional[PortalProfile]:
        return self._profiles.get(profile_id)

    def get_or_raise(self, profile_id: str) -> PortalProfile:
        profile = self.get(profile_id)
        if profile is None:
            raise ProfileNotFoundError(f"Profile '{profile_id}' not found")
        return profile

    def list_ids(self) -> List[str]:
        return list(self._profiles.keys())

    def list_all(self) -> List[PortalProfile]:
        return list(self._profiles.values())

    def clear(self) -> None:
        self._profiles.clear()

    def __len__(self) -> int:
        return len(self._profiles)

    def __contains__(self, profile_id: str) -> bool:
        return profile_id in self._profiles


class ProfileManager:
    """High-level orchestrator for profile operations.

    Usage:
        manager = ProfileManager()
        manager.load_directory("portals/profiles/")
        health = manager.analyze("great_eastern")
        diff = manager.compare("great_eastern", "prudential")
        manager.upgrade("great_eastern")
    """

    def __init__(
        self,
        loader: Optional[ProfileLoader] = None,
        validator: Optional[ProfileValidator] = None,
        analyzer: Optional[ProfileAnalyzer] = None,
        comparator: Optional[ProfileComparator] = None,
        upgrader: Optional[ProfileUpgrader] = None,
        registry: Optional[ProfileRegistry] = None,
        versioning: Optional[VersionManager] = None,
    ):
        self._loader = loader or ProfileLoader()
        self._validator = validator or ProfileValidator()
        self._analyzer = analyzer or ProfileAnalyzer(self._validator)
        self._comparator = comparator or ProfileComparator()
        self._upgrader = upgrader or ProfileUpgrader()
        self._registry = registry or ProfileRegistry()
        self._versioning = versioning or VersionManager()

    # ── Loading ──

    def load(self, path: str) -> PortalProfile:
        """Load a profile from file and register it."""
        profile = self._loader.load(path)
        self._registry.register(profile)
        return profile

    def load_directory(self, directory: str) -> List[PortalProfile]:
        """Load all profiles from a directory."""
        profiles = self._loader.load_directory(directory)
        for p in profiles:
            self._registry.register(p)
        return profiles

    def save(self, profile: PortalProfile, path: str) -> str:
        """Save a profile to file."""
        return self._loader.save(profile, path)

    # ── Validation ──

    def validate(self, profile_id: str) -> List[str]:
        """Validate a registered profile."""
        profile = self._registry.get_or_raise(profile_id)
        return self._validator.validate(profile)

    def is_valid(self, profile_id: str) -> bool:
        """Quick validity check."""
        profile = self._registry.get_or_raise(profile_id)
        return self._validator.is_valid(profile)

    # ── Analysis ──

    def analyze(self, profile_id: str) -> ProfileHealth:
        """Analyze a profile's health."""
        profile = self._registry.get_or_raise(profile_id)
        return self._analyzer.analyze(profile)

    def suggest(self, profile_id: str) -> List[str]:
        """Get improvement suggestions."""
        profile = self._registry.get_or_raise(profile_id)
        return self._analyzer.suggest_improvements(profile)

    # ── Comparison ──

    def compare(
        self,
        profile_id_a: str,
        profile_id_b: str,
    ) -> ProfileDiff:
        """Compare two registered profiles."""
        profile_a = self._registry.get_or_raise(profile_id_a)
        profile_b = self._registry.get_or_raise(profile_id_b)
        return self._comparator.compare(profile_a, profile_b)

    # ── Upgrade ──

    def upgrade(
        self,
        profile_id: str,
    ) -> tuple[PortalProfile, ProfileVersion]:
        """Upgrade a profile to the latest schema."""
        profile = self._registry.get_or_raise(profile_id)
        upgraded, version = self._upgrader.upgrade(profile)
        self._registry.register(upgraded)
        return upgraded, version

    # ── Registry access ──

    def get(self, profile_id: str) -> Optional[PortalProfile]:
        return self._registry.get(profile_id)

    def list_ids(self) -> List[str]:
        return self._registry.list_ids()

    def list_all(self) -> List[PortalProfile]:
        return self._registry.list_all()

    # ── Sprint 5.4: Version Management ──

    def create_version(self, profile_id: str,
                        description: str = "") -> Dict[str, Any]:
        """Create a version snapshot of a profile."""
        profile = self._registry.get_or_raise(profile_id)
        return self._versioning.create_version(profile, description)

    def list_versions(self, profile_id: str) -> List[Dict[str, Any]]:
        """List all versions for a profile."""
        return self._versioning.list_versions(profile_id)

    def rollback(self, profile_id: str,
                  version_id: str) -> PortalProfile:
        """Rollback a profile to a previous version."""
        restored = self._versioning.rollback(profile_id, version_id)
        self._registry.register(restored)
        # Log the rollback as a migration
        self._versioning.log_migration(
            profile_id, "current", version_id,
            f"Rolled back to {version_id}"
        )
        return restored

    def compare_versions(self, profile_id: str,
                          version_a: str,
                          version_b: str) -> Dict[str, Any]:
        """Compare two versions for differences."""
        return self._versioning.compare_versions(
            profile_id, version_a, version_b
        )

    def activate(self, profile_id: str,
                  version_id: Optional[str] = None) -> None:
        """Activate a profile (optionally pin a version)."""
        self._versioning.activate(profile_id, version_id)

    def deactivate(self, profile_id: str) -> None:
        """Deactivate a profile."""
        self._versioning.deactivate(profile_id)

    def is_active(self, profile_id: str) -> bool:
        """Check if profile is active."""
        return self._versioning.is_active(profile_id)

    def get_active_version(self, profile_id: str) -> Optional[str]:
        """Get the active pinned version."""
        return self._versioning.get_active_version(profile_id)

    # ── Sprint 5.4: Migration History ──

    def log_migration(self, profile_id: str, from_version: str,
                       to_version: str, description: str) -> Dict[str, Any]:
        """Record a migration event."""
        return self._versioning.log_migration(
            profile_id, from_version, to_version, description
        )

    def get_migration_history(self, profile_id: str) -> List[Dict[str, Any]]:
        """Get migration history for a profile."""
        return self._versioning.get_migration_history(profile_id)

    # ── Sprint 5.4: Health Monitoring ──

    def monitor_all(self) -> Dict[str, Any]:
        """Monitor health across all registered profiles."""
        return self._versioning.monitor_all(self._registry.list_all())
