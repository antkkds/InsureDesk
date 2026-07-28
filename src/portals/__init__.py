"""InsureDesk — Portal Adapters.

Portal Adapter Framework 2.0 (Sprint 5.1):
- PortalAdapter base class with unified contract
- AdapterRegistry with auto-discovery
- Concrete adapters for each insurance portal
"""
from __future__ import annotations

# Re-export from base adapter (backward compatible)
from src.portals.base import (
    PortalAdapter,
    PortalCredentials,
    GreatEasternAdapter,
    AllianzAdapter,
    AIAAdapter,
)

# Re-export from registry
from src.portals.registry import (
    get_adapter,
    list_adapters,
    register_adapter,
)

__all__ = [
    "PortalAdapter",
    "PortalCredentials",
    "GreatEasternAdapter",
    "AllianzAdapter",
    "AIAAdapter",
    "get_adapter",
    "list_adapters",
    "register_adapter",
]
