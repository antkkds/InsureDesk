"""Portal Profile Intelligence.

Manages, analyzes, validates, compares, and upgrades InsureDesk
Portal Profile configurations (YAML files).

NOT UIP-AI Blueprints. These are PORTAL CONFIGURATIONS
describing how InsureDesk automates a specific insurance portal.
"""

from __future__ import annotations

from src.portal.profile.models import (
    PortalProfile,
    ProfileVersion,
    ProfileDiff,
    ProfileHealth,
    HealthIssue,
    ProfileStatus,
    HealthCategory,
)
from src.portal.profile.registry import ProfileManager, ProfileRegistry
from src.portal.profile.loader import ProfileLoader
from src.portal.profile.validator import ProfileValidator
from src.portal.profile.analyzer import ProfileAnalyzer
from src.portal.profile.comparator import ProfileComparator
from src.portal.profile.upgrader import ProfileUpgrader
from src.portal.profile.schema import CURRENT_SCHEMA_VERSION
from src.portal.profile.exceptions import (
    ProfileError,
    ProfileNotFoundError,
    ProfileValidationError,
    ProfileLoadError,
    ProfileUpgradeError,
    ProfileSchemaError,
)

__all__ = [
    "PortalProfile",
    "ProfileVersion",
    "ProfileDiff",
    "ProfileHealth",
    "HealthIssue",
    "ProfileStatus",
    "HealthCategory",
    "ProfileManager",
    "ProfileRegistry",
    "ProfileLoader",
    "ProfileValidator",
    "ProfileAnalyzer",
    "ProfileComparator",
    "ProfileUpgrader",
    "CURRENT_SCHEMA_VERSION",
    "ProfileError",
    "ProfileNotFoundError",
    "ProfileValidationError",
    "ProfileLoadError",
    "ProfileUpgradeError",
    "ProfileSchemaError",
]
