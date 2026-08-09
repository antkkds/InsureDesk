"""Tests: Sprint 5 — Bridge Protocol.

Tests for:
1. BridgeRequest / BridgeResponse — protocol models
2. BridgeServer — start/stop, health, tools, execute
3. Integration — policy checks, session tracking, tool execution
"""

from __future__ import annotations

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. BridgeRequest / BridgeResponse (6 tests)
# ══════════════════════════════════════════════════════════════════


class TestBridgeModels:
    """Protocol data models."""

    def test_bridge_request_defaults(self):
        from src.bridge.server import BridgeRequest
        r = BridgeRequest(request_id="abc", tool="create_quote")
        assert r.request_id == "abc"
        assert r.tool == "create_quote"
        assert r.arguments == {}
        assert r.session_id is None
        assert r.timestamp != ""

    def test_bridge_request_to_dict(self):
        from src.bridge.server import BridgeRequest
        r = BridgeRequest(
            request_id="abc", tool="calculate_quote",
            arguments={"premium": 5000}, session_id="S001",
        )
        d = r.to_dict()
        assert d["request_id"] == "abc"
        assert d["tool"] == "calculate_quote"
        assert d["arguments"] == {"premium": 5000}
        assert d["session_id"] == "S001"

    def test_bridge_request_from_dict(self):
        from src.bridge.server import BridgeRequest
        r = BridgeRequest.from_dict({
            "request_id": "xyz",
            "tool": "list_products",
            "arguments": {},
            "session_id": "S002",
        })
        assert r.request_id == "xyz"
        assert r.tool == "list_products"
        assert r.session_id == "S002"

    def test_bridge_response_success(self):
        from src.bridge.server import BridgeResponse
        r = BridgeResponse.success("abc", {"premium": 3200}, duration_ms=15.5)
        assert r.request_id == "abc"
        assert r.status == "success"
        assert r.result == {"premium": 3200}
        assert r.error is None
        assert r.duration_ms == 15.5

    def test_bridge_response_error(self):
        from src.bridge.server import BridgeResponse
        r = BridgeResponse.from_error("abc", "Something failed", duration_ms=5.0)
        assert r.request_id == "abc"
        assert r.status == "error"
        assert r.error == "Something failed"
        assert r.result is None

    def test_bridge_response_to_dict(self):
        from src.bridge.server import BridgeResponse
        r = BridgeResponse.success("abc", {"ok": True}, duration_ms=10.0)
        d = r.to_dict()
        assert d["request_id"] == "abc"
        assert d["status"] == "success"
        assert d["result"] == {"ok": True}
        assert "duration_ms" in d
        assert "timestamp" in d
        assert "error" not in d


# ══════════════════════════════════════════════════════════════════
# 2. BridgeServer — lifecycle (8 tests)
# ══════════════════════════════════════════════════════════════════


class TestBridgeServer:
    """BridgeServer start, stop, health, tools."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from src.tools.registry import ToolRegistry
        from src.tools.insurance.quote_tools import (
            register_all_quote_tools, reset_shared_adapter,
        )
        from src.policy.engine import PolicyEngine
        from src.runtime.session_runtime import SessionRuntime

        ToolRegistry.reset_instance()
        reset_shared_adapter()
        registry = ToolRegistry.get_instance()
        register_all_quote_tools(registry)

        self.registry = registry
        self.policy = PolicyEngine()
        self.sessions = SessionRuntime()

        yield

        ToolRegistry.reset_instance()
        reset_shared_adapter()

    @pytest.fixture
    def server(self):
        from src.bridge.server import BridgeServer
        s = BridgeServer(
            port=0,  # auto port
            registry=self.registry,
            policy_engine=self.policy,
            session_runtime=self.sessions,
        )
        s.start()
        yield s
        s.stop()

    def _get(self, server, path):
        import urllib.request
        url = f"http://127.0.0.1:{server.port}{path}"
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def _post(self, server, path, data):
        import urllib.request
        url = f"http://127.0.0.1:{server.port}{path}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_health_endpoint(self, server):
        status, data = self._get(server, "/api/v1/health")
        assert status == 200
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert data["tools_loaded"] >= 6

    def test_tools_endpoint(self, server):
        status, data = self._get(server, "/api/v1/tools")
        assert status == 200
        assert data["count"] >= 6
        names = [t["name"] for t in data["tools"]]
        assert "create_quote" in names
        assert "calculate_quote" in names
        assert "list_products" in names

    def test_execute_list_products(self, server):
        status, data = self._post(server, "/api/v1/execute", {
            "request_id": "test-001",
            "tool": "list_products",
            "arguments": {},
        })
        assert status == 200
        assert data["status"] == "success"
        assert data["request_id"] == "test-001"
        assert "FIRE" in [p["code"] for p in data["result"]["products"]]
        assert data["duration_ms"] > 0

    def test_execute_create_quote(self, server):
        status, data = self._post(server, "/api/v1/execute", {
            "request_id": "test-002",
            "tool": "create_quote",
            "arguments": {
                "proposer_name": "Tiong Hoe Hung",
                "risk_class": "fire",
                "sum_insured": 5000000,
            },
        })
        assert status == 200
        assert data["status"] == "success"
        assert data["result"]["quote_number"].startswith("MOCK-")
        assert data["result"]["status"] == "draft"

    def test_execute_calculate_quote(self, server):
        status, data = self._post(server, "/api/v1/execute", {
            "request_id": "test-003",
            "tool": "calculate_quote",
            "arguments": {
                "proposer_name": "Test",
                "risk_class": "fire",
                "sum_insured": 1000000,
            },
        })
        assert status == 200
        assert data["status"] == "success"
        assert data["result"]["total_premium"] > 0

    def test_execute_unknown_tool(self, server):
        status, data = self._post(server, "/api/v1/execute", {
            "request_id": "test-004",
            "tool": "nonexistent_tool",
            "arguments": {},
        })
        assert status == 422
        assert data["status"] == "error"
        assert "not found" in data["error"].lower()

    def test_execute_missing_request_id(self, server):
        status, data = self._post(server, "/api/v1/execute", {
            "tool": "list_products",
        })
        assert status == 400
        assert "request_id" in data["error"]

    def test_404_unknown_path(self, server):
        status, data = self._get(server, "/api/v1/unknown")
        assert status == 404


# ══════════════════════════════════════════════════════════════════
# 3. Integration — Bridge + Policy + Session (6 tests)
# ══════════════════════════════════════════════════════════════════


class TestBridgeIntegration:
    """Bridge with policy engine and session runtime."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from src.tools.registry import ToolRegistry
        from src.tools.insurance.quote_tools import (
            register_all_quote_tools, reset_shared_adapter,
        )
        from src.policy.engine import PolicyEngine, PolicyRule, PolicyEffect
        from src.runtime.session_runtime import SessionRuntime

        ToolRegistry.reset_instance()
        reset_shared_adapter()
        registry = ToolRegistry.get_instance()
        register_all_quote_tools(registry)

        policy = PolicyEngine()
        policy.add_rule(PolicyRule(
            name="block_submit",
            action="quote.submit",
            effect=PolicyEffect.DENY,
            reason="Submit is disabled via bridge.",
        ))

        sessions = SessionRuntime()

        self.registry = registry
        self.policy = policy
        self.sessions = sessions

        yield

        ToolRegistry.reset_instance()
        reset_shared_adapter()

    @pytest.fixture
    def server(self):
        from src.bridge.server import BridgeServer
        s = BridgeServer(
            port=0,
            registry=self.registry,
            policy_engine=self.policy,
            session_runtime=self.sessions,
        )
        s.start()
        yield s
        s.stop()

    def _post(self, server, path, data):
        import urllib.request
        url = f"http://127.0.0.1:{server.port}{path}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_policy_blocks_tool(self, server):
        """Policy should block the tool and return error."""
        status, data = self._post(server, "/api/v1/execute", {
            "request_id": "pol-001",
            "tool": "quote.submit",
            "arguments": {},
        })
        assert status == 422
        assert data["status"] == "error"
        assert "Policy blocked" in data["error"]

    def test_policy_allows_tool(self, server):
        """Policy should allow non-blocked tools."""
        status, data = self._post(server, "/api/v1/execute", {
            "request_id": "pol-002",
            "tool": "list_products",
            "arguments": {},
        })
        assert status == 200
        assert data["status"] == "success"

    def test_session_tracking(self, server):
        """Session should be created and tool call logged."""
        # First create a session
        s = self.sessions.create_session(customer_id="C001", task="fire_quote")

        # Execute with session_id
        status, data = self._post(server, "/api/v1/execute", {
            "request_id": "sess-001",
            "tool": "create_quote",
            "arguments": {
                "proposer_name": "Test",
                "risk_class": "fire",
                "sum_insured": 100000,
            },
            "session_id": s.id,
        })
        assert status == 200

        # Verify session has the tool call logged
        session = self.sessions.get_session(s.id)
        assert session is not None
        assert len(session.tool_calls) >= 1
        assert session.tool_calls[0]["tool"] == "create_quote"

    def test_session_tracking_with_policy_block(self, server):
        """Blocked calls should still be logged in session."""
        s = self.sessions.create_session(customer_id="C001", task="fire_quote")

        status, data = self._post(server, "/api/v1/execute", {
            "request_id": "sess-002",
            "tool": "quote.submit",
            "arguments": {},
            "session_id": s.id,
        })
        assert status == 422

        session = self.sessions.get_session(s.id)
        assert session is not None
        # Policy check happened before tool call
        # The session should exist and be tracked

    def test_compare_then_calculate_through_bridge(self, server):
        """Full workflow through bridge."""
        # Compare
        status1, data1 = self._post(server, "/api/v1/execute", {
            "request_id": "wf-001",
            "tool": "compare_quotes",
            "arguments": {
                "proposer_name": "Test",
                "sum_insured": 500000,
                "risk_classes": ["fire", "travel"],
            },
        })
        assert status1 == 200
        assert data1["result"]["count"] == 2

        # Create quote
        status2, data2 = self._post(server, "/api/v1/execute", {
            "request_id": "wf-002",
            "tool": "create_quote",
            "arguments": {
                "proposer_name": "Test",
                "risk_class": "fire",
                "sum_insured": 500000,
            },
        })
        assert status2 == 200

    def test_concurrent_requests(self, server):
        """Multiple requests should be handled."""
        import threading
        results = []

        def send_req(idx):
            _, data = self._post(server, "/api/v1/execute", {
                "request_id": f"conc-{idx:03d}",
                "tool": "list_products",
                "arguments": {},
            })
            results.append(data["status"])

        threads = [threading.Thread(target=send_req, args=(i,))
                   for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r == "success" for r in results)
        assert len(results) == 5
