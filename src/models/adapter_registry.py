"""ModelAdapter registry — get adapter by portal name."""

from typing import Optional
from src.models.adapter_base import ModelAdapter
from src.models.adapter_ge import GreatEasternAdapter, GreatEasternPDFAdapter
from src.models.adapter_allianz import AllianzAdapter
from src.models.adapter_aia import AIAAdapter


_ADAPTERS = {
    "great_eastern": GreatEasternAdapter,
    "ge": GreatEasternAdapter,
    "allianz": AllianzAdapter,
    "aia": AIAAdapter,
    "great_eastern_pdf": GreatEasternPDFAdapter,
    "ge_pdf": GreatEasternPDFAdapter,
}


def get_model_adapter(portal_name: str, source: str = "portal") -> Optional[ModelAdapter]:
    """Get a ModelAdapter by portal name.

    Args:
        portal_name: Portal identifier (e.g. "great_eastern", "allianz", "aia")
        source: "portal" or "pdf"
    Returns:
        ModelAdapter instance or None if not found
    """
    key = portal_name.lower().replace(" ", "_")
    if source == "pdf":
        key = f"{key}_pdf"

    cls = _ADAPTERS.get(key)
    if cls:
        return cls()
    return None


def list_model_adapters() -> list[dict]:
    """List all available model adapters."""
    seen = set()
    result = []
    for key, cls in _ADAPTERS.items():
        if cls not in seen:
            seen.add(cls)
            inst = cls()
            result.append({
                "name": inst.name,
                "type": "pdf" if "pdf" in key else "portal",
                "key": key,
            })
    return result
