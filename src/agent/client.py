"""InsureDesk — Agent Client (UIP-AI Agent Protocol client).

Phase 4.3: UIP-AI is the Agent Protocol SERVER; InsureDesk is the
Agent Protocol CLIENT.

    register()        → POST /api/v1/agent-providers/register-manifest
    heartbeat()       → POST /api/v1/agent-providers/{instance_id}/heartbeat
    poll_commands()   → GET  /api/v1/agent-providers/{instance_id}/commands
    report_result()   → POST /api/v1/agent-providers/{instance_id}/executions/{execution_id}/result

Connection config points to the CLOUD UIP-AI endpoint (NOT 127.0.0.1 —
this is a remote connection, not the local bridge).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from src.agent.manifest import InsureDeskManifest

logger = logging.getLogger(__name__)


class AgentClientError(Exception):
    pass


@dataclass
class AgentClientConfig:
    """UIP-AI cloud connection settings."""

    endpoint: str = ""          # e.g. https://api.uip-ai.com
    tenant_id: str = ""
    api_key: str = ""
    timeout: float = 10.0
    verify_ssl: bool = True


@dataclass
class AgentCommand:
    """A command received from UIP-AI (polled)."""

    execution_id: str
    capability: str
    arguments: Dict[str, Any] = field(default_factory=dict)


class AgentClient:
    """HTTP client for the UIP-AI Agent Provider API."""

    def __init__(
        self,
        config: AgentClientConfig,
        manifest: Optional[InsureDeskManifest] = None,
    ) -> None:
        self.config = config
        self.manifest = manifest or InsureDeskManifest()
        self.instance_id: str = ""
        self._session = requests.Session()
        if config.api_key:
            self._session.headers["Authorization"] = f"Bearer {config.api_key}"

    # ── Connection ─────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.config.endpoint.rstrip('/')}{path}"

    def _post(self, path: str, json: Any) -> Dict[str, Any]:
        try:
            resp = self._session.post(
                self._url(path), json=json, timeout=self.config.timeout,
                verify=self.config.verify_ssl,
            )
        except requests.RequestException as e:
            raise AgentClientError(f"network error: {e}") from e
        if resp.status_code >= 400:
            raise AgentClientError(
                f"HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()

    def _get(self, path: str) -> Dict[str, Any]:
        try:
            resp = self._session.get(
                self._url(path), timeout=self.config.timeout,
                verify=self.config.verify_ssl,
            )
        except requests.RequestException as e:
            raise AgentClientError(f"network error: {e}") from e
        if resp.status_code >= 400:
            raise AgentClientError(
                f"HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()

    # ── Protocol ───────────────────────────────────────────────────────────

    def register(self) -> str:
        """Register with UIP-AI. Returns the instance_id."""
        data = self._post(
            "/api/v1/agent-providers/register-manifest",
            {
                "tenant_id": self.config.tenant_id,
                "manifest": self.manifest.to_dict(),
            },
        )
        self.instance_id = data.get("instance_id", "")
        if not self.instance_id:
            raise AgentClientError("register response missing instance_id")
        logger.info(
            "agent_client.registered: instance=%s status=%s",
            self.instance_id, data.get("status"),
        )
        return self.instance_id

    def heartbeat(self) -> Dict[str, Any]:
        """Send a heartbeat for the registered instance."""
        if not self.instance_id:
            raise AgentClientError("not registered — call register() first")
        return self._post(
            f"/api/v1/agent-providers/{self.instance_id}/heartbeat", {}
        )

    def poll_commands(self, limit: int = 10) -> List[AgentCommand]:
        """Poll pending commands from UIP-AI."""
        if not self.instance_id:
            raise AgentClientError("not registered — call register() first")
        data = self._get(
            f"/api/v1/agent-providers/{self.instance_id}/commands?limit={limit}"
        )
        return [
            AgentCommand(
                execution_id=c["execution_id"],
                capability=c["capability"],
                arguments=c.get("arguments", {}),
            )
            for c in data.get("commands", [])
        ]

    def report_result(
        self, execution_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Report execution result to UIP-AI."""
        if not self.instance_id:
            raise AgentClientError("not registered — call register() first")
        return self._post(
            f"/api/v1/agent-providers/{self.instance_id}"
            f"/executions/{execution_id}/result",
            payload,
        )

    def close(self) -> None:
        self._session.close()
