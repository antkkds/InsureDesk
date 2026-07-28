"""Portal Profile Intelligence — Schema Definition.

Defines the expected structure and required fields for PortalProfile YAML files.
Used by the Validator and Loader to ensure profile correctness.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Current schema version for portal profiles
CURRENT_SCHEMA_VERSION = "2.0"

# Required top-level fields
REQUIRED_FIELDS = [
    "id",
    "name",
    "portal",
    "version",
    "schema_version",
]

# Recommended fields (warning if missing)
RECOMMENDED_FIELDS = [
    "adapter",
    "workflows",
    "mappings",
]

# Schema definition for validation
PORTAL_PROFILE_SCHEMA = {
    "id": {"type": str, "required": True, "description": "Unique profile identifier"},
    "name": {"type": str, "required": True, "description": "Human-readable name"},
    "portal": {"type": str, "required": True, "description": "Portal identifier"},
    "version": {"type": str, "required": True, "description": "Profile version string"},
    "schema_version": {
        "type": str,
        "required": True,
        "description": "Schema version for compatibility",
    },
    "adapter": {
        "type": str,
        "required": False,
        "description": "Portal adapter class path",
    },
    "workflows": {
        "type": dict,
        "required": False,
        "description": "Workflow definitions keyed by action name",
    },
    "mappings": {
        "type": dict,
        "required": False,
        "description": "Field mappings for form filling",
    },
    "validation_rules": {
        "type": dict,
        "required": False,
        "description": "Validation rule references",
    },
    "metadata": {
        "type": dict,
        "required": False,
        "description": "Additional metadata",
    },
}

# Version history for migration/upgrade
SCHEMA_VERSIONS = {
    "1.0": {
        "description": "Initial schema",
        "fields": ["id", "name", "portal", "version"],
        "changes": [],
    },
    "2.0": {
        "description": "Added schema_version, validation_rules, adapter",
        "fields": [
            "id", "name", "portal", "version", "schema_version",
        ],
        "changes": [
            "Added schema_version field",
            "Added validation_rules section",
            "Added adapter field",
            "Added metadata section",
        ],
    },
}


def get_required_fields_for_schema(schema_version: str) -> List[str]:
    """Get required fields for a specific schema version."""
    if schema_version in SCHEMA_VERSIONS:
        return SCHEMA_VERSIONS[schema_version]["fields"]
    return REQUIRED_FIELDS


def is_schema_compatible(profile_version: str) -> bool:
    """Check if a profile version is compatible with the current schema."""
    try:
        profile_parts = [int(x) for x in profile_version.split(".")]
        current_parts = [int(x) for x in CURRENT_SCHEMA_VERSION.split(".")]
        return profile_parts[0] == current_parts[0]  # Major version must match
    except (ValueError, IndexError):
        return False
