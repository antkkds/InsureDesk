"""Tests for InsureDesk Tool Runtime Core (Phase 1 + Phase 2)."""

from __future__ import annotations

import json
import asyncio
from http.server import HTTPServer
from threading import Thread
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

import pytest

from src.tools import (
    ToolBase,
    ToolRegistry,
    ToolExecutionResult,
    ToolNotFoundError,
    ToolRegistrationError,
    register_all_tools,
)


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════


class EchoTool(ToolBase):
    """Simple test tool that echoes arguments back."""
    name = "echo"
    description = "Echoes back the arguments"

    async def execute(self, arguments, context=None):
        return ToolExecutionResult.ok(data={
            "echo": arguments,
            "context": context or {},
        })


class FailingTool(ToolBase):
    """Test tool that always fails."""
    name = "fail"
    description = "Always fails"

    async def execute(self, arguments, context=None):
        return ToolExecutionResult.fail(
            error="Intentional failure",
            error_code="test_failure",
            error_context={"reason": "testing"},
        )


class SlowTool(ToolBase):
    """Test tool that takes time."""
    name = "slow"
    description = "Slow tool"

    async def execute(self, arguments, context=None):
        await asyncio.sleep(0.1)
        return ToolExecutionResult.ok(data={"slow": True})


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register(EchoTool())
    r.register(FailingTool())
    r.register(SlowTool())
    return r


# ══════════════════════════════════════════════════════════════════
# ToolBase Tests
# ══════════════════════════════════════════════════════════════════


class TestToolBase:
    def test_tool_has_name_and_description(self):
        tool = EchoTool()
        assert tool.name == "echo"
        assert tool.description

    def test_execute_returns_tool_execution_result(self):
        tool = EchoTool()
        result = asyncio.run(tool.execute({"msg": "hello"}))
        assert isinstance(result, ToolExecutionResult)
        assert result.success
        assert result.data["echo"] == {"msg": "hello"}


# ══════════════════════════════════════════════════════════════════
# ToolExecutionResult Tests
# ══════════════════════════════════════════════════════════════════


class TestToolExecutionResult:
    def test_ok(self):
        r = ToolExecutionResult.ok(data={"key": "val"})
        assert r.success
        assert r.data == {"key": "val"}
        assert r.error is None

    def test_fail(self):
        r = ToolExecutionResult.fail("error msg", error_code="err")
        assert not r.success
        assert r.error == "error msg"
        assert r.error_code == "err"

    def test_to_dict(self):
        r = ToolExecutionResult.ok(data=42)
        d = r.to_dict()
        assert d["success"] is True
        assert d["data"] == 42

        r2 = ToolExecutionResult.fail("nope", error_code="fail")
        d2 = r2.to_dict()
        assert d2["success"] is False
        assert d2["error"] == "nope"
        assert d2["error_code"] == "fail"


# ══════════════════════════════════════════════════════════════════
# ToolRegistry Tests
# ══════════════════════════════════════════════════════════════════


class TestToolRegistry:
    def test_empty_registry(self):
        r = ToolRegistry()
        assert r.tool_count == 0
        assert r.list_tools() == []

    def test_register_and_get(self, registry):
        tool = registry.get("echo")
        assert isinstance(tool, EchoTool)

    def test_register_duplicate_raises(self, registry):
        with pytest.raises(ToolRegistrationError):
            registry.register(EchoTool())

    def test_register_empty_name_raises(self):
        class NoNameTool(ToolBase):
            name = ""
            description = "no name"

            async def execute(self, arguments, context=None):
                return ToolExecutionResult.ok()

        with pytest.raises(ToolRegistrationError):
            ToolRegistry().register(NoNameTool())

    def test_unregister(self, registry):
        assert registry.has_tool("echo")
        registry.unregister("echo")
        assert not registry.has_tool("echo")

    def test_get_not_found(self, registry):
        with pytest.raises(ToolNotFoundError):
            registry.get("nonexistent")

    def test_list_tools(self, registry):
        tools = registry.list_tools()
        names = [t["name"] for t in tools]
        assert "echo" in names
        assert "fail" in names
        assert "slow" in names
        assert len(tools) == 3

    def test_execute_success(self, registry):
        result = asyncio.run(registry.execute("echo", {"x": 1}))
        assert result.success
        assert result.data["echo"]["x"] == 1

    def test_execute_failure(self, registry):
        result = asyncio.run(registry.execute("fail", {}))
        assert not result.success
        assert result.error == "Intentional failure"
        assert result.error_code == "test_failure"

    def test_execute_not_found(self, registry):
        with pytest.raises(ToolNotFoundError):
            asyncio.run(registry.execute("ghost", {}))

    def test_execute_with_context(self, registry):
        result = asyncio.run(registry.execute(
            "echo", {"msg": "hi"},
            context={"session": "abc"},
        ))
        assert result.success
        assert result.data["context"]["session"] == "abc"

    def test_execute_unexpected_error(self):
        class BrokenTool(ToolBase):
            name = "broken"
            description = "broken"

            async def execute(self, arguments, context=None):
                raise ValueError("something broke")

        r = ToolRegistry()
        r.register(BrokenTool())
        result = asyncio.run(r.execute("broken", {}))
        assert not result.success
        assert result.error_code == "tool_execution_error"

    def test_stats(self, registry):
        stats = registry.stats()
        assert stats["tool_count"] == 3
        assert len(stats["tools"]) == 3


# ══════════════════════════════════════════════════════════════════
# BridgeServer Tests (integration)
# ══════════════════════════════════════════════════════════════════


TEST_PORT = 8200


@pytest.fixture(scope="module")
def bridge_server():
    """Start a Bridge server for integration tests."""
    from src.bridge.server import BridgeServer, BridgeRequestHandler

    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(FailingTool())

    BridgeRequestHandler.registry = registry
    server = HTTPServer(("127.0.0.1", TEST_PORT), BridgeRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield server

    server.shutdown()


def _bridge_request(method: str, path: str, body: Optional[dict] = None):
    """Make a request to the bridge server."""
    url = f"http://127.0.0.1:{TEST_PORT}{path}"
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except URLError as e:
        if hasattr(e, "code") and e.code:
            return e.code, json.loads(e.read().decode())
        raise


class TestBridgeServer:
    def test_health(self, bridge_server):
        status, data = _bridge_request("GET", "/api/v1/health")
        assert status == 200
        assert data["status"] == "ok"
        assert data["service"] == "insuredesk-bridge"

    def test_list_tools(self, bridge_server):
        status, data = _bridge_request("GET", "/api/v1/tools")
        assert status == 200
        names = [t["name"] for t in data["tools"]]
        assert "echo" in names
        assert "fail" in names

    def test_execute_success(self, bridge_server):
        status, data = _bridge_request("POST", "/api/v1/execute", {
            "tool": "echo",
            "arguments": {"msg": "hello"},
            "session_id": "test-1",
        })
        assert status == 200
        assert data["status"] == "success"
        assert data["tool"] == "echo"
        assert data["result"]["echo"]["msg"] == "hello"

    def test_execute_failure(self, bridge_server):
        status, data = _bridge_request("POST", "/api/v1/execute", {
            "tool": "fail",
            "arguments": {},
            "session_id": "test-2",
        })
        assert status == 200  # Tool failure != HTTP error
        assert data["status"] == "error"
        assert data["error"] == "Intentional failure"
        assert data["error_code"] == "test_failure"

    def test_execute_tool_not_found(self, bridge_server):
        status, data = _bridge_request("POST", "/api/v1/execute", {
            "tool": "ghost",
            "arguments": {},
            "session_id": "test-3",
        })
        assert status == 404
        assert data["error_code"] == "tool_not_found"

    def test_execute_missing_tool_field(self, bridge_server):
        status, data = _bridge_request("POST", "/api/v1/execute", {
            "arguments": {},
        })
        assert status == 400
        assert data["error_code"] == "missing_tool"

    def test_404(self, bridge_server):
        status, data = _bridge_request("GET", "/api/v1/nonexistent")
        assert status == 404


# ══════════════════════════════════════════════════════════════════
# register_all_tools
# ══════════════════════════════════════════════════════════════════


class TestRegisterAllTools:
    def test_register_all_tools(self):
        registry = ToolRegistry()
        register_all_tools(registry)
        # Phase 3: CalculateQuoteTool registered
        assert registry.tool_count == 2
        assert registry.has_tool("calculate_quote")
