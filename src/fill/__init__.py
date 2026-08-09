"""InsureDesk — Fill Engine.

The Fill Engine is responsible for populating web portal forms
using YAML-defined field schemas and strategy-based interaction patterns.

Architecture:
    FillEngine.fill_section()
        → FieldMapper.map()           # Domain object → dict
        → Transformer.transform()     # Domain values → portal values
        → Strategy.fill()             # Browser interaction
        → Verifier.verify()           # Post-fill verification
        → FillResult                  # Result object
"""

from src.fill.engine import FillEngine
from src.fill.schema import FillSchema, FieldDefinition, FieldType
from src.fill.result import FillResult, FieldResult
from src.fill.mapper import FieldMapper
from src.fill.transformer import TransformerRegistry

__all__ = [
    "FillEngine",
    "FillSchema",
    "FieldDefinition",
    "FieldType",
    "FillResult",
    "FieldResult",
    "FieldMapper",
    "TransformerRegistry",
]
