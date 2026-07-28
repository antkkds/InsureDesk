"""Allianz Malaysia (Life e-Service) Portal Adapter.

Concrete adapter for Allianz Malaysia's Life e-Service portal.
Uses YAML-based selector mapping from portals/allianz.yaml.
"""
from __future__ import annotations

from src.portals.base import PortalAdapter


class AllianzAdapter(PortalAdapter):
    """Allianz Malaysia (Life e-Service) Portal Adapter.

    Features:
    - Username/password login
    - Policy search and details extraction
    - Claims submission
    - Document upload
    """

    @property
    def adapter_name(self) -> str:
        return "allianz"
