"""AIA Malaysia (e-Care) Portal Adapter.

Concrete adapter for AIA Malaysia's e-Care portal.
Uses YAML-based selector mapping from portals/aia.yaml.
"""
from __future__ import annotations

from src.portals.base import PortalAdapter


class AIAAdapter(PortalAdapter):
    """AIA Malaysia (e-Care) Portal Adapter.

    Features:
    - Username/password login
    - Policy search and details extraction
    - Claims submission
    """

    @property
    def adapter_name(self) -> str:
        return "aia"
