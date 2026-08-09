"""InsureDesk — Field Mapper.

Maps domain-level insurance fields to portal form fields using YAML profiles.
This separates the tool/domain layer from portal-specific HTML structure.

Domain fields (used by tools):
    proposer_name, proposer_ic, sum_insured, risk_class, building_type, etc.

Portal fields (from YAML profiles):
    f_insured_name, f_add1, cmbOccupancyType, txtSumInsured, etc.

Usage:
    mapper = FieldMapper("profiles/ife_quote.yaml")
    portal_fields = mapper.map_to_portal({
        "proposer_name": "Tiong Hoe Hung",
        "sum_insured": 5000000,
        "occupancy": "Factory",
    })
"""

from __future__ import annotations

from typing import Dict, Any, Optional, List
from pathlib import Path
import yaml


# ══════════════════════════════════════════════════════════════════
# Domain-to-Portal field mapping
# ══════════════════════════════════════════════════════════════════

# Maps domain field names to portal field keys from YAML profiles.
# Each mapping has:
#   portal_key: the YAML element key (before the colon in the profile)
#   transform: optional value transformation
#   default: optional default value

FIELD_MAPPINGS: Dict[str, Dict[str, Any]] = {
    # Policy holder
    "proposer_name": {"portal_key": "*.jpj_f_q_insured_name"},
    "proposer_ic": {"portal_key": "*.jpj_f_q_ic_new"},
    "proposer_email": {"portal_key": "*.jpj_f_q_email"},
    "proposer_phone": {"portal_key": "*.jpj_f_q_mobile_no"},

    # Address
    "address_line_1": {"portal_key": "*.jpj_f_q_add1"},
    "address_line_2": {"portal_key": "*.jpj_f_q_add2"},
    "address_line_3": {"portal_key": "*.jpj_f_q_add3"},
    "address_postcode": {"portal_key": "*.jpj_f_q_postcode"},
    "address_city": {"portal_key": "*.jpj_f_q_city"},
    "address_state": {"portal_key": "*.jpj_f_q_state"},

    # Coverage
    "sum_insured": {"portal_key": "*.jpj_f_q_si_fc"},
    "building_sum_insured": {"portal_key": "*.jpj_f_q_si_building"},
    "content_sum_insured": {"portal_key": "*.jpj_f_q_si_content"},
    "stock_sum_insured": {"portal_key": "*.jpj_f_q_si_stock"},

    # Risk details
    "occupancy": {"portal_key": "*.jpj_f_q_occupancy"},
    "occupation": {"portal_key": "*.jpj_f_q_occupation"},
    "construction": {"portal_key": "*.jpj_f_q_construction"},
    "building_structure": {"portal_key": "*.jpj_f_q_building_structure"},
    "year_built": {"portal_key": "*.jpj_f_q_year_built"},
    "num_floors": {"portal_key": "*.jpj_f_q_no_of_floors"},
    "building_area": {"portal_key": "*.jpj_f_q_build_area"},

    # Period
    "cover_start_date": {"portal_key": "*.jpj_f_q_cov_start_date"},
    "cover_end_date": {"portal_key": "*.jpj_f_q_cov_end_date"},
    "cover_years": {"portal_key": "*.jpj_f_q_cover_year"},
}


# ══════════════════════════════════════════════════════════════════
# Portal-specific overrides
# ══════════════════════════════════════════════════════════════════

# Some portals use different field names.
# Override the generic mapping per quote channel.

PORTAL_OVERRIDES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "IFE": {
        "sum_insured": {"portal_key": "*.jpj_f_q_si_fc"},
        "building_sum_insured": {"portal_key": "*.jpj_f_q_si_building"},
        "content_sum_insured": {"portal_key": "*.jpj_f_q_si_content"},
        "occupancy": {"portal_key": "*.jpj_f_q_occupancy"},
        "occupation": {"portal_key": "*.jpj_f_q_occupation"},
    },
    "EQ": {
        # EQ uses different field names — TBD from profile
    },
}


# ══════════════════════════════════════════════════════════════════
# FieldMapper
# ══════════════════════════════════════════════════════════════════


class FieldMapper:
    """Maps domain fields to portal form fields.

    Uses YAML profiles to know which selectors/fields exist,
    and FIELD_MAPPINGS to translate domain names to portal keys.

    Args:
        profile_path: Path to YAML profile for the quote channel.
        channel_type: "IFE" or "EQ" for portal-specific overrides.
    """

    def __init__(self, profile_path: Optional[str] = None,
                 channel_type: str = "IFE"):
        self.channel_type = channel_type.upper()
        self._profile: Optional[dict] = None
        self._elements: Dict[str, dict] = {}

        if profile_path:
            self.load_profile(profile_path)

    def load_profile(self, profile_path: str) -> None:
        """Load a YAML profile."""
        path = Path(profile_path)
        if not path.exists():
            raise FileNotFoundError(f"Profile not found: {profile_path}")

        with open(path, "r") as f:
            self._profile = yaml.safe_load(f)

        # Extract elements from profile
        pages = self._profile.get("pages", {})
        for page_name, page_data in pages.items():
            elements = page_data.get("elements", {})
            self._elements.update(elements)

    @property
    def elements(self) -> Dict[str, dict]:
        """All available form elements from the profile."""
        return dict(self._elements)

    @property
    def element_count(self) -> int:
        return len(self._elements)

    def get_selector(self, portal_key: str) -> Optional[str]:
        """Get CSS selector for a portal field key.

        The portal_key is matched by suffix (last part after .)
        because YAML keys have prefix like 'fire.jpj_f_q_insured_name'.
        """
        for key, info in self._elements.items():
            if key.endswith(portal_key) or key == portal_key:
                return info.get("selector")
        return None

    def map_to_portal(self, domain_data: Dict[str, Any]) -> Dict[str, Any]:
        """Map domain fields to portal fields.

        Args:
            domain_data: Dict of domain field names and values.

        Returns:
            Dict of {portal_selector: value} ready for form filling.
        """
        mappings = dict(FIELD_MAPPINGS)

        # Apply portal-specific overrides
        portal_overrides = PORTAL_OVERRIDES.get(self.channel_type, {})
        mappings.update(portal_overrides)

        result = {}
        unmapped = []

        for domain_key, value in domain_data.items():
            if value is None or value == "":
                continue

            mapping = mappings.get(domain_key)
            if not mapping:
                unmapped.append(domain_key)
                continue

            portal_pattern = mapping["portal_key"]
            # Resolve wildcard to actual selector
            selector = self._resolve_portal_key(portal_pattern)
            if selector:
                result[selector] = str(value)
            else:
                unmapped.append(domain_key)

        return result

    def map_to_domain(self, portal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Reverse map: portal field values → domain fields.

        Args:
            portal_data: Dict of {portal_key: value} from form reading.

        Returns:
            Dict of domain field names and values.
        """
        # Build reverse mapping
        reverse_map = {}
        mappings = dict(FIELD_MAPPINGS)
        portal_overrides = PORTAL_OVERRIDES.get(self.channel_type, {})
        mappings.update(portal_overrides)

        for domain_key, mapping in mappings.items():
            portal_pattern = mapping["portal_key"]
            reverse_map[portal_pattern] = domain_key

        result = {}
        for portal_key, value in portal_data.items():
            # Find domain key by matching portal pattern
            domain_key = None
            for pattern, dk in reverse_map.items():
                pattern_clean = pattern.replace("*.", "")
                if portal_key.endswith(pattern_clean) or portal_key == pattern:
                    domain_key = dk
                    break

            if domain_key:
                result[domain_key] = value

        return result

    def _resolve_portal_key(self, pattern: str) -> Optional[str]:
        """Resolve a pattern like '*.jpj_f_q_insured_name' to a CSS selector.

        The wildcard * matches any prefix (e.g. 'fire.jpj_f_q_insured_name').
        """
        if pattern.startswith("*."):
            suffix = pattern[2:]
            for key, info in self._elements.items():
                if key.endswith(suffix):
                    return info.get("selector")
            return None
        else:
            info = self._elements.get(pattern)
            return info.get("selector") if info else None

    def get_required_fields(self) -> List[Dict[str, Any]]:
        """Get list of required fields from the profile.

        Returns:
            List of {domain_key, portal_key, selector, label, max_length}
        """
        mappings = dict(FIELD_MAPPINGS)
        portal_overrides = PORTAL_OVERRIDES.get(self.channel_type, {})
        mappings.update(portal_overrides)

        # Build reverse map (portal_pattern → domain_key)
        pattern_to_domain = {v["portal_key"]: k for k, v in mappings.items()}

        required = []
        for key, info in self._elements.items():
            if info.get("required"):
                portal_key = key
                # Find domain key
                domain_key = None
                for pattern, dk in pattern_to_domain.items():
                    p_clean = pattern.replace("*.", "")
                    if portal_key.endswith(p_clean):
                        domain_key = dk
                        break

                required.append({
                    "domain_key": domain_key or portal_key,
                    "portal_key": portal_key,
                    "selector": info.get("selector", ""),
                    "label": info.get("label", key),
                    "field_type": info.get("field_type", "text"),
                    "max_length": info.get("max_length"),
                })

        return required
