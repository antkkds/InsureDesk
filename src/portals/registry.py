"""InsureDesk — Portal Adapter Registry.

Central registry for discovering and loading portal adapters.
Supports both hardcoded registration and auto-discovery.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Any, Type

from src.portal.mapping import PortalMapping, load_portal_mapping
from src.browser.driver import BrowserEngine

# Lazy imports — adapters import from base so we defer to avoid circular imports
_ADAPTER_MAP: Dict[str, Type] = {}
_ADAPTER_MAP_LOCKED = False


def register_adapter(portal_id: str, adapter_cls: Type) -> None:
    """Register a portal adapter class.

    Args:
        portal_id: Unique identifier (e.g. 'great_eastern').
        adapter_cls: PortalAdapter subclass.

    Raises:
        ValueError: If portal_id is already registered.
    """
    if _ADAPTER_MAP_LOCKED:
        raise RuntimeError("Adapter registry is locked — cannot register after first use")
    if portal_id in _ADAPTER_MAP:
        raise ValueError(f"Adapter '{portal_id}' is already registered")
    _ADAPTER_MAP[portal_id] = adapter_cls


def lock_registry() -> None:
    """Lock the registry to prevent further modifications."""
    global _ADAPTER_MAP_LOCKED
    _ADAPTER_MAP_LOCKED = True


def _ensure_loaded():
    """Ensure default adapters are registered."""
    if not _ADAPTER_MAP:
        # Register known adapters
        from src.portals.great_eastern import GreatEasternAdapter
        from src.portals.aia import AIAAdapter
        from src.portals.allianz import AllianzAdapter

        for pid, cls in [
            ("great_eastern", GreatEasternAdapter),
            ("aia", AIAAdapter),
            ("allianz", AllianzAdapter),
        ]:
            if pid not in _ADAPTER_MAP:
                _ADAPTER_MAP[pid] = cls
        lock_registry()


def get_adapter(portal_id: str,
                mapping: Optional[PortalMapping] = None,
                engine: Optional[BrowserEngine] = None,
                login_url: Optional[str] = None):
    """Get a portal adapter instance by ID.

    Args:
        portal_id: Portal identifier (e.g. 'great_eastern', 'aia').
        mapping: Optional pre-loaded PortalMapping. Auto-loaded if None.
        engine: Optional BrowserEngine instance.
        login_url: Optional DB Portal.login_url override (takes priority).

    Returns:
        PortalAdapter instance, or None if not found.
    """
    _ensure_loaded()
    adapter_cls = _ADAPTER_MAP.get(portal_id)
    if not adapter_cls:
        return None
    if mapping is None:
        mapping = load_portal_mapping(portal_id)
    return adapter_cls(mapping=mapping, engine=engine, login_url=login_url)


def list_adapters() -> List[Dict[str, Any]]:
    """List all available portal adapters.

    Returns:
        List of dicts with adapter metadata (name, short_name, portals_count).
    """
    _ensure_loaded()
    result = []
    for pid, cls in _ADAPTER_MAP.items():
        try:
            mapping = load_portal_mapping(pid)
            name = mapping.name if mapping else pid
        except Exception:
            name = pid
        result.append({
            "id": pid,
            "name": name,
            "adapter_class": cls.__name__,
        })
    return result
