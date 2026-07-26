"""Low-level CDP WebSocket connection.

Handles the Chrome DevTools Protocol communication:
- Connect to a page/browser WebSocket endpoint
- Send commands and receive responses
- Subscribe to events
"""

import asyncio
import json
from typing import Optional, Callable, Dict, Any
import websockets


class CdpConnection:
    """A single CDP WebSocket connection to a Chrome target (page or browser)."""

    def __init__(self):
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._msg_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._event_handlers: Dict[str, list] = {}
        self._listener_task: Optional[asyncio.Task] = None
        self._closed = False

    async def connect(self, ws_url: str, timeout: float = 10.0):
        """Connect to a CDP WebSocket endpoint."""
        self._ws = await asyncio.wait_for(
            websockets.connect(ws_url, ping_interval=None),
            timeout=timeout,
        )
        self._closed = False
        # Start listener background task
        self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self):
        """Background task: receive and dispatch CDP messages."""
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                # Response to a command
                if "id" in msg:
                    future = self._pending.pop(msg["id"], None)
                    if future and not future.done():
                        if "error" in msg:
                            future.set_exception(
                                Exception(msg["error"].get("message", "CDP error"))
                            )
                        else:
                            future.set_result(msg.get("result", {}))

                # Event
                elif "method" in msg:
                    handlers = self._event_handlers.get(msg["method"], [])
                    for handler in handlers:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                asyncio.ensure_future(handler(msg.get("params", {})))
                            else:
                                handler(msg.get("params", {}))
                        except Exception:
                            pass
        except websockets.ConnectionClosed:
            pass
        except Exception:
            pass
        finally:
            self._closed = True
            # Fail all pending futures
            for fid, future in self._pending.items():
                if not future.done():
                    future.set_exception(ConnectionError("CDP connection closed"))
            self._pending.clear()

    async def send_command(self, method: str, params: dict = None,
                           timeout: float = 30.0) -> dict:
        """Send a CDP command and wait for the response.

        Args:
            method: CDP method name (e.g. "Page.navigate").
            params: Command parameters.
            timeout: Max seconds to wait for response.

        Returns:
            The 'result' dict from the CDP response.

        Raises:
            TimeoutError if no response within timeout.
            ConnectionError if connection is closed.
        """
        if self._closed or not self._ws:
            raise ConnectionError("CDP connection is not open")

        self._msg_id += 1
        msg_id = self._msg_id

        payload = {"id": msg_id, "method": method}
        if params:
            payload["params"] = params

        future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        try:
            await self._ws.send(json.dumps(payload))
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"CDP command {method} timed out after {timeout}s")

    async def send_command_no_wait(self, method: str, params: dict = None):
        """Send a CDP command without waiting for response (fire-and-forget)."""
        if self._closed or not self._ws:
            return

        self._msg_id += 1
        payload = {"id": self._msg_id, "method": method}
        if params:
            payload["params"] = params

        try:
            await self._ws.send(json.dumps(payload))
        except Exception:
            pass

    def on(self, event_name: str, handler: Callable):
        """Subscribe to a CDP event.

        Args:
            event_name: Full CDP event name (e.g. "Page.frameStoppedLoading").
            handler: Callback receiving the event params dict.
        """
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(handler)

    def off(self, event_name: str, handler: Callable = None):
        """Unsubscribe from a CDP event."""
        if handler:
            handlers = self._event_handlers.get(event_name, [])
            if handler in handlers:
                handlers.remove(handler)
        else:
            self._event_handlers.pop(event_name, None)

    async def close(self):
        """Close the WebSocket connection."""
        self._closed = True
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except Exception:
                pass
            self._listener_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    @property
    def is_connected(self) -> bool:
        return not self._closed and self._ws is not None
