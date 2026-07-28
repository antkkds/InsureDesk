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
    navigation: dict = None
    schemas: dict = None
    transformers: dict = None


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
        navigation=data.get("navigation", {}),
        schemas=data.get("schemas", {}),
        transformers=data.get("transformers", {}),
    )


def get_selector(mapping: PortalMapping, *path: str) -> Optional[str]:
    """Get a selector by path.

    Supports both formats:
      - Simple string: get_selector(m, 'login', 'username') -> "input[name='...']"
      - Dict with metadata: get_selector(m, 'quotation', 'product_select')
        -> "#productSelect" (extracts 'selector' key from dict)

    Args:
        mapping: PortalMapping instance.
        *path: Key path, e.g. ('login', 'username') or ('quotation', 'fields', 'sum_insured').

    Returns:
        CSS selector string, or None if not found.
    """
    if not mapping or not mapping.selectors:
        return None
    current = mapping.selectors
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    # String value -> return directly
    if isinstance(current, str):
        return current
    # Dict with 'selector' key -> extract it
    if isinstance(current, dict) and "selector" in current:
        return current["selector"]
    return None


def get_field_def(mapping: PortalMapping, field_name: str) -> Optional[dict]:
    """Get the full field definition for a quotation field.

    Args:
        mapping: PortalMapping instance.
        field_name: Field name (e.g. 'sum_insured_building').

    Returns:
        Dict with 'selector', 'type', 'required', etc., or None.
    """
    if not mapping or not mapping.selectors:
        return None
    fields = mapping.selectors.get("quotation", {}).get("fields", {})
    return fields.get(field_name)


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
