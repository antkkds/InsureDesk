"""InsureDesk — Value Transformer.

Transforms domain-model values into portal-specific values.
Mappings are defined in YAML config, not Python code.

Example YAML:
    transformers:
      gender:
        MALE: M
        FEMALE: F
      occupation:
        ENGINEER: "002"
        TEACHER: "018"
"""
from __future__ import annotations

from typing import Any, Optional, Callable

from src.fill.exceptions import TransformationError


class TransformerRegistry:
    """Registry of named value transformers.

    Each transformer is a dict mapping domain_value -> portal_value.
    Built-in functions (uppercase, lowercase, trim) are also supported.
    """

    def __init__(self, transformers: dict[str, dict[str, Any] | Callable] | None = None):
        self._transformers: dict[str, dict[str, Any] | Callable] = {}
        self._builtins: dict[str, Callable] = {
            "uppercase": lambda v: v.upper() if isinstance(v, str) else v,
            "lowercase": lambda v: v.lower() if isinstance(v, str) else v,
            "trim": lambda v: v.strip() if isinstance(v, str) else v,
        }
        if transformers:
            self._transformers.update(transformers)

    def register(self, name: str, mapping: dict[str, Any] | Callable):
        """Register a transformer by name."""
        self._transformers[name] = mapping

    def register_from_yaml(self, data: dict[str, dict[str, Any]]):
        """Load transformers from YAML dict."""
        for name, mapping in data.items():
            if isinstance(mapping, dict):
                self._transformers[name] = mapping

    def transform(self, name: str, value: Any) -> Any:
        """Transform a value using the named transformer.

        Args:
            name: Transformer name (e.g., 'gender', 'uppercase').
            value: Domain value to transform.

        Returns:
            Transformed value.

        Raises:
            TransformationError: If transformer not found or mapping fails.
        """
        # Built-in functions first
        if name in self._builtins:
            return self._builtins[name](value)

        # Dict mapping
        if name in self._transformers:
            mapping = self._transformers[name]
            if isinstance(mapping, dict):
                if value in mapping:
                    return mapping[value]
                raise TransformationError(
                    message=f"No mapping for value '{value}' in transformer '{name}'",
                    field="",
                )
            # Callable
            return mapping(value)

        raise TransformationError(
            message=f"Unknown transformer: {name}",
            field="",
        )

    def has(self, name: str) -> bool:
        """Check if a transformer exists."""
        return name in self._transformers or name in self._builtins
