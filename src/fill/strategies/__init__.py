"""InsureDesk — Fill Strategy Registry.

Maps FieldType -> FillStrategy class.
"""
from __future__ import annotations

from src.fill.schema import FieldType
from src.fill.strategies.base import FillStrategy
from src.fill.strategies.text import TextStrategy
from src.fill.strategies.textarea import TextAreaStrategy
from src.fill.strategies.select import SelectStrategy
from src.fill.strategies.radio import RadioStrategy
from src.fill.strategies.checkbox import CheckboxStrategy
from src.fill.strategies.date import DateStrategy
from src.fill.strategies.lookup import LookupStrategy
from src.fill.strategies.upload import UploadStrategy
from src.fill.strategies.hidden import HiddenStrategy
from src.fill.strategies.readonly import ReadOnlyStrategy

# Default strategy registry
DEFAULT_STRATEGIES: dict[FieldType, type[FillStrategy]] = {
    FieldType.TEXT: TextStrategy,
    FieldType.TEXTAREA: TextAreaStrategy,
    FieldType.SELECT: SelectStrategy,
    FieldType.RADIO: RadioStrategy,
    FieldType.CHECKBOX: CheckboxStrategy,
    FieldType.DATE: DateStrategy,
    FieldType.LOOKUP: LookupStrategy,
    FieldType.UPLOAD: UploadStrategy,
    FieldType.HIDDEN: HiddenStrategy,
    FieldType.READONLY: ReadOnlyStrategy,
}

__all__ = [
    "FillStrategy",
    "TextStrategy",
    "TextAreaStrategy",
    "SelectStrategy",
    "RadioStrategy",
    "CheckboxStrategy",
    "DateStrategy",
    "LookupStrategy",
    "UploadStrategy",
    "HiddenStrategy",
    "ReadOnlyStrategy",
    "DEFAULT_STRATEGIES",
]
