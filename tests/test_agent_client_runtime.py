"""
Phase 4.3 acceptance tests — InsureDesk Agent Client Runtime (T1–T6).

    T1 — Manifest Register → agent online
    T2 — Heartbeat → provider ONLINE
    T3 — Fake command → poll receives execution_id/capability/arguments
    T4 — Simulation execution → result → Execution SUCCESS
    T5 — Error mapping (login_failed → PORTAL_AUTH_FAILED)
    T6 — Restart recovery → re-register works

Uses a stdlib FakeUIPAI server implementing the Agent Protocol endpoints
(no external deps).
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import pytest

from src.agent import (
    AgentClient,
    AgentClientConfig,
    AgentCommandLoop,
    AgentHeartbeat,
    CapabilityHandlerRegistry,
    InsureDeskManifest,
    ResultReporter,
    map_error_code,
)


# ══════════════════════════════════════════════════════════════════════════════
# Fake UIP-AI server (Agent Protocol server side)
# ══════════════════════════════════════════════════════════════════════════════


class FakeUIPAIState:
    def __init__(self) -> None:
        self.registrations: List[Dict[str, Any]] = []
        self.heartbeats: Dict[str, int] = {}
        self.pending_commands: Dict[str, List[Dict[str, Any]]] = {}
        self.results: List[Dict[str, Any]] = []


class FakeUIPAIHandler(BaseHTTPRequestHandler):
    state: FakeUIPAIState = FakeUIPAIState()

    def log_message(self, fmt, *args):  # silence
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        path = urlparse(self.path).path
        st = self.state
        if path == "/api/v1/agent-providers/register-manifest":
            body = self._read_json()
            manifest = body.get("manifest", {})
            instance_id = f"inst_{manifest.get('name', 'agent')}"
            st.registrations.append(
                {"instance_id": instance_id, "manifest": manifest,
                 "tenant_id": body.get("tenant_id", "")}
            )
            st.pending_commands.setdefault(instance_id, [])
            self._send_json({"instance_id": instance_id, "status": "online"})
        elif "/heartbeat" in path:
            instance_id = path.split("/")[4]
            st.heartbeats[instance_id] = st.heartbeats.get(instance_id, 0) + 1
            self._send_json({"status": "running"})
        elif "/result" in path:
            body = self._read_json()
            st.results.append({"path": path, "body": body})
            self._send_json({"accepted": True})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_GET(self):
        path = urlparse(self.path).path
        st = self.state
        if "/commands" in path:
            instance_id = path.split("/")[4]
            cmds = st.pending_commands.get(instance_id, [])
            st.pending_commands[instance_id] = []
            self._send_json({"commands": cmds})
        else:
            self._send_json({"error": "not found"}, 404)


@pytest.fixture(scope="module")
def fake_server():
    FakeUIPAIHandler.state = FakeUIPAIState()
    server = HTTPServer(("127.0.0.1", 0), FakeUIPAIHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def make_client(endpoint: str, tenant: str = "tenant_a") -> AgentClient:
    return AgentClient(
        AgentClientConfig(endpoint=endpoint, tenant_id=tenant, api_key="test-key")
    )


# ══════════════════════════════════════════════════════════════════════════════
# T1 — Manifest Register
# ══════════════════════════════════════════════════════════════════════════════


class TestManifestRegister:
    def test_manifest_shape(self):
        m = InsureDeskManifest()
        d = m.to_dict()
        assert d["name"] == "insuredesk"
        assert d["type"] == "desktop_agent"
        assert d["transport"] == "http_pull"
        assert "insurance.quote.calculate" in m.capability_names()
        # Phase 4.5: per-capability safety scope
        quote = next(
            item for item in d["provides"]
            if "insurance.quote.calculate" in item
        )
        assert quote["insurance.quote.calculate"]["safety"] == "readonly"

    def test_t1_register_sets_online(self, fake_server):
        client = make_client(fake_server)
        instance_id = client.register()
        assert instance_id.startswith("inst_")
        assert client.instance_id == instance_id
        # Server saw the registration
        state = FakeUIPAIHandler.state
        assert len(state.registrations) == 1
        assert state.registrations[0]["manifest"]["name"] == "insuredesk"
        assert state.registrations[0]["tenant_id"] == "tenant_a"


# ══════════════════════════════════════════════════════════════════════════════
# T2 — Heartbeat
# ══════════════════════════════════════════════════════════════════════════════


class TestHeartbeat:
    def test_t2_heartbeat_keeps_online(self, fake_server):
        client = make_client(fake_server)
        client.register()
        resp = client.heartbeat()
        assert resp["status"] == "running"
        state = FakeUIPAIHandler.state
        assert state.heartbeats.get(client.instance_id, 0) == 1

    def test_heartbeat_thread_ticks(self, fake_server):
        client = make_client(fake_server)
        client.register()
        calls = {"n": 0}

        def hb():
            calls["n"] += 1
            return client.heartbeat()

        thread = AgentHeartbeat(hb, interval_seconds=0.05, max_retries=2)
        thread.start()
        import time

        time.sleep(0.25)
        thread.stop()
        assert calls["n"] >= 2
        assert thread.state == "online"

    def test_heartbeat_failure_does_not_crash(self):
        """Heartbeat failure → retry → offline, thread survives."""
        calls = {"n": 0}

        def failing_hb():
            calls["n"] += 1
            raise ConnectionError("server unreachable")

        thread = AgentHeartbeat(failing_hb, interval_seconds=0.02, max_retries=3)
        thread.start()
        import time

        time.sleep(0.2)
        thread.stop()
        assert calls["n"] >= 3
        assert thread.state == "offline"
        assert "unreachable" in thread.last_error


# ══════════════════════════════════════════════════════════════════════════════
# T3 — Fake command polling
# ══════════════════════════════════════════════════════════════════════════════


class TestCommandPolling:
    def test_t3_poll_receives_command(self, fake_server):
        client = make_client(fake_server)
        client.register()
        # Server has a pending command for this instance
        FakeUIPAIHandler.state.pending_commands[client.instance_id] = [
            {
                "execution_id": "exec_123",
                "capability": "insurance.quote.calculate",
                "arguments": {"product": "IFE", "sum_insured": 100000},
            }
        ]
        commands = client.poll_commands()
        assert len(commands) == 1
        assert commands[0].execution_id == "exec_123"
        assert commands[0].capability == "insurance.quote.calculate"
        assert commands[0].arguments == {"product": "IFE", "sum_insured": 100000}

    def test_poll_empty(self, fake_server):
        client = make_client(fake_server)
        client.register()
        assert client.poll_commands() == []


# ══════════════════════════════════════════════════════════════════════════════
# T4 — Simulation execution via command loop
# ══════════════════════════════════════════════════════════════════════════════


class TestSimulationExecution:
    def test_t4_command_loop_executes_quote(self, fake_server):
        client = make_client(fake_server)
        client.register()
        FakeUIPAIHandler.state.pending_commands[client.instance_id] = [
            {
                "execution_id": "exec_sim",
                "capability": "insurance.quote.calculate",
                "arguments": {
                    "proposer_name": "Test User",
                    "risk_class": "fire",
                    "sum_insured": 500000,
                    "execution_mode": "simulation",
                },
            }
        ]
        handlers = CapabilityHandlerRegistry()
        handlers.register_defaults()
        loop = AgentCommandLoop(client, handlers, poll_interval_seconds=0.05)
        loop.start()
        import time

        for _ in range(100):
            if loop.executed_count >= 1:
                break
            time.sleep(0.05)
        loop.stop()

        assert loop.executed_count == 1
        assert loop.failed_count == 0
        # Result was reported to the server
        results = FakeUIPAIHandler.state.results
        assert len(results) == 1
        body = results[0]["body"]
        assert body["status"] == "success"
        assert body["execution_mode"] == "simulation"
        assert "quote_number" in body["result"] or "premium" in body["result"]

    def test_quote_handler_direct(self):
        """Quote handler executes against the local mock quote engine."""
        from src.agent.handlers import QuoteCapabilityHandler

        import asyncio

        handler = QuoteCapabilityHandler()
        result = asyncio.run(
            handler.execute(
                {
                    "proposer_name": "Alice",
                    "risk_class": "travel",
                    "sum_insured": 20000,
                    "execution_mode": "simulation",
                }
            )
        )
        assert result["status"] == "success"
        assert result["result"]["proposer_name"] == "Alice"


# ══════════════════════════════════════════════════════════════════════════════
# T5 — Error mapping
# ══════════════════════════════════════════════════════════════════════════════


class TestErrorMapping:
    def test_t5_login_failed_maps(self):
        assert map_error_code("Login failed: invalid credentials") == "PORTAL_AUTH_FAILED"
        assert map_error_code("session expired") == "PORTAL_SESSION_EXPIRED"
        assert map_error_code("something unknown") == "EXECUTION_FAILED"

    def test_reporter_failed_payload(self):
        reporter = ResultReporter()
        payload = reporter.failed("login failed")
        assert payload["status"] == "failed"
        assert payload["error_code"] == "PORTAL_AUTH_FAILED"

    def test_unknown_capability_reports_failure(self, fake_server):
        client = make_client(fake_server)
        client.register()
        FakeUIPAIHandler.state.pending_commands[client.instance_id] = [
            {
                "execution_id": "exec_unk",
                "capability": "unknown.capability.x",
                "arguments": {},
            }
        ]
        handlers = CapabilityHandlerRegistry()  # no defaults
        loop = AgentCommandLoop(client, handlers, poll_interval_seconds=0.05)
        loop.start()
        import time

        for _ in range(100):
            if loop.failed_count >= 1:
                break
            time.sleep(0.05)
        loop.stop()
        assert loop.failed_count == 1
        body = FakeUIPAIHandler.state.results[-1]["body"]
        assert body["status"] == "failed"
        assert body["error_code"] == "UNKNOWN_CAPABILITY"


# ══════════════════════════════════════════════════════════════════════════════
# T6 — Restart recovery
# ══════════════════════════════════════════════════════════════════════════════


class TestRestartRecovery:
    def test_t6_restart_reregisters(self, fake_server):
        # First "boot"
        client1 = make_client(fake_server, tenant="tenant_a")
        instance1 = client1.register()
        client1.heartbeat()

        # Agent "restarts" — new client, same identity
        client2 = make_client(fake_server, tenant="tenant_a")
        instance2 = client2.register()
        assert instance2  # fresh instance issued
        resp = client2.heartbeat()
        assert resp["status"] == "running"
        # Server has both registrations (old heartbeat eventually expires;
        # earlier tests also registered — count only needs >= 2)
        state = FakeUIPAIHandler.state
        assert len(state.registrations) >= 2
        assert state.registrations[-1]["tenant_id"] == "tenant_a"
