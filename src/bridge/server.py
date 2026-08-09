"""InsureDesk — Bridge Server.

Local HTTP server that receives tool execution requests from UIP-AI.
UIP-AI sends JSON commands; InsureDesk executes them and returns results.

Endpoints:
    GET  /api/v1/health   — Health check
    GET  /api/v1/tools    — List available tools
    POST /api/v1/execute  — Execute a tool

Protocol:
    Request:
        {
            "request_id": "unique-id",
            "tool": "create_quote",
            "arguments": { "proposer_name": "...", "risk_class": "fire" }
        }

    Response (success):
        {
            "request_id": "unique-id",
            "status": "success",
            "result": { "quote_number": "MOCK-001", ... }
        }

    Response (error):
        {
            "request_id": "unique-id",
            "status": "error",
            "error": "Tool 'unknown' not found"
        }

Usage:
    from src.bridge.server import BridgeServer
    server = BridgeServer(port=8199)
    server.start()  # Starts in background thread
    # ... server running ...
    server.stop()
"""

from __future__ import annotations

import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread, Event
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse


API_VERSION = "v1"
DEFAULT_PORT = 8199
VERSION = "1.0.0"


# ══════════════════════════════════════════════════════════════════
# Protocol Models
# ══════════════════════════════════════════════════════════════════


@dataclass
class BridgeRequest:
    """Incoming tool execution request from UIP-AI."""
    request_id: str
    tool: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "tool": self.tool,
            "arguments": self.arguments,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BridgeRequest":
        return cls(
            request_id=d.get("request_id", ""),
            tool=d.get("tool", ""),
            arguments=d.get("arguments", {}),
            session_id=d.get("session_id"),
            timestamp=d.get("timestamp", datetime.utcnow().isoformat()),
        )


@dataclass
class BridgeResponse:
    """Response sent back to UIP-AI."""
    request_id: str
    status: str  # "success" or "error"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        d = {
            "request_id": self.request_id,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp,
        }
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return d

    @classmethod
    def success(cls, request_id: str, result: Dict[str, Any],
                duration_ms: float = 0.0) -> "BridgeResponse":
        return cls(
            request_id=request_id,
            status="success",
            result=result,
            duration_ms=duration_ms,
        )

    @classmethod
    def from_error(cls, request_id: str, error: str,
              duration_ms: float = 0.0) -> "BridgeResponse":
        return cls(
            request_id=request_id,
            status="error",
            error=error,
            duration_ms=duration_ms,
        )


# ══════════════════════════════════════════════════════════════════
# HTTP Request Handler
# ══════════════════════════════════════════════════════════════════


class BridgeRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for bridge API endpoints."""

    # Shared references set by BridgeServer
    server_instance: Optional["BridgeServer"] = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/v1/health":
            self._handle_health()
        elif path == "/api/v1/tools":
            self._handle_list_tools()
        else:
            self._send_json(404, {"error": f"Not found: {path}"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/v1/execute":
            self._handle_execute()
        else:
            self._send_json(404, {"error": f"Not found: {path}"})

    # ── Handlers ──────────────────────────────────────────────

    def _handle_health(self):
        self._send_json(200, {
            "status": "ok",
            "version": VERSION,
            "tools_loaded": self._bridge().registry.count() if self._bridge() else 0,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def _handle_list_tools(self):
        if not self._bridge():
            self._send_json(503, {"error": "Bridge not initialized"})
            return

        tools = self._bridge().registry.list_tools()
        self._send_json(200, {
            "tools": tools,
            "count": len(tools),
        })

    def _handle_execute(self):
        if not self._bridge():
            self._send_json(503, {"error": "Bridge not initialized"})
            return

        # Parse request body
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self._send_json(400, {"error": "Empty request body"})
            return

        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": f"Invalid JSON: {e}"})
            return

        # Validate request
        request = BridgeRequest.from_dict(data)
        if not request.request_id:
            self._send_json(400, {"error": "Missing 'request_id'"})
            return
        if not request.tool:
            self._send_json(400, {"error": "Missing 'tool'"})
            return

        # Execute via bridge
        start = time.perf_counter()
        try:
            response = self._bridge().execute_tool(request)
            elapsed = (time.perf_counter() - start) * 1000
            response.duration_ms = elapsed

            status_code = 200 if response.status == "success" else 422
            self._send_json(status_code, response.to_dict())
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            self._send_json(500, BridgeResponse.from_error(
                request.request_id, f"Internal error: {e}", elapsed
            ).to_dict())

    # ── Helpers ───────────────────────────────────────────────

    def _bridge(self) -> Optional["BridgeServer"]:
        return BridgeRequestHandler.server_instance

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Suppress default HTTP server logging (use bridge's logger)."""
        if self._bridge():
            self._bridge().log(format % args)


# ══════════════════════════════════════════════════════════════════
# Bridge Server
# ══════════════════════════════════════════════════════════════════


class BridgeServer:
    """Local HTTP bridge server for UIP-AI tool execution.

    Runs in a background thread. Accepts JSON tool calls
    and returns JSON results.

    Usage:
        server = BridgeServer(port=8199)
        server.start()
        # ... server running in background ...
        server.stop()
    """

    def __init__(self, port: int = DEFAULT_PORT,
                 host: str = "127.0.0.1",
                 registry=None,
                 policy_engine=None,
                 session_runtime=None):
        self.port = port
        self.host = host
        self.url = f"http://{host}:{port}"

        # Lazy imports to avoid circular dependencies
        from src.tools.registry import ToolRegistry
        from src.tools.insurance.quote_tools import (
            register_all_quote_tools, reset_shared_adapter,
        )
        from src.policy.engine import PolicyEngine
        from src.runtime.session_runtime import SessionRuntime

        # Setup registry with default tools
        self.registry = registry or ToolRegistry.get_instance()
        if self.registry.count() == 0:
            register_all_quote_tools(self.registry)

        self.policy = policy_engine or PolicyEngine()
        self.sessions = session_runtime or SessionRuntime()

        self._server: Optional[HTTPServer] = None
        self._thread: Optional[Thread] = None
        self._stop_event = Event()

    # ── Lifecycle ─────────────────────────────────────────────

    def start(self) -> bool:
        """Start the bridge server in a background thread.

        Returns:
            True if started, False if already running.
        """
        if self._server is not None:
            return False

        BridgeRequestHandler.server_instance = self
        self._server = HTTPServer((self.host, self.port), BridgeRequestHandler)
        # Update port in case 0 was passed (auto-assign)
        self.port = self._server.server_address[1]
        self._thread = Thread(target=self._run, daemon=True, name="bridge-server")
        self._thread.start()
        return True

    def stop(self) -> bool:
        """Stop the bridge server.

        Returns:
            True if stopped, False if not running.
        """
        if self._server is None:
            return False

        self._stop_event.set()
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._server = None
        self._thread = None
        return True

    @property
    def is_running(self) -> bool:
        return self._server is not None and not self._stop_event.is_set()

    def _run(self):
        self.log(f"Bridge server started on {self.url}")
        self._server.serve_forever(poll_interval=0.5)

    # ── Tool Execution ────────────────────────────────────────

    def execute_tool(self, request: BridgeRequest) -> BridgeResponse:
        """Execute a tool requested by UIP-AI.

        Flow:
            1. Check policy (allow/deny/require_approval)
            2. Track session (if session_id provided)
            3. Execute tool via ToolRegistry
            4. Return result
        """
        start = time.perf_counter()

        # Step 1: Policy check
        policy_result = self.policy.evaluate(request.tool, request.arguments)
        if policy_result.is_blocked:
            elapsed = (time.perf_counter() - start) * 1000
            return BridgeResponse.from_error(
                request.request_id,
                f"Policy blocked: {policy_result.reason}",
                elapsed,
            )

        # Step 2: Track session if provided
        session_id = request.session_id
        if session_id:
            session = self.sessions.get_session(session_id)
            if session:
                self.sessions.start(session_id)
                self.sessions.log_tool_call(
                    session_id, request.tool, request.arguments,
                    error=policy_result.reason if not policy_result.is_allowed else None,
                )

        # Step 3: Execute tool
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            tool_result = loop.run_until_complete(
                self.registry.execute(request.tool, **request.arguments)
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            # Classify the error for structured response
            from src.portal.errors import classify_error
            portal_err = classify_error(e, {"tool": request.tool, "args": request.arguments})
            return BridgeResponse(
                request_id=request.request_id,
                status="error",
                error=portal_err.message,
                duration_ms=elapsed,
                result={
                    "error_type": portal_err.error_type.value,
                    "recoverable": portal_err.recoverable,
                    "auto_retry": portal_err.auto_retry,
                },
            )
        finally:
            loop.close()

        elapsed = (time.perf_counter() - start) * 1000

        # Step 4: Log result to session
        if session_id:
            session = self.sessions.get_session(session_id)
            if session:
                self.sessions.log_tool_call(
                    session_id, request.tool, request.arguments,
                    result=tool_result.data if tool_result.success else None,
                    error=tool_result.error if not tool_result.success else None,
                    duration_ms=elapsed,
                )

        if tool_result.success:
            return BridgeResponse.success(
                request.request_id, tool_result.data, elapsed
            )
        else:
            return BridgeResponse.from_error(
                request.request_id, tool_result.error, elapsed
            )

    # ── Logging ───────────────────────────────────────────────

    def log(self, message: str):
        """Log a bridge message."""
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        print(f"[Bridge {timestamp}] {message}")
