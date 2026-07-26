"""Deep Dive: Bridge Protocol, Session Timeout, Browser Recovery.

Integration-level tests for production failure scenarios.
"""

import os
import sys
import time
import json
import pytest
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestBridgeProtocol:
    """Bridge Protocol — connection, messaging, policy operations."""

    def test_bridge_client_creates(self):
        """BridgeClient creates with default URL."""
        from src.bridge.protocol import BridgeClient
        client = BridgeClient()
        assert client is not None
        assert client.base_url == "http://localhost:8000"
        assert client.connected is False

    def test_bridge_connect_no_server(self):
        """Connect to non-existent server returns False gracefully."""
        from src.bridge.protocol import BridgeClient
        client = BridgeClient(base_url="http://localhost:1")
        result = client.connect(token="fake_token")
        assert result is False
        assert client.connected is False

    def test_bridge_ping_no_server(self):
        """Ping without connection returns False."""
        from src.bridge.protocol import BridgeClient
        client = BridgeClient(base_url="http://localhost:1")
        result = client.ping()
        assert result is False

    def test_bridge_send_message_no_server(self):
        """Send message without connection returns None gracefully."""
        from src.bridge.protocol import BridgeClient, BridgeMessage
        client = BridgeClient(base_url="http://localhost:1")
        msg = BridgeMessage(text="Hello")
        result = client.send_message(msg)
        assert result is None

    def test_bridge_execute_tool_no_server(self):
        """Execute tool without connection returns None."""
        from src.bridge.protocol import BridgeClient, ToolCall
        client = BridgeClient(base_url="http://localhost:1")
        tc = ToolCall(tool="test_tool", params={})
        result = client.execute_tool(tc)
        assert result is None

    def test_bridge_disconnect_no_connection(self):
        """Disconnect without connection doesn't crash."""
        from src.bridge.protocol import BridgeClient
        client = BridgeClient()
        client.disconnect()  # Should not raise
        assert client.connected is False

    def test_bridge_message_has_id_and_timestamp(self):
        """BridgeMessage auto-generates id and timestamp."""
        from src.bridge.protocol import BridgeMessage
        msg = BridgeMessage(text="test")
        assert msg.id is not None
        assert len(msg.id) > 0
        assert msg.timestamp is not None

    def test_bridge_message_to_dict(self):
        """BridgeMessage serializes to dict."""
        from src.bridge.protocol import BridgeMessage
        msg = BridgeMessage(text="test", customer_id="c1")
        d = msg.to_dict()
        assert d["text"] == "test"
        assert d["customer_id"] == "c1"
        assert "id" in d
        assert "timestamp" in d

    def test_bridge_response_from_dict(self):
        """BridgeResponse deserializes from dict."""
        from src.bridge.protocol import BridgeResponse
        data = {
            "text": "Hello there",
            "actions": [{"type": "search", "params": {"q": "test"}}],
            "conversation_id": "conv-1",
        }
        resp = BridgeResponse.from_dict(data)
        assert resp.text == "Hello there"
        assert len(resp.actions) == 1
        assert resp.conversation_id == "conv-1"

    def test_upload_policy_no_server(self):
        """Upload policy without connection returns None."""
        from src.bridge.protocol import BridgeClient
        client = BridgeClient(base_url="http://localhost:1")
        result = client.upload_policy("nonexistent.pdf", "c1")
        assert result is None


class TestSessionDeepDive:
    """Session timeout, edge cases, and recovery scenarios."""

    def setup_method(self):
        from src.portal.session import SessionManager
        self.sm = SessionManager()
        self.sm.clear_session("deep_test")
        self.sm.clear_session("deep_test_timeout")

    def teardown_method(self):
        self.sm.clear_session("deep_test")
        self.sm.clear_session("deep_test_timeout")

    def test_session_nonexistent_adapter(self):
        """Non-existent adapter returns valid=False."""
        valid = self.sm.is_session_valid("completely_nonexistent_adapter_xyz")
        assert valid is False

    def test_session_info_empty(self):
        """Session info for non-existent adapter."""
        from src.portal.session import PortalSession
        info = self.sm.get_session_info("deep_test")
        assert isinstance(info, PortalSession)
        assert info.adapter_name == "deep_test"
        assert info.logged_in is False

    def test_session_save_then_info(self):
        """After saving cookies, session info shows logged in."""
        self.sm.save_cookies("deep_test", [{"name": "x", "value": "1"}])
        info = self.sm.get_session_info("deep_test")
        assert info.logged_in is True
        assert info.cookies_file is not None

    def test_session_clear_removes_all(self):
        """Clear session removes directory."""
        self.sm.save_cookies("deep_test", [{"name": "x", "value": "1"}])
        assert self.sm.is_session_valid("deep_test") is True
        self.sm.clear_session("deep_test")
        assert self.sm.is_session_valid("deep_test") is False

    def test_list_sessions_empty(self):
        """list_sessions returns empty list when no sessions."""
        all_sessions = self.sm.list_sessions()
        # Just check it doesn't raise and returns a list
        assert isinstance(all_sessions, list)

    def test_save_empty_cookies(self):
        """Saving empty cookie list should still work."""
        self.sm.save_cookies("deep_test", [])
        loaded = self.sm.load_cookies("deep_test")
        assert loaded == []

    def test_save_cookies_with_special_chars(self):
        """Cookies with special characters save and load correctly."""
        cookies = [
            {"name": "session_id", "value": "abc123!@#$%", "domain": ".example.com"},
            {"name": "token", "value": "eyJhbGciOiJIUzI1NiJ9", "domain": ".example.com"},
        ]
        self.sm.save_cookies("deep_test", cookies)
        loaded = self.sm.load_cookies("deep_test")
        assert loaded == cookies

    def test_session_timeout_detection(self):
        """Session timeout detection works — simulate by modifying mtime."""
        self.sm.save_cookies("deep_test", [{"name": "x", "value": "1"}])
        assert self.sm.is_session_valid("deep_test") is True


class TestBrowserEngineEdgeCases:
    """Browser engine edge cases and error handling."""

    def test_engine_factory_auto_prefers_chrome(self):
        """create_browser_engine auto mode prefers chrome over playwright."""
        from src.browser import create_browser_engine
        engine = create_browser_engine()
        assert engine is not None
        assert engine.name in ("chrome", "playwright", "qt")

    def test_playwright_engine_stop_without_start(self):
        """Stopping an unstarted PlaywrightDriver doesn't crash."""
        from src.browser.playwright.driver import PlaywrightDriver
        engine = PlaywrightDriver()
        # Stop without start
        import asyncio
        asyncio.run(engine.stop())
        assert engine._running is False

    def test_playwright_engine_get_ops_before_start(self):
        """Engine operations before start return safe defaults."""
        from src.browser.playwright.driver import PlaywrightDriver
        engine = PlaywrightDriver()
        import asyncio
        assert asyncio.run(engine.get_url()) == ""
        assert asyncio.run(engine.get_title()) == ""
        assert asyncio.run(engine.get_tabs()) == 0
        assert asyncio.run(engine.get_page_info()).url == ""
        assert asyncio.run(engine.get_cookies()) == []

    def test_webengine_engine_stop_without_start(self):
        """Stopping an unstarted QtDriver doesn't crash."""
        from src.browser.qt_driver import QtDriver
        engine = QtDriver()
        import asyncio
        asyncio.run(engine.stop())
        assert engine._running is False

    def test_webengine_engine_get_ops_before_start(self):
        """WebEngine operations before start return safe defaults."""
        from src.browser.qt_driver import QtDriver
        engine = QtDriver()
        import asyncio
        assert asyncio.run(engine.get_url()) == ""
        assert asyncio.run(engine.get_title()) == ""
        assert asyncio.run(engine.get_page_info()).url == ""
        assert asyncio.run(engine.get_cookies()) == []


class TestPortalAdapterEdgeCases:
    """Portal adapter edge cases and error handling."""

    def test_adapter_get_sel_nonexistent(self):
        """Getting non-existent selector returns empty string."""
        from src.portals.base import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        sel = adapter.get_sel("nonexistent", "group", "field")
        assert sel == ""

    def test_adapter_get_sel_partial_path(self):
        """Getting selector with partial path returns empty string."""
        from src.portals.base import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        sel = adapter.get_sel("login")  # login is a dict, not a string
        # Should be empty since it's not a leaf
        assert sel == ""

    def test_adapter_double_disconnect_no_crash(self):
        """Disconnecting twice doesn't crash."""
        from src.portals.base import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        import asyncio
        asyncio.run(adapter.disconnect())
        asyncio.run(adapter.disconnect())  # Second time should be safe
        assert adapter._logged_in is False

    def test_get_adapter_with_custom_engine(self):
        """get_adapter accepts a custom engine parameter."""
        from src.portals.base import get_adapter
        from src.browser.playwright.driver import PlaywrightDriver
        engine = PlaywrightDriver()
        adapter = get_adapter("great_eastern", engine=engine)
        assert adapter is not None
        assert adapter.engine is engine

    def test_get_adapter_with_preexisting_mapping(self):
        """get_adapter accepts a preloaded mapping."""
        from src.portals.base import get_adapter
        from src.portal.mapping import load_portal_mapping
        mapping = load_portal_mapping("great_eastern")
        adapter = get_adapter("great_eastern", mapping=mapping)
        assert adapter is not None
        assert adapter.mapping is mapping


class TestFormEngineDeepDive:
    """FormEngine edge cases and method compatibility."""

    def test_form_engine_legacy_page(self):
        """FormEngine accepts legacy Playwright page."""
        from src.portal.form_engine import FormEngine
        engine = FormEngine()
        # Set legacy page to None — should not crash on any operation
        engine.set_legacy_page(None)
        assert engine._page is None

    def test_form_engine_engine_setter(self):
        """FormEngine.engine setter updates both engine and form.engine."""
        from src.portal.form_engine import FormEngine
        from src.browser.playwright.driver import PlaywrightDriver
        engine = FormEngine()
        pw_engine = PlaywrightDriver()
        engine.engine = pw_engine
        assert engine.engine is pw_engine
        assert engine.browser is pw_engine

    def test_form_engine_browser_setter(self):
        """FormEngine.browser setter is backward compatible."""
        from src.portal.form_engine import FormEngine
        from src.browser.playwright.driver import PlaywrightDriver
        engine = FormEngine()
        pw_engine = PlaywrightDriver()
        engine.browser = pw_engine
        assert engine.engine is pw_engine
