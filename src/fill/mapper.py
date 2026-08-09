"""InsureDesk — Field Mapper.

Converts domain objects (dataclass/Pydantic) into flat dicts
keyed by field name, suitable for FillEngine consumption.

The mapper performs no browser interaction — pure data transformation.
"""
from __future__ import annotations

from typing import Any
from dataclasses import fields as dataclass_fields


class FieldMapper:
    """Maps domain objects to field-value dicts.

    Usage:
        mapper = FieldMapper()
        data = mapper.map(customer_obj, {
            "customer_name": "full_name",
            "gender": "gender",
        })
        # -> {"customer_name": "John", "gender": "MALE"}
    """

    def map(
        self,
        obj: Any,
        field_map: dict[str, str],
    ) -> dict[str, Any]:
        """Map domain object fields to portal field values.

        Args:
            obj: Domain object (dataclass).
            field_map: Dict mapping portal field name -> object attribute name.

        Returns:
            Dict of portal field name -> value.
        """
        result: dict[str, Any] = {}
        for portal_field, attr_name in field_map.items():
            value = self._get_attr(obj, attr_name)
            if value is not None:
                result[portal_field] = value
        return result

    def map_with_schema(
        self,
        obj: Any,
        schema_fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Map domain object using schema field definitions.

        Derives field_map automatically from schema field names vs
        object attributes (uses the same name if not explicitly mapped).

        Args:
            obj: Domain object.
            schema_fields: Dict of field_name -> FieldDefinition.

        Returns:
            Dict of field name -> value.
        """
        result: dict[str, Any] = {}
        for field_name in schema_fields:
            value = self._get_attr(obj, field_name)
            if value is not None:
                result[field_name] = value
        return result

    def _get_attr(self, obj: Any, name: str) -> Any:
        """Get an attribute from an object, supporting nested paths."""
        if isinstance(obj, dict):
            return obj.get(name)
        return getattr(obj, name, None)
