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
    ):
        self._loader = loader or ProfileLoader()
        self._validator = validator or ProfileValidator()
        self._analyzer = analyzer or ProfileAnalyzer(self._validator)
        self._comparator = comparator or ProfileComparator()
        self._upgrader = upgrader or ProfileUpgrader()
        self._registry = registry or ProfileRegistry()

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
