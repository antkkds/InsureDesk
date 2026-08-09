"""Portal Profile Intelligence — Profile Validator.

Validates PortalProfile configurations against the schema definition.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.profile.models import PortalProfile
from src.portal.profile.schema import (
    PORTAL_PROFILE_SCHEMA,
    CURRENT_SCHEMA_VERSION,
    get_required_fields_for_schema,
    is_schema_compatible,
)
from src.portal.profile.exceptions import ProfileValidationError

logger = logging.getLogger("insuredesk.profile.validator")


class ProfileValidator:
    """Validates PortalProfile instances against the schema.

    Performs:
    - Required field presence
    - Field type checking
    - Schema version compatibility
    - Workflow structure validation
    - Mapping structure validation

    Usage:
        validator = ProfileValidator()
        errors = validator.validate(profile)
        if errors:
            print(f"Profile has {len(errors)} errors")
    """

    def validate(self, profile: PortalProfile) -> List[str]:
        """Validate a PortalProfile and return a list of error messages.

        Args:
            profile: The profile to validate

        Returns:
            List of error messages (empty = valid)
        """
        errors: List[str] = []
        profile_dict = profile.to_dict()

        # 1. Check schema version compatibility
        if not is_schema_compatible(profile.schema_version):
            errors.append(
                f"Schema version {profile.schema_version} is incompatible "
                f"with current {CURRENT_SCHEMA_VERSION}"
            )

        # 2. Check required fields
        for field in get_required_fields_for_schema(profile.schema_version):
            value = getattr(profile, field, None)
            if value is None or (isinstance(value, (dict, list)) and not value):
                errors.append(f"Required field '{field}' is missing or empty")

        # 3. Check field types against schema
        for field_name, field_schema in PORTAL_PROFILE_SCHEMA.items():
            if field_schema.get("required", False):
                value = getattr(profile, field_name, None)
                expected_type = field_schema["type"]
                if value is not None and not isinstance(value, expected_type):
                    errors.append(
                        f"Field '{field_name}' should be {expected_type.__name__}, "
                        f"got {type(value).__name__}"
                    )

        # 4. Validate workflow structure
        if profile.workflows:
            self._validate_workflows(profile.workflows, errors)

        # 5. Validate mapping structure
        if profile.mappings:
            self._validate_mappings(profile.mappings, errors)

        return errors

    def validate_or_raise(self, profile: PortalProfile) -> None:
        """Validate and raise on first error.

        Raises:
            ProfileValidationError: If any validation error is found
        """
        errors = self.validate(profile)
        if errors:
            raise ProfileValidationError(
                f"Profile '{profile.id}' validation failed: {'; '.join(errors)}"
            )

    def is_valid(self, profile: PortalProfile) -> bool:
        """Quick validity check."""
        return len(self.validate(profile)) == 0

    def _validate_workflows(
        self, workflows: Dict[str, Any], errors: List[str]
    ) -> None:
        """Validate workflow definitions."""
        for name, workflow in workflows.items():
            if isinstance(workflow, dict):
                if "steps" not in workflow:
                    errors.append(f"Workflow '{name}' is missing 'steps'")
                elif not isinstance(workflow["steps"], list):
                    errors.append(f"Workflow '{name}'.steps should be a list")
            elif isinstance(workflow, str):
                pass  # External file reference is valid
            else:
                errors.append(f"Workflow '{name}' has invalid type")

    def _validate_mappings(
        self, mappings: Dict[str, Any], errors: List[str]
    ) -> None:
        """Validate field mappings."""
        for section_name, section in mappings.items():
            if isinstance(section, dict):
                for field_name, field_config in section.items():
                    if isinstance(field_config, dict):
                        if "selector" not in field_config:
                            errors.append(
                                f"Mapping '{section_name}.{field_name}' "
                                f"is missing 'selector'"
                            )
