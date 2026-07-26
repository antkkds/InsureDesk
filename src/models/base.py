"""InsureDesk — Base Model.

Shared base class for all domain models.
Provides serialization (to_dict/from_dict) and validation helpers.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, List, Type, TypeVar, Union
from datetime import date, datetime
from dataclasses import dataclass, fields, asdict
from enum import Enum

T = TypeVar("T", bound="BaseModel")


def _serialize_value(v: Any) -> Any:
    """Serialize a value for dict/JSON output."""
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, BaseModel):
        return v.to_dict()
    if isinstance(v, list):
        return [_serialize_value(x) for x in v]
    if isinstance(v, dict):
        return {k: _serialize_value(x) for k, x in v.items()}
    return v


def _deserialize_value(v: Any, target_type: Any) -> Any:
    """Deserialize a value from dict/JSON input."""
    if v is None:
        return None

    # Unwrap Optional[Type] → Type (Optional[X] is Union[X, None])
    origin = getattr(target_type, "__origin__", None)
    args = getattr(target_type, "__args__", ())
    if origin is Union:
        # Pick the non-None type from Union[X, None]
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            target_type = non_none[0]
            # Re-extract origin and args for the unwrapped type
            origin = getattr(target_type, "__origin__", None)
            args = getattr(target_type, "__args__", ())

    # Date/datetime
    if target_type is date and isinstance(v, str):
        return date.fromisoformat(v)
    if target_type is datetime and isinstance(v, str):
        return datetime.fromisoformat(v)

    # Enum
    if isinstance(target_type, type) and issubclass(target_type, Enum) and isinstance(v, str):
        try:
            return target_type(v)
        except ValueError:
            return target_type(v.replace(" ", "_"))  # fuzzy match "in force" → "in_force"

    # Nested BaseModel
    if isinstance(v, dict) and hasattr(target_type, "from_dict"):
        return target_type.from_dict(v)

    # List of BaseModel
    if origin is list and args and isinstance(v, list):
        item_type = args[0]
        if hasattr(item_type, "from_dict"):
            return [_deserialize_value(x, item_type) for x in v]

    return v


@dataclass
class BaseModel:
    """Base class for all domain models.

    Provides:
    - to_dict() — recursive serialization to plain dict
    - to_json() — JSON string output
    - from_dict() — classmethod for deserialization
    """

    def to_dict(self) -> Dict[str, Any]:
        """Recursively serialize to plain dict (JSON-safe)."""
        result = {}
        for f in fields(self):
            value = getattr(self, f.name)
            result[f.name] = _serialize_value(value)
        return result

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """Create instance from dict, handling nested models."""
        # Resolve type hints (handles `from __future__ import annotations`)
        try:
            import typing
            hints = typing.get_type_hints(cls)
        except Exception:
            hints = {f.name: f.type for f in fields(cls)}

        kwargs = {}
        for key, value in data.items():
            if key in hints:
                kwargs[key] = _deserialize_value(value, hints[key])
        return cls(**kwargs)

    def __str__(self) -> str:
        """Human-readable summary."""
        items = []
        for f in fields(self):
            v = getattr(self, f.name)
            if v is not None and v != "" and v != []:
                if isinstance(v, BaseModel):
                    items.append(f"{f.name}=<{type(v).__name__}>")
                elif isinstance(v, list) and v and isinstance(v[0], BaseModel):
                    items.append(f"{f.name}=[{len(v)} items]")
                else:
                    s = str(v)
                    items.append(f"{f.name}={s[:60]}")
        return f"{type(self).__name__}({', '.join(items)})"
