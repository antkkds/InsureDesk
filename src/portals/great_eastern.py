"""Great Eastern Malaysia (GEGLink) Portal Adapter.

Concrete adapter for Great Eastern General Insurance's GEGLink portal.
Uses YAML-based selector mapping from portals/great_eastern.yaml.
"""
from __future__ import annotations

from src.portals.base import PortalAdapter


class GreatEasternAdapter(PortalAdapter):
    """Great Eastern Malaysia (GEGLink) Portal Adapter.

    Features:
    - Username/password login with image-based submit button
    - Policy search and details extraction
    - Claims submission and status checking
    - Document upload
    - Policy renewal
    """

    @property
    def adapter_name(self) -> str:
        return "great_eastern"
