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
    PROVIDES = [
        "insurance.quote.calculate",
        "insurance.claim.status",
        "insurance.policy.search",
    ]

    def __init__(
        self,
        provides: List[str] | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        self.provides = provides or list(self.PROVIDES)
        self.metadata = dict(metadata or {})
        self.metadata.setdefault("vendor", "InsureDesk Pte Ltd")
        self.metadata.setdefault("simulation_supported", True)

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
