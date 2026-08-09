"""InsureDesk — Portal Mapping & Profile System.

Two-layer config:
- portals/<adapter>.yaml — portal metadata (name, URLs, adapter class)
- profiles/<profile>.yaml  — portal/quote selectors (captured elements)

Usage:
    # Portal metadata
    mapping = load_portal_mapping("great_eastern")  # portals/great_eastern.yaml
    mapping.login_url  # "https://..."

    # Portal selectors (from profile)
    profile = load_portal_profile("geglink")  # profiles/geglink.yaml
    profile.get_selector("login", "username")  # "input[name='oac_username']"

    # Quote selectors (from profile)
    ife = load_quote_profile("great_eastern", "IFE")  # profiles/ife_quote.yaml
    ife.get_selector("quote_form", "example_field")  # None (not captured yet)
"""

from __future__ import annotations

import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════
# Paths
# ══════════════════════════════════════════════════════════════════

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
PORTALS_DIR = ROOT_DIR / "portals"
PROFILES_DIR = ROOT_DIR / "profiles"


# ══════════════════════════════════════════════════════════════════
# Portal Mapping (metadata)
# ══════════════════════════════════════════════════════════════════

@dataclass
class PortalMapping:
    """Portal metadata from YAML."""
    name: str = ""
    short_name: str = ""
    base_url: str = ""
    login_url: str = ""
    login_action: str = ""
    adapter: str = ""
    profile: str = ""           # references profiles/<name>.yaml
    selectors: dict = None      # legacy: inline selectors (migration support)


def load_portal_mapping(adapter_name: str) -> Optional[PortalMapping]:
    """Load portal metadata from portals/<adapter_name>.yaml."""
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
        login_action=p.get("login_action", ""),
        adapter=p.get("adapter", adapter_name),
        profile=p.get("profile", ""),
        selectors=data.get("selectors"),
    )


def get_selector(mapping: PortalMapping, *path: str) -> Optional[str]:
    """Get a selector from portal mapping by path. (Legacy, prefer ProfileData.)

    Args:
        mapping: PortalMapping instance.
        *path: Selector path, e.g. ('login', 'username').

    Returns:
        Selector string or None.
    """
    if not mapping or not mapping.selectors:
        return None
    current = mapping.selectors
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current if isinstance(current, str) else None


def list_available_portals() -> List[Dict[str, Any]]:
    """List all available portal YAML files."""
    portals = []
    if not PORTALS_DIR.exists():
        return portals
    for yf in sorted(PORTALS_DIR.glob("*.yaml")):
        with open(yf) as f:
            data = yaml.safe_load(f)
        if data and "portal" in data:
            p = data["portal"]
            portals.append({
                "file": yf.name,
                "adapter": p.get("adapter", yf.stem),
                "name": p.get("name", yf.stem),
                "short_name": p.get("short_name", ""),
                "has_adapter": True,
                "has_profile": bool(p.get("profile")),
            })
    return portals


# ══════════════════════════════════════════════════════════════════
# Portal Profile (selectors from capture)
# ══════════════════════════════════════════════════════════════════

@dataclass
class ProfileData:
    """A captured portal/quote profile from profiles/<name>.yaml.

    Contains page definitions and their captured element selectors.
    Loaded by load_portal_profile() / load_quote_profile().
    Distinct from capture.ProfileData (which is the capture output model).
    """
    version: str = "1.0"
    portal: str = ""
    quote_channel: str = ""     # "IFE", "EQ", or "" for portal profile
    pages: Dict[str, Dict] = field(default_factory=dict)

    def get_selector(self, page: str, field: str) -> Optional[str]:
        """Get the best selector for a field on a page.

        Args:
            page: Page name, e.g. "login", "quote_form"
            field: Field key, e.g. "username", "sum_insured"

        Returns:
            Selector string or None.
        """
        page_data = self.pages.get(page)
        if not page_data:
            return None
        elements = page_data.get("elements", {})
        el = elements.get(field)
        if not el:
            return None
        return el.get("best_selector") or el.get("selector")

    def get_element(self, page: str, field: str) -> Optional[Dict]:
        """Get full element metadata for a field."""
        page_data = self.pages.get(page)
        if not page_data:
            return None
        elements = page_data.get("elements", {})
        return elements.get(field)

    def list_fields(self, page: str) -> List[str]:
        """List all field keys on a page."""
        page_data = self.pages.get(page)
        if not page_data:
            return []
        return list(page_data.get("elements", {}).keys())

    def list_pages(self) -> List[str]:
        return list(self.pages.keys())

    def to_dict(self) -> Dict:
        return {
            "version": self.version,
            "portal": self.portal,
            "quote_channel": self.quote_channel,
            "pages": self.pages,
        }


def load_portal_profile(profile_name: str) -> Optional[ProfileData]:
    """Load a profile from profiles/<profile_name>.yaml.

    Profile names: "geglink", "ife_quote", "eq_quote", etc.
    """
    yaml_path = PROFILES_DIR / f"{profile_name}.yaml"
    if not yaml_path.exists():
        return None

    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    if not data:
        return None

    return ProfileData(
        version=data.get("version", "1.0"),
        portal=data.get("portal", ""),
        quote_channel=data.get("quote_channel", ""),
        pages=data.get("pages", {}),
    )


def load_quote_profile(portal: str, channel: str) -> Optional[ProfileData]:
    """Load a quote profile by portal and channel.

    Args:
        portal: Portal adapter name, e.g. "great_eastern"
        channel: Quote channel, e.g. "IFE", "EQ"

    Returns:
        ProfileData or None.
    """
    profile_name = f"{channel.lower()}_quote"
    return load_portal_profile(profile_name)


def list_available_profiles() -> List[Dict[str, Any]]:
    """List all available profile files."""
    profiles = []
    if not PROFILES_DIR.exists():
        return profiles
    for yf in sorted(PROFILES_DIR.glob("*.yaml")):
        with open(yf) as f:
            data = yaml.safe_load(f)
        if data:
            profiles.append({
                "file": yf.name,
                "profile": yf.stem,
                "portal": data.get("portal", ""),
                "quote_channel": data.get("quote_channel", ""),
                "version": data.get("version", "1.0"),
                "pages": list(data.get("pages", {}).keys()),
            })
    return profiles
