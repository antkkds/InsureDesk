"""Portal Validation Engine — YAML Rule Loader.

Loads validation rule configurations from YAML files
and registers them with the ValidationRuleRegistry.

Example YAML:
    portal: great_eastern
    validation:
      create_quote:
        rules:
          - id: age_limit
            type: age
            severity: ERROR
            min: 18
            max: 65
          - id: ic_check
            type: ic
            severity: ERROR
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.portal.validation.models import RuleDefinition
from src.portal.validation.registry import ValidationRuleRegistry
from src.portal.validation.exceptions import ValidationConfigError

logger = logging.getLogger("insuredesk.validation.loader")

# Try to import yaml; fall back to a simple message
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


class ValidationLoader:
    """Loads validation rules from YAML config files.

    Usage:
        loader = ValidationLoader(registry)
        loader.load_file("configs/validation/great_eastern.yaml")
        loader.load_directory("configs/validation/")
    """

    def __init__(self, registry: ValidationRuleRegistry):
        self._registry = registry
        self._loaded_files: set[str] = set()

    def load_file(self, path: str) -> int:
        """Load validation rules from a YAML file.

        Args:
            path: Path to the YAML file

        Returns:
            Number of rules loaded

        Raises:
            ValidationConfigError: If the file is invalid
        """
        if yaml is None:
            raise ValidationConfigError(
                "PyYAML is required to load validation configs. "
                "Install it with: pip install pyyaml"
            )

        path = os.path.expanduser(path)
        if not os.path.exists(path):
            raise ValidationConfigError(f"Validation config not found: {path}")

        with open(path) as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValidationConfigError(f"Invalid YAML in {path}: {e}")

        if not data or "validation" not in data:
            logger.warning("No validation rules in %s", path)
            return 0

        portal = data.get("portal", "unknown")
        validation = data["validation"]
        count = 0

        for action, config in validation.items():
            rules = config.get("rules", [])
            for rule_def in rules:
                rule_id = rule_def.get("id", f"rule_{count}")
                rule_type = rule_def.get("type", "")
                severity = rule_def.get("severity", "error")
                field = rule_def.get("field")

                # Create rule definition for later instantiation
                params = {k: v for k, v in rule_def.items()
                         if k not in ("id", "type", "severity", "field")}

                # Try to create the rule if the type is registered
                if self._registry.has_type(rule_type):
                    rule_class = self._registry.get_type(rule_type)
                    rule = rule_class(
                        id=rule_id,
                        name=rule_id,
                        category="business",
                        severity=severity.lower(),
                        field=field,
                        metadata={"message": params.pop("message", "")},
                    )
                    # Set type-specific params
                    for k, v in params.items():
                        if hasattr(rule, k):
                            setattr(rule, k, v)
                        else:
                            rule.metadata[k] = v

                    self._registry.add_rule(rule)
                    self._registry.add_portal_rule(portal, action, rule_id)
                    count += 1
                else:
                    # Store as definition for later instantiation
                    logger.warning(
                        "Rule type '%s' not registered, skipping rule '%s' in %s",
                        rule_type, rule_id, path,
                    )

        self._loaded_files.add(os.path.abspath(path))
        logger.info("Loaded %d rules from %s (portal=%s)", count, path, portal)
        return count

    def load_directory(self, directory: str) -> int:
        """Load all YAML files from a directory.

        Args:
            directory: Path to directory containing YAML files

        Returns:
            Total number of rules loaded
        """
        directory = os.path.expanduser(directory)
        if not os.path.isdir(directory):
            raise ValidationConfigError(f"Directory not found: {directory}")

        total = 0
        for filename in sorted(os.listdir(directory)):
            if filename.endswith((".yaml", ".yml")):
                path = os.path.join(directory, filename)
                total += self.load_file(path)

        return total

    def loaded_files(self) -> List[str]:
        """Return paths of all loaded files."""
        return list(self._loaded_files)
