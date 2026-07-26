"""InsureDesk Runtime — Adapter Capabilities.

Each ModelAdapter declares what operations it supports.
The runtime uses this to select the right adapter for each operation.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Set, Type

from src.models.adapter_base import ModelAdapter


class AdapterCapability(Enum):
    """Standard capabilities an adapter may support.

    Each enum value represents one atomic operation.
    """

    # ── Policy ──
    FETCH_POLICY = "fetch_policy"
    """Retrieve a single policy by policy_number."""
    SEARCH_POLICIES = "search_policies"
    """Search policies by customer, date, or keyword."""
    LIST_POLICIES = "list_policies"
    """List all policies for a customer."""

    # ── Claim ──
    FETCH_CLAIM = "fetch_claim"
    """Retrieve a single claim by claim_id."""
    SEARCH_CLAIMS = "search_claims"
    """Search claims by policy or customer."""
    SUBMIT_CLAIM = "submit_claim"
    """Submit a new claim to the portal."""

    # ── Customer ──
    FETCH_CUSTOMER = "fetch_customer"
    """Retrieve customer profile from portal."""
    SEARCH_CUSTOMERS = "search_customers"
    """Search customers by name or IC."""

    # ── Document ──
    DOWNLOAD_DOCUMENT = "download_document"
    """Download a policy/claim document from portal."""

    # ── Portal Meta ──
    LOGIN = "login"
    """Supports portal login authentication."""
    HEALTH_CHECK = "health_check"
    """Can verify portal is reachable."""


# ── Per-adapter capability declarations ──

# Default: all portal adapters can extract data from raw dicts
CORE_CAPABILITIES: Set[AdapterCapability] = {
    AdapterCapability.FETCH_POLICY,
    AdapterCapability.FETCH_CLAIM,
    AdapterCapability.FETCH_CUSTOMER,
}

ADAPTER_CAPABILITIES: Dict[str, Set[AdapterCapability]] = {
    # Portal adapters support core + search
    "great_eastern": CORE_CAPABILITIES | {
        AdapterCapability.SEARCH_POLICIES,
        AdapterCapability.SEARCH_CLAIMS,
        AdapterCapability.LOGIN,
    },
    "allianz": CORE_CAPABILITIES | {
        AdapterCapability.SEARCH_POLICIES,
        AdapterCapability.LOGIN,
    },
    "aia": CORE_CAPABILITIES | {
        AdapterCapability.SEARCH_POLICIES,
        AdapterCapability.SEARCH_CLAIMS,
        AdapterCapability.LOGIN,
    },
    # PDF adapters only support policy extraction
    "great_eastern_pdf": {
        AdapterCapability.FETCH_POLICY,
        AdapterCapability.SEARCH_POLICIES,
    },
}


def get_adapter_capabilities(adapter_key: str) -> Set[AdapterCapability]:
    """Get capabilities for a registered adapter key.

    Args:
        adapter_key: The registry key (e.g. 'great_eastern', 'aia')
    Returns:
        Set of supported capabilities (empty set if unknown key)
    """
    return ADAPTER_CAPABILITIES.get(adapter_key, CORE_CAPABILITIES.copy())


def supports_capability(adapter_key: str, capability: AdapterCapability) -> bool:
    """Check if an adapter supports a specific capability.

    Args:
        adapter_key: The registry key
        capability: The capability to check
    Returns:
        True if supported
    """
    caps = get_adapter_capabilities(adapter_key)
    return capability in caps


def register_adapter_capabilities(adapter_key: str, capabilities: Set[AdapterCapability]):
    """Register capabilities for a custom/dynamically added adapter.

    Args:
        adapter_key: The registry key
        capabilities: Set of supported capabilities
    """
    ADAPTER_CAPABILITIES[adapter_key] = set(capabilities)
