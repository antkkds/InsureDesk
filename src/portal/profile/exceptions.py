"""Portal Profile Intelligence — Exceptions."""

from __future__ import annotations


class ProfileError(Exception):
    """Base exception for profile errors."""


class ProfileNotFoundError(ProfileError):
    """Raised when a profile is not found."""


class ProfileValidationError(ProfileError):
    """Raised when profile validation fails."""


class ProfileLoadError(ProfileError):
    """Raised when loading a profile fails."""


class ProfileUpgradeError(ProfileError):
    """Raised when upgrading a profile fails."""


class ProfileSchemaError(ProfileError):
    """Raised when the profile schema is invalid."""
