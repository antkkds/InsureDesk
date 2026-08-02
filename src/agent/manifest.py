"""InsureDesk — Agent Manifest.

Frozen schema (docs/agent-manifest-schema.md in UIP-AI):
    name / type / version / transport: http_pull / provides / metadata

Do NOT hand-write manifest strings scattered in code — always build via
this class.
"""

from __future__ import annotations

from typing import Any, Dict, List


class InsureDeskManifest:
    """Builds the InsureDesk agent manifest dict (schema-frozen)."""

    NAME = "insuredesk"
    TYPE = "desktop_agent"
    VERSION = "1.0.0"
    TRANSPORT = "http_pull"
    # Per-capability safety (Phase 4.5 — Agent Capability Scope):
    #   readonly → calculate/search/status allowed; save/submit blocked
    PROVIDES = [
        {"insurance.quote.calculate": {"safety": "readonly"}},
        {"insurance.claim.status": {"safety": "readonly"}},
        {"insurance.policy.search": {"safety": "readonly"}},
    ]

    def __init__(
        self,
        provides: List[Any] | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        self.provides = provides or list(self.PROVIDES)
        self.metadata = dict(metadata or {})
        self.metadata.setdefault("vendor", "InsureDesk Pte Ltd")
        self.metadata.setdefault("simulation_supported", True)

    def capability_names(self) -> List[str]:
        """Flat capability names (for quick checks)."""
        names = []
        for item in self.provides:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                names.extend(item.keys())
        return names

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.NAME,
            "type": self.TYPE,
            "version": self.VERSION,
            "transport": self.TRANSPORT,
            "provides": list(self.provides),
            "metadata": dict(self.metadata),
        }

    def to_yaml(self) -> str:
        import yaml

        return yaml.safe_dump(self.to_dict(), sort_keys=False)

    def __repr__(self) -> str:
        return f"InsureDeskManifest(name={self.NAME}, provides={self.provides})"
