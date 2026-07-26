"""InsureDesk — Portal Mapping System.

Loads YAML-based selector configs for each insurer portal.
Mappings are stored in ~/InsureDesk/portals/<adapter>.yaml
When an insurer changes UI, update the YAML — no code changes.
"""

import os
import yaml
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass


PORTALS_DIR = Path(__file__).resolve().parent.parent.parent / "portals"


@dataclass
class PortalMapping:
    """Loaded portal mapping from YAML."""
    name: str = ""
    short_name: str = ""
    base_url: str = ""
    login_url: str = ""
    adapter: str = ""
    selectors: dict = None


def load_portal_mapping(adapter_name: str) -> Optional[PortalMapping]:
    """Load a portal mapping from YAML file."""
    yaml_path = PORTALS_DIR / f"{adapter_name}.yaml"
    if not yaml_path.exists():
        return None

    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    if not data or "portal" not in data:
        return None

    p = data["portal"]
    return PortalMapping(
        name=p.get("name", ""),
        short_name=p.get("short_name", ""),
        base_url=p.get("base_url", ""),
        login_url=p.get("login_url", ""),
        adapter=p.get("adapter", adapter_name),
        selectors=data.get("selectors", {}),
    )


def get_selector(mapping: PortalMapping, *path: str) -> Optional[str]:
    """Get a selector by path. E.g., get_selector(m, 'login', 'username')."""
    if not mapping or not mapping.selectors:
        return None
    current = mapping.selectors
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current if isinstance(current, str) else None


def list_available_portals() -> list:
    """List all YAML portal configs available."""
    if not PORTALS_DIR.exists():
        return []
    files = sorted(PORTALS_DIR.glob("*.yaml"))
    portals = []
    for f in files:
        with open(f, "r") as fh:
            data = yaml.safe_load(fh)
        if data and "portal" in data:
            p = data["portal"]
            portals.append({
                "name": p.get("name", f.stem),
                "short_name": p.get("short_name", f.stem),
                "adapter": p.get("adapter", f.stem),
                "file": f.name,
            })
    return portals
