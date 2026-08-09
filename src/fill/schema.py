"""InsureDesk — Fill Schema Models.

Defines the YAML-driven field schema for portal forms.
Each field maps a logical name to a browser selector + type + behavior.
"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class FieldType(str, Enum):
    """Supported field input types."""
    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    DATE = "date"
    LOOKUP = "lookup"
    UPLOAD = "upload"
    HIDDEN = "hidden"
    READONLY = "readonly"

    @classmethod
    def _missing_(cls, value: str) -> "FieldType":
        """Case-insensitive fallback."""
        value_lower = value.lower()
        for member in cls:
            if member.value == value_lower:
                return member
        raise ValueError(f"'{value}' is not a valid FieldType")


@dataclass
class FieldDefinition:
    """Definition of a single form field.

    Loaded from YAML portal config:
        field_name:
          selector: "#cssSelector"
          type: text              # One of FieldType values
          required: false
          verify: true
          retry: 2
          clear_first: true
          timeout: 5000
          transform: uppercase    # Transformer name
          format: "%d/%m/%Y"     # Date format (for date fields)
          options: {}             # Extra options per strategy
          max_length: 100         # Text field max length
    """
    name: str = ""
    selector: str = ""
    type: FieldType = FieldType.TEXT
    required: bool = False
    verify: bool = True
    retry: int = 2
    clear_first: bool = True
    timeout: int = 5000
    transform: Optional[str] = None
    format: Optional[str] = None
    options: dict = field(default_factory=dict)
    max_length: Optional[int] = None


@dataclass
class FillSchema:
    """Schema for a form section (e.g., customer, risk, coverage).

    Loaded from YAML portal config:
        schemas:
          customer:
            customer_name:
              selector: "#customerName"
              type: text
              required: true
            gender:
              selector: "#gender"
              type: radio
              transform: gender
    """
    name: str = ""
    fields: dict[str, FieldDefinition] = field(default_factory=dict)


def fill_schema_from_dict(name: str, data: dict) -> FillSchema:
    """Build a FillSchema from a parsed YAML dictionary.

    Args:
        name: Section name (e.g., 'customer').
        data: Raw dict from YAML, keyed by field name.

    Returns:
        FillSchema with FieldDefinition objects.
    """
    fields: dict[str, FieldDefinition] = {}
    for field_name, raw in data.items():
        if not isinstance(raw, dict):
            raw = {"selector": str(raw)}
        raw.setdefault("name", field_name)
        raw.setdefault("type", "text")

        # Convert type string to FieldType enum
        ft = raw.get("type", "text")
        if isinstance(ft, str):
            try:
                raw["type"] = FieldType(ft)
            except ValueError:
                raw["type"] = FieldType.TEXT

        fields[field_name] = FieldDefinition(**raw)

    return FillSchema(name=name, fields=fields)


def schemas_from_yaml(yaml_data: dict) -> dict[str, FillSchema]:
    """Parse all schemas from a portal YAML's 'schemas' section.

    Args:
        yaml_data: Full YAML data dict.

    Returns:
        Dict mapping section name -> FillSchema.
    """
    raw_schemas = yaml_data.get("schemas", {})
    if not raw_schemas:
        return {}

    return {
        name: fill_schema_from_dict(name, data)
        for name, data in raw_schemas.items()
        if isinstance(data, dict)
    }
