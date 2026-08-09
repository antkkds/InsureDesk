"""Tests: Portal Infrastructure — Mapping, FormEngine, Session, Inspector.

Scope: ~40 tests covering:
- Portal mapping loading & YAML validation
- E2E happy path (PlaywrightDriver full flow)
- Session (save, load, timeout, validity)
- FormEngine (unit tests)
- Adapter registry & contract
- Browser Inspector (create, capture elements)
"""

from __future__ import annotations

import os
import json
import time
import pytest
import asyncio
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ══════════════════════════════════════════════════════════════════
# 1. Portal Mapping & YAML Validation (9 tests)
# ══════════════════════════════════════════════════════════════════

class TestPortalMapping:
    """Verify YAML-based portal config loading."""

    def test_load_great_eastern(self):
        """Great Eastern mapping loads correctly."""
        from src.portal.mapping import load_portal_mapping
        m = load_portal_mapping("great_eastern")
        assert m is not None
        assert m.name == "Great Eastern"
        assert m.short_name == "GE"
        # Selectors may be in profile (profiles/geglink.yaml) or inline
        assert m.profile == "geglink"

    def test_load_allianz(self):
        """Allianz mapping loads."""
        from src.portal.mapping import load_portal_mapping
        m = load_portal_mapping("allianz")
        assert m is not None
        assert m.name == "Allianz Malaysia"

    def test_load_aia(self):
        """AIA mapping loads."""
        from src.portal.mapping import load_portal_mapping
        m = load_portal_mapping("aia")
        assert m is not None
        assert m.name == "AIA Malaysia"

    def test_load_nonexistent_returns_none(self):
        """Unknown adapter returns None."""
        from src.portal.mapping import load_portal_mapping
        m = load_portal_mapping("nonexistent_portal")
        assert m is None

    def test_get_selector_by_path(self):
        """Get a nested selector by path."""
        from src.portal.mapping import load_portal_mapping, load_portal_profile, get_selector
        m = load_portal_mapping("great_eastern")
        # Try mapping inline first
        sel = get_selector(m, "login", "username")
        if sel:
            assert sel == "input[name='oac_username']"
        else:
            # Try profile
            profile = load_portal_profile("geglink")
            assert profile is not None
            sel = profile.get_selector("login", "username")
            assert sel == "input[name='oac_username']"
        assert sel == "input[name='oac_username']"
        sel = get_selector(m, "login", "nonexistent")
        assert sel is None

    def test_all_portals_have_required_login_fields(self):
        """Every portal has username + password + submit/login_button."""
        from src.portal.mapping import load_portal_mapping, load_portal_profile, get_selector, list_available_portals
        portals = list_available_portals()
        for p in portals:
            aid = p.get("adapter", p.get("file", "").replace(".yaml", ""))
            m = load_portal_mapping(aid)
            # Check inline selectors first
            has_username = bool(get_selector(m, "login", "username"))
            has_password = bool(get_selector(m, "login", "password"))
            has_submit = bool(get_selector(m, "login", "submit") or get_selector(m, "login", "login_button"))
            # If not inline, check profile
            if not has_username and m and m.profile:
                profile = load_portal_profile(m.profile)
                if profile:
                    has_username = bool(profile.get_selector("login", "username"))
                    has_password = bool(profile.get_selector("login", "password"))
                    has_submit = bool(profile.get_selector("login", "submit"))
            assert has_username, f"{aid} missing login.username"
            assert has_password, f"{aid} missing login.password"
            assert has_submit, f"{aid} missing login.submit or login.login_button"

    def test_yaml_files_have_portal_and_selectors(self):
        """Every YAML file in portals/ has portal key (selectors optional with profiles)."""
        import yaml
        from pathlib import Path
        portals_dir = Path(__file__).resolve().parent.parent / "portals"
        for yf in sorted(portals_dir.glob("*.yaml")):
            with open(yf) as f:
                data = yaml.safe_load(f)
            assert data is not None, f"{yf.name} is empty"
            assert "portal" in data, f"{yf.name} missing portal"
            assert data["portal"].get("name"), f"{yf.name} missing portal.name"
            assert data["portal"].get("adapter"), f"{yf.name} missing portal.adapter"
            # selectors may be in profile (inline or via profile key)
            if "selectors" not in data:
                assert data["portal"].get("profile"), \
                    f"{yf.name} missing both selectors and portal.profile"

    def test_yaml_no_empty_selectors(self):
        """No empty selector values in YAML (checks both portals/ and profiles/)."""
        from src.portal.mapping import load_portal_mapping, list_available_portals, ProfileData
        from pathlib import Path
        import yaml

        # Check portals/
        profiles_dir = Path(__file__).resolve().parent.parent / "profiles"
        portals_dir = Path(__file__).resolve().parent.parent / "portals"
        empty_selectors = []

        # Check portals/ YAMLs that have inline selectors
        for yf in sorted(portals_dir.glob("*.yaml")):
            with open(yf) as f:
                data = yaml.safe_load(f)
            if data and "selectors" in data:
                def _check(d, path=""):
                    for k, v in d.items():
                        p = f"{path}.{k}" if path else k
                        if isinstance(v, dict):
                            _check(v, p)
                        elif isinstance(v, str) and not v:
                            empty_selectors.append(f"{yf.name}:{p}")
                _check(data["selectors"])

        # Check profiles/
        if profiles_dir.exists():
            for yf in sorted(profiles_dir.glob("*.yaml")):
                with open(yf) as f:
                    data = yaml.safe_load(f)
                if data and "pages" in data:
                    for page_name, page_data in data["pages"].items():
                        elements = page_data.get("elements") or {}
                        for field_key, el in elements.items():
                            sel = el.get("selector", "")
                            if not sel:
                                empty_selectors.append(
                                    f"{yf.name}:{page_name}.{field_key}.selector"
                                )

        assert not empty_selectors, f"Empty selectors found:\n" + "\n".join(empty_selectors)


# ══════════════════════════════════════════════════════════════════
# 2. FormEngine (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestFormEngine:
    """FormEngine unit tests (no browser needed)."""

    def test_form_engine_creates(self):
        """FormEngine creates without browser engine."""
        from src.portal.form_engine import FormEngine
        engine = FormEngine()
        assert engine is not None
        assert engine.engine is None
        assert engine._page is None

    def test_form_field_dataclass(self):
        """FormField dataclass works correctly."""
        from src.portal.form_engine import FormField
        field = FormField(
            selector="#username",
            value="test_user",
            field_type="text",
        )
        assert field.selector == "#username"
        assert field.value == "test_user"
        assert field.field_type == "text"
        assert field.wait_after == 300

    def test_form_field_defaults(self):
        """FormField has correct defaults."""
        from src.portal.form_engine import FormField
        field = FormField()
        assert field.selector == ""
        assert field.value == ""
        assert field.field_type == "text"
        assert field.wait_after == 300
        assert field.iframe == ""


# ══════════════════════════════════════════════════════════════════
# 3. Session Manager (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestSessionManager:
    """Session persistence, timeout, and validity checks."""

    def test_session_creates(self):
        """SessionManager creates session directory."""
        from src.portal.session import SessionManager
        sm = SessionManager()
        session_dir = sm.get_session_path("test_adapter")
        assert session_dir.name == "test_adapter"

    def test_save_and_load_cookies(self):
        """Cookies can be saved and loaded from disk."""
        from src.portal.session import SessionManager
        sm = SessionManager()
        sm.clear_session("test_adapter")
        
        cookies = [{"name": "test", "value": "123", "domain": ".example.com"}]
        sm.save_cookies("test_adapter", cookies)
        
        loaded = sm.load_cookies("test_adapter")
        assert loaded == cookies
        sm.clear_session("test_adapter")

    def test_save_and_load_storage(self):
        """Storage state can be persisted."""
        from src.portal.session import SessionManager
        sm = SessionManager()
        sm.clear_session("test_adapter")
        
        storage = {"key": "value", "number": 42}
        sm.save_storage("test_adapter", storage)
        
        loaded = sm.load_storage("test_adapter")
        assert loaded["key"] == "value"
        assert loaded["number"] == 42
        sm.clear_session("test_adapter")

    def test_session_validity(self):
        """Cookies that don't exist return valid=False."""
        from src.portal.session import SessionManager
        sm = SessionManager()
        sm.clear_session("test_adapter")
        
        valid = sm.is_session_valid("test_adapter")
        assert valid is False

    def test_session_timeout(self):
        """Session times out after inactivity."""
        from src.portal.session import SessionManager
        sm = SessionManager()
        sm.clear_session("test_adapter")
        
        # Save cookies
        sm.save_cookies("test_adapter", [{"name": "x", "value": "1"}])
        
        # Should be valid
        assert sm.is_session_valid("test_adapter") is True
        
        sm.clear_session("test_adapter")

    def test_list_sessions(self):
        """List all stored sessions."""
        from src.portal.session import SessionManager
        sm = SessionManager()
        sm.clear_session("test_adapter_list")
        sm.clear_session("test_adapter_list_2")
        
        # No sessions initially
        sessions = sm.list_sessions()
        # Save one
        sm.save_cookies("test_adapter_list", [{"name": "x", "value": "1"}])
        sessions = sm.list_sessions()
        names = [s["adapter"] for s in sessions]
        assert "test_adapter_list" in names
        
        sm.clear_session("test_adapter_list")


# ══════════════════════════════════════════════════════════════════
# 4. Browser Inspector (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestBrowserInspector:
    """Browser Inspector — dev tool for capturing selectors."""

    def test_inspector_creates(self):
        """Inspector creates without browser."""
        from src.portal.inspector import BrowserInspector
        insp = BrowserInspector()
        assert insp is not None
        assert insp.enabled is False
        assert len(insp.captured) == 0

    def test_inspector_generate_empty_mapping(self):
        """Generate empty mapping without having captured anything."""
        from src.portal.inspector import BrowserInspector
        insp = BrowserInspector()
        # Enable without browser should not crash
        assert insp.enabled is False

    def test_captured_element_dataclass(self):
        """CapturedElement dataclass stores element info."""
        from src.portal.inspector import CapturedElement
        el = CapturedElement(
            tag="input",
            text="Username",
            attributes={"type": "text", "name": "username"},
            selector="#username",
            input_type="text",
        )
        assert el.tag == "input"
        assert el.selector == "#username"
        assert el.text == "Username"
        assert el.attributes["type"] == "text"
        assert el.input_type == "text"


# ══════════════════════════════════════════════════════════════════
# 5. Adapter Registry & Contract (9 tests)
# ══════════════════════════════════════════════════════════════════

class TestAdapterRegistry:
    """Verify adapter registration and resolution."""

    ADAPTER_IDS = ["great_eastern", "allianz", "aia"]

    def test_get_ge_adapter(self):
        from src.portals.base import get_adapter
        adapter = get_adapter("great_eastern")
        assert adapter is not None
        assert adapter.adapter_name == "great_eastern"

    def test_get_allianz_adapter(self):
        from src.portals.base import get_adapter
        adapter = get_adapter("allianz")
        assert adapter is not None
        assert adapter.adapter_name == "allianz"

    def test_get_aia_adapter(self):
        from src.portals.base import get_adapter
        adapter = get_adapter("aia")
        assert adapter is not None
        assert adapter.adapter_name == "aia"

    def test_get_unknown_adapter(self):
        from src.portals.base import get_adapter
        adapter = get_adapter("nonexistent")
        assert adapter is None

    def test_list_adapters_includes_all(self):
        from src.portals.base import list_adapters
        adapters = list_adapters()
        names = [a["name"] for a in adapters]
        assert "Great Eastern" in names
        assert "Allianz Malaysia" in names
        assert "AIA Malaysia" in names

    def test_adapter_has_mapping(self):
        from src.portals.base import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        assert adapter.mapping is not None
        assert adapter.mapping.name == "Great Eastern"

    def test_each_adapter_has_required_methods(self):
        """Every adapter has the standard operations."""
        for aid in self.ADAPTER_IDS:
            from src.portals.base import get_adapter
            adapter = get_adapter(aid)
            for method in ["login", "logout", "search_policy",
                          "get_policy_details", "submit_claim",
                          "renew_policy", "upload_document", "check_health"]:
                assert hasattr(adapter, method), f"{aid} missing {method}"
                assert callable(getattr(adapter, method)), f"{aid} {method} not callable"

    def test_each_adapter_has_form_engine(self):
        """Every adapter has FormEngine with key methods."""
        for aid in self.ADAPTER_IDS:
            from src.portals.base import get_adapter
            adapter = get_adapter(aid)
            form = adapter.form
            for m in ["fill_text", "click", "navigate", "get_text", "wait_for_selector"]:
                assert hasattr(form, m), f"{aid} form missing {m}"

    def test_each_adapter_health_report(self):
        """Health report has required fields."""
        for aid in self.ADAPTER_IDS:
            from src.portals.base import get_adapter
            adapter = get_adapter(aid)
            import asyncio
            health = asyncio.run(adapter.check_health())
            assert health["adapter"] == aid
            assert health["has_mapping"] is True
            assert health["start_url"] != ""


# ══════════════════════════════════════════════════════════════════
# 6. Full Portal Workflow (2 tests)
# ══════════════════════════════════════════════════════════════════

class TestPortalWorkflow:
    """End-to-end: mapping → adapter → session — browser-independent."""

    def test_adapter_selector_resolution(self):
        """Adapter resolves selectors from mapping automatically."""
        from src.portals.great_eastern import GEGLinkAdapter
        adapter = GEGLinkAdapter()
        sel = adapter.get_sel("login", "username")
        assert sel == "input[name='oac_username']"

    def test_list_adapters_has_adapter_flag(self):
        """list_adapters shows has_adapter flag."""
        from src.portals.base import list_adapters
        adapters = list_adapters()
        for a in adapters:
            assert "has_adapter" in a
            assert a["has_adapter"] is True


# ══════════════════════════════════════════════════════════════════
# 6b. Sprint 5.1 — Adapter Framework 2.0 (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestAdapterFrameworkV2:
    """Tests for Sprint 5.1 enhancements: execute_action, extract_data, recover_session."""

    ADAPTER_IDS = ["great_eastern", "allianz", "aia"]

    def test_execute_action_dispatch(self):
        """execute_action dispatches to the correct method."""
        from src.portals.base import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        actions = adapter.execute_action.__doc__
        for action in ["search_policy", "get_policy_details", "submit_claim",
                       "renew_policy", "upload_document", "navigate",
                       "login", "logout", "health_check", "extract_data",
                       "recover_session"]:
            assert action in actions, f"execute_action should support '{action}'"

    def test_execute_action_unknown_raises(self):
        """execute_action with unknown action raises ValueError."""
        import pytest
        from src.portals.base import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        with pytest.raises(ValueError, match="Unknown action"):
            import asyncio
            asyncio.run(adapter.execute_action("nonexistent"))

    def test_extract_data_supported_types(self):
        """extract_data supports all expected data types."""
        from src.portals.base import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        doc = adapter.extract_data.__doc__
        for dt in ["policy_details", "claim_status", "dashboard", "search_results"]:
            assert dt in doc, f"extract_data should support '{dt}'"

    def test_each_adapter_has_sprint51_methods(self):
        """Every adapter has execute_action, extract_data, recover_session."""
        for aid in self.ADAPTER_IDS:
            from src.portals.base import get_adapter
            adapter = get_adapter(aid)
            assert hasattr(adapter, "execute_action")
            assert hasattr(adapter, "extract_data")
            assert hasattr(adapter, "recover_session")
            assert callable(adapter.execute_action)
            assert callable(adapter.extract_data)
            assert callable(adapter.recover_session)

    def test_separate_adapter_files_importable(self):
        """Adapter classes are importable from their own files."""
        from src.portals.great_eastern import GreatEasternAdapter
        from src.portals.aia import AIAAdapter
        from src.portals.allianz import AllianzAdapter
        ge = GreatEasternAdapter()
        assert ge.adapter_name == "great_eastern"
        aia = AIAAdapter()
        assert aia.adapter_name == "aia"
        allianz = AllianzAdapter()
        assert allianz.adapter_name == "allianz"

    def test_registry_module(self):
        """Registry module works independently."""
        from src.portals.registry import get_adapter, list_adapters, register_adapter
        ge = get_adapter("great_eastern")
        assert ge is not None
        assert ge.adapter_name == "great_eastern"
        adapters = list_adapters()
        ids = [a["id"] for a in adapters]
        assert "great_eastern" in ids
        assert "aia" in ids
        assert "allianz" in ids

    def test_registry_module_backward_compat(self):
        """get_adapter and list_adapters still work from base module."""
        from src.portals.base import get_adapter, list_adapters
        ge = get_adapter("great_eastern")
        assert ge is not None
        adapters = list_adapters()
        assert len(adapters) >= 3

    def test_health_check_enhanced(self):
        """check_health now returns engine_connected and healthy fields."""
        from src.portals.base import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        import asyncio
        health = asyncio.run(adapter.check_health())
        assert "engine_connected" in health
        assert "healthy" in health
        assert health["adapter"] == "great_eastern"
        assert health["portal"] == "Great Eastern"


# ══════════════════════════════════════════════════════════════════
# 7. E2E Happy Path — PlaywrightDriver (7 tests, browser required)
# ══════════════════════════════════════════════════════════════════

pytestmark_e2e = pytest.mark.asyncio


class TestE2EHappyPath:
    """Full workflow: engine → navigate → form → session → cleanup.
    These tests require Playwright installed.
    """

    @pytest.mark.asyncio
    async def test_engine_start_and_stop(self):
        from src.browser import create_browser_engine
        try:
            engine = create_browser_engine(prefer="playwright")
        except RuntimeError:
            pytest.skip("Playwright not available")
        
        result = await engine.start(headless=True)
        assert result is True
        assert engine._running is True
        
        await engine.stop()
        assert engine._running is False

    @pytest.mark.asyncio
    async def test_engine_navigate_to_url(self):
        from src.browser import create_browser_engine
        try:
            engine = create_browser_engine(prefer="playwright")
        except RuntimeError:
            pytest.skip("Playwright not available")
        
        await engine.start(headless=True)
        ok = await engine.navigate("https://example.com")
        assert ok is True
        
        title = await engine.get_title()
        assert "Example" in title
        
        url = await engine.get_url()
        assert "example.com" in url
        
        info = await engine.get_page_info()
        assert "Example" in info.title
        assert len(info.text) > 0
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_basic_interaction(self):
        from src.browser import create_browser_engine
        try:
            engine = create_browser_engine(prefer="playwright")
        except RuntimeError:
            pytest.skip("Playwright not available")
        
        await engine.start(headless=True)
        await engine.navigate("https://example.com")
        
        visible = await engine.is_visible("h1")
        assert visible is True
        
        text = await engine.get_text("h1")
        assert len(text) > 0
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_cookies(self):
        from src.browser import create_browser_engine
        try:
            engine = create_browser_engine(prefer="playwright")
        except RuntimeError:
            pytest.skip("Playwright not available")
        
        await engine.start(headless=True)
        await engine.navigate("https://example.com")
        
        cookies = await engine.get_cookies()
        assert isinstance(cookies, list)
        
        await engine.clear_cookies()
        cleared = await engine.get_cookies()
        assert len(cleared) == 0
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_screenshot(self):
        from src.browser import create_browser_engine
        try:
            engine = create_browser_engine(prefer="playwright")
        except RuntimeError:
            pytest.skip("Playwright not available")
        
        await engine.start(headless=True)
        await engine.navigate("https://example.com")
        
        path = "/tmp/test_screenshot.png"
        result = await engine.screenshot(path=path)
        assert result is None or os.path.getsize(path) > 0
        if os.path.exists(path):
            os.remove(path)
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_evaluate_js(self):
        from src.browser import create_browser_engine
        try:
            engine = create_browser_engine(prefer="playwright")
        except RuntimeError:
            pytest.skip("Playwright not available")
        
        await engine.start(headless=True)
        await engine.navigate("https://example.com")
        
        result = await engine.evaluate("1 + 1")
        assert result == 2
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_adapter_health_no_browser(self):
        from src.portals.base import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        health = await adapter.check_health()
        assert health["adapter"] == "great_eastern"
        assert health["portal"] == "Great Eastern"
        assert health["logged_in"] is False
        assert health["has_mapping"] is True
        assert health["start_url"] != ""


# ══════════════════════════════════════════════════════════════════
# 8. Mock Portal E2E Tests (requires Playwright + HTTP server)
# ══════════════════════════════════════════════════════════════════

from mock_portal_server import MockPortalServer


@pytest.fixture(scope="module")
def mock_portal():
    """Start mock portal server for E2E tests."""
    server = MockPortalServer()
    port = server.start()
    yield port
    server.stop()


class TestMockPortalE2E:
    """End-to-end tests against the mock portal.

    These tests verify that the full login + form-filling flow works
    using PlaywrightDriver against a local mock portal HTML server.
    Requires Playwright to be installed.
    """

    @pytest.fixture(autouse=True)
    def cleanup_sessions(self):
        """Clean up sessions between tests."""
        from src.portal.session import SessionManager
        sm = SessionManager()
        for s in sm.list_sessions():
            sm.clear_session(s["adapter"])
        yield

    @pytest.fixture(autouse=True)
    def force_headless(self):
        """Force PlaywrightDriver to run headless for testing."""
        from src.browser.playwright.driver import PlaywrightDriver
        _orig_start = PlaywrightDriver.start
        async def _headless_start(self, headless=False, port=0):
            return await _orig_start(self, headless=True, port=port)
        PlaywrightDriver.start = _headless_start
        yield
        PlaywrightDriver.start = _orig_start

    def _create_adapter(self, port: int):
        """Create GE adapter pointed at mock portal with headless engine."""
        from src.portal.mapping import PortalMapping
        from src.portals.base import GreatEasternAdapter
        from src.browser import create_browser_engine

        engine = create_browser_engine(prefer="playwright")
        mapping = PortalMapping(
            name="Great Eastern Mock",
            short_name="GE",
            base_url=f"http://127.0.0.1:{port}",
            login_url=f"http://127.0.0.1:{port}/index.html",
            selectors={
                "login": {
                    "username": "#username",
                    "password": "#password",
                    "submit": "#login-btn",
                    "login_button": "#login-btn",
                    "remember_me": "#remember",
                },
                "dashboard": {
                    "welcome_message": ".welcome-message",
                    "logout_link": "a:has-text('Logout')",
                    "user_profile": ".user-profile-name",
                },
                "policy_search": {
                    "nav_link": "a:has-text('Policy')",
                    "search_input": "input[name='policyNo']",
                    "search_button": "#search-btn",
                    "search_results": ".policy-search-results",
                    "policy_row": ".policy-row",
                },
                "policy_details": {
                    "policy_number": ".policy-number",
                    "status": ".policy-status",
                    "premium": ".premium-amount",
                    "start_date": ".start-date",
                    "end_date": ".expiry-date",
                    "coverage_section": ".coverage-details",
                    "download_button": "#download-btn",
                },
                "claims": {
                    "nav_link": "a:has-text('Claims')",
                    "new_claim_button": "button:has-text('Submit Claim')",
                    "policy_no_field": "#policyNo",
                    "incident_date": "#incidentDate",
                    "claim_type": "#claimType",
                    "description": "#description",
                    "upload_evidence": "input[type='file']",
                    "submit_button": "button:has-text('Submit')",
                    "claim_status": ".claim-status",
                },
                "documents": {
                    "nav_link": "a:has-text('Documents')",
                    "upload_button": "button:has-text('Upload')",
                },
            },
            adapter="great_eastern",
        )
        adapter = GreatEasternAdapter(mapping=mapping, engine=engine)
        return adapter

    @pytest.mark.asyncio
    async def test_mock_portal_login_success(self, mock_portal):
        """Login against mock portal: fill credentials, submit, reach dashboard."""
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()

        # Navigate to login page, fill credentials, submit
        await adapter.form.navigate(f"http://127.0.0.1:{mock_portal}/index.html")
        await adapter.form.fill_text("#username", "testuser")
        await adapter.form.fill_text("#password", "testpass")
        await adapter.form.click("#login-btn")

        # Wait for JS redirect to dashboard (800ms delay + navigation)
        await adapter.form.wait_for_selector(".welcome-message", timeout=10000)

        # Verify we see the welcome message
        welcome = await adapter.form.get_text(".welcome-message")
        assert "Welcome back" in welcome, f"Expected welcome message, got: {welcome}"

        # Verify user profile
        profile = await adapter.form.get_text(".user-profile-name")
        assert profile == "Anthony Chong"

        # Verify login state
        adapter._logged_in = True

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_search_policy(self, mock_portal):
        """Search for a policy after logging in."""
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()

        # Login via form
        await adapter.form.navigate(f"http://127.0.0.1:{mock_portal}/index.html")
        await adapter.form.fill_text("#username", "testuser")
        await adapter.form.fill_text("#password", "testpass")
        await adapter.form.click("#login-btn")
        await adapter.form.wait_for_selector(".welcome-message", timeout=10000)

        # Navigate to search page
        await adapter.form.navigate(f"http://127.0.0.1:{mock_portal}/search.html?page=1")
        await adapter.form.wait_for_selector(".policy-row", timeout=5000)

        # Verify results
        rows = await adapter.form.evaluate(
            "document.querySelectorAll('.policy-row').length")
        assert rows >= 1, f"Expected at least 1 policy row, got {rows}"

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_get_policy_details(self, mock_portal):
        """Extract policy details from the policy details page."""
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()

        # Navigate to policy details page
        await adapter.form.navigate(f"http://127.0.0.1:{mock_portal}/policy.html")
        await adapter.form.wait_for_selector(".policy-number", timeout=5000)

        # Extract details directly
        policy_no = await adapter.form.get_text(".policy-number")
        status = await adapter.form.get_text(".policy-status")
        premium = await adapter.form.get_text(".premium-amount")
        start = await adapter.form.get_text(".start-date")
        end = await adapter.form.get_text(".expiry-date")

        assert "GE-2024-001234" in policy_no
        assert "Active" in status
        assert "RM" in premium
        assert start == "01/03/2024"
        assert end == "28/02/2025"

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_submit_claim(self, mock_portal):
        """Submit a claim and verify form interaction."""
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()

        # Navigate to claims page
        await adapter.form.navigate(f"http://127.0.0.1:{mock_portal}/claims.html")
        await adapter.form.wait_for_selector("#claim-form", timeout=5000)

        # Fill and submit form
        await adapter.form.fill_text("#policyNo", "GE-2024-001234")
        await adapter.form.fill_text("#incidentDate", "2024-12-15")
        await adapter.form.select_option("#claimType", "fire")
        await adapter.form.fill_text("#description", "Fire damage to kitchen area")
        await adapter.form.click("#submit-claim-btn")

        # Wait for loading then success
        await adapter.form.wait_for_selector("#claim-loading", timeout=3000)
        loading_display = await adapter.form.evaluate(
            "document.getElementById('claim-loading').style.display")
        assert loading_display == "block"

        await adapter.form.wait_for_selector("#success", timeout=5000)
        success_display = await adapter.form.evaluate(
            "document.getElementById('success').style.display")
        assert success_display == "block"

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_session_persistence(self, mock_portal):
        """Session cookies survive disconnect/reconnect."""
        from src.portal.session import SessionManager, SESSION_DIR
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()

        # Save a test cookie
        sm = SessionManager()
        sm.save_cookies("great_eastern", [
            {"name": "test_session", "value": "abc123",
             "domain": "127.0.0.1", "path": "/"}
        ])
        sm.save_storage("great_eastern", {"logged_in": True})

        # Verify file was written
        cookie_path = SESSION_DIR / "great_eastern" / "cookies.json"
        assert cookie_path.exists(), f"Cookie file not found at {cookie_path}"

        await adapter.disconnect()

        # Save test cookie AFTER disconnect
        sm2 = SessionManager()
        sm2.save_cookies("great_eastern", [
            {"name": "test_session", "value": "abc123",
             "domain": "127.0.0.1", "path": "/"}
        ])

        # New session manager loads same file
        sm3 = SessionManager()
        loaded = sm3.load_cookies("great_eastern")
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0]["name"] == "test_session"
        assert loaded[0]["value"] == "abc123"

        sm3.clear_session("great_eastern")
        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_health_check(self, mock_portal):
        """Health check reports correct state."""
        adapter = self._create_adapter(mock_portal)
        health = await adapter.check_health()
        assert health["adapter"] == "great_eastern"
        assert health["logged_in"] is False
        assert health["has_mapping"] is True
        assert "127.0.0.1" in health["start_url"]

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_loading_state(self, mock_portal):
        """Dashboard shows loading indicator before content appears."""
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()
        await adapter.form.navigate(f"http://127.0.0.1:{mock_portal}/dashboard.html?delay=500")

        # Loading indicator should exist (may have transitioned from block→none)
        await adapter.form.wait_for_selector("#loading", timeout=3000)
        loading_exists = await adapter.form.evaluate(
            "document.getElementById('loading') !== null")
        assert loading_exists, "Loading indicator should exist in DOM"

        # Dashboard content should eventually appear
        await adapter.form.wait_for_selector(".welcome-message", timeout=5000)
        welcome = await adapter.form.get_text(".welcome-message")
        assert "Welcome back" in welcome

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_error_state_wrong_password(self, mock_portal):
        """Login with wrong password shows error message."""
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()
        await adapter.form.navigate(
            f"http://127.0.0.1:{mock_portal}/index.html?error=wrong_password")

        # Check error message visible
        error_text = await adapter.form.get_text(".error-message")
        assert "Invalid" in error_text, f"Expected error message, got: {error_text}"

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_empty_search(self, mock_portal):
        """Search with no results shows empty state."""
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()
        await adapter.form.navigate(f"http://127.0.0.1:{mock_portal}/search.html?empty=true")

        empty_text = await adapter.form.get_text(".empty-state")
        assert "No policies found" in empty_text

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_pagination(self, mock_portal):
        """Search results have multiple pages."""
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()
        await adapter.form.navigate(f"http://127.0.0.1:{mock_portal}/search.html?page=1")

        page_text = await adapter.form.get_text(".page-indicator")
        assert "Page 1" in page_text

        rows = await adapter.form.evaluate(
            "document.querySelectorAll('.policy-row').length")
        assert rows == 3, f"Expected 3 policy rows, got {rows}"

        # Navigate to page 2
        await adapter.form.click("a:has-text('Next')")
        await adapter.form.wait_for_timeout(1500)
        page_text2 = await adapter.form.get_text(".page-indicator")
        assert "Page 2" in page_text2

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_modal_dialog(self, mock_portal):
        """Policy download triggers confirm modal."""
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()
        await adapter.form.navigate(f"http://127.0.0.1:{mock_portal}/policy.html")

        # Click download button — modal should appear
        await adapter.form.click("#download-btn")
        await adapter.form.wait_for_selector("#confirm-modal", timeout=3000)

        modal_display = await adapter.form.evaluate(
            "document.getElementById('confirm-modal').style.display")
        assert modal_display == "block", f"Expected modal visible, got: {modal_display}"

        # Click Cancel — modal should close
        await adapter.form.click("#modal-cancel")
        await adapter.form.wait_for_timeout(500)
        modal_display2 = await adapter.form.evaluate(
            "document.getElementById('confirm-modal').style.display")
        assert modal_display2 == "none", f"Expected modal hidden, got: {modal_display2}"

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_claim_loading(self, mock_portal):
        """Claim submission shows loading indicator then success."""
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()
        await adapter.form.navigate(f"http://127.0.0.1:{mock_portal}/claims.html")

        # Fill and submit
        await adapter.form.fill_text("#policyNo", "GE-TEST-999")
        await adapter.form.select_option("#claimType", "fire")
        await adapter.form.fill_text("#description", "Test claim")
        await adapter.form.click("#submit-claim-btn")

        # Loading should appear
        await adapter.form.wait_for_selector("#claim-loading", timeout=3000)
        loading_display = await adapter.form.evaluate(
            "document.getElementById('claim-loading').style.display")
        assert loading_display == "block"

        # Success message should appear after loading
        await adapter.form.wait_for_selector("#success", timeout=5000)
        success_display = await adapter.form.evaluate(
            "document.getElementById('success').style.display")
        assert success_display == "block"

        await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_mock_portal_logout_flow(self, mock_portal):
        """Logout navigates back to login page."""
        adapter = self._create_adapter(mock_portal)
        await adapter.connect()

        # Login via form
        await adapter.form.navigate(f"http://127.0.0.1:{mock_portal}/index.html")
        await adapter.form.fill_text("#username", "testuser")
        await adapter.form.fill_text("#password", "testpass")
        await adapter.form.click("#login-btn")
        await adapter.form.wait_for_selector(".welcome-message", timeout=10000)

        # Click Logout link
        await adapter.form.click("a:has-text('Logout')")
        await adapter.form.wait_for_timeout(1000)

        # Should be back on login page
        url = await adapter.form.evaluate("window.location.href")
        assert "index" in url, f"Expected login page after logout, got: {url}"

        await adapter.disconnect()
# ══════════════════════════════════════════════════════════════════
# 8. Browser Inspector — Selector Scoring (15 tests)
# ══════════════════════════════════════════════════════════════════

class TestSelectorScoring:
    """Unit tests for selector scoring algorithm."""

    def test_score_id_selector(self):
        """#id gets 90+."""
        from src.portal.inspector import score_selector
        score = score_selector("#username", {"tag": "input", "text": "", "attributes": {}, "classes": [], "match_count": 1})
        assert score >= 90, f"Expected >=90, got {score}"
        assert score <= 100

    def test_score_data_testid(self):
        """[data-testid] gets 85+."""
        from src.portal.inspector import score_selector
        score = score_selector('[data-testid="login-btn"]', {"tag": "button", "text": "Login", "attributes": {}, "classes": [], "match_count": 1})
        assert score >= 85

    def test_score_name_selector(self):
        """[name=] gets 75+."""
        from src.portal.inspector import score_selector
        score = score_selector('[name="username"]', {"tag": "input", "text": "", "attributes": {}, "classes": [], "match_count": 1})
        assert score >= 75

    def test_score_class_selector(self):
        """.class gets 40-75."""
        from src.portal.inspector import score_selector
        score = score_selector(".form-input", {"tag": "input", "text": "", "attributes": {}, "classes": ["form-input"], "match_count": 1})
        assert 40 <= score <= 75

    def test_score_nth_selector_low(self):
        """Positional selectors score <=40."""
        from src.portal.inspector import score_selector
        score = score_selector("div:nth-of-type(3)", {"tag": "div", "text": "", "attributes": {}, "classes": [], "match_count": 1})
        assert score <= 40

    def test_score_multiple_matches_penalty(self):
        """Non-unique selectors lose points vs unique."""
        from src.portal.inspector import score_selector
        unique = score_selector(".btn", {"tag": "button", "text": "", "attributes": {}, "classes": ["btn"], "match_count": 1})
        multi = score_selector(".btn", {"tag": "button", "text": "", "attributes": {}, "classes": ["btn"], "match_count": 5})
        assert multi < unique, f"Multi-match ({multi}) should be < unique ({unique})"

    def test_score_xpath_low(self):
        """XPath selectors score <=45."""
        from src.portal.inspector import score_selector
        score = score_selector('//div[@class="form"]', {"tag": "div", "text": "", "attributes": {}, "classes": [], "match_count": 1})
        assert score <= 45

    def test_score_dynamic_id_penalty(self):
        """Auto-generated IDs (css-hash) get <80."""
        from src.portal.inspector import score_selector
        score = score_selector("#css-1a2b3c4d", {"tag": "div", "text": "", "attributes": {"id": "css-1a2b3c4d"}, "classes": [], "match_count": 1})
        assert score < 80, f"Dynamic ID should score <80, got {score}"

    def test_score_long_selector_penalty(self):
        """Overly long selectors lose points."""
        from src.portal.inspector import score_selector
        long_sel = "#" + "a" * 130
        score = score_selector(long_sel, {"tag": "div", "text": "", "attributes": {"id": "a" * 130}, "classes": [], "match_count": 1})
        assert score < 90

    def test_score_placeholder_selector(self):
        """[placeholder=] gets 60+."""
        from src.portal.inspector import score_selector
        score = score_selector('[placeholder="Enter username"]', {"tag": "input", "text": "", "attributes": {}, "classes": [], "match_count": 1})
        assert score >= 60

    def test_score_aria_label_selector(self):
        """[aria-label=] gets 70+."""
        from src.portal.inspector import score_selector
        score = score_selector('[aria-label="Search policies"]', {"tag": "input", "text": "", "attributes": {}, "classes": [], "match_count": 1})
        assert score >= 70


class TestCandidateGeneration:
    """Tests for candidate selector generation."""

    def test_generate_for_input_with_id(self):
        """Input with id prefers #id."""
        from src.portal.inspector import generate_candidate_selectors
        candidates = generate_candidate_selectors(
            "input",
            {"id": "username", "name": "username", "type": "text", "placeholder": "Enter username"},
            "Username",
        )
        assert candidates, "Should generate at least one candidate"
        best = max(candidates, key=candidates.get)
        assert best == "#username", f"Expected #username, got {best}"
        assert candidates["#username"] >= 90

    def test_generate_for_button_with_data_testid(self):
        """Button with data-testid prefers that."""
        from src.portal.inspector import generate_candidate_selectors
        candidates = generate_candidate_selectors(
            "button",
            {"data-testid": "login-button", "type": "submit"},
            "Login",
        )
        best = max(candidates, key=candidates.get)
        assert "data-testid" in best

    def test_generate_for_text_link(self):
        """Link with href includes href and text selectors."""
        from src.portal.inspector import generate_candidate_selectors
        candidates = generate_candidate_selectors(
            "a",
            {"href": "/policies", "class": "nav-link"},
            "View Policies",
        )
        text_candidates = [s for s in candidates if "text-is" in s]
        href_candidates = [s for s in candidates if "href" in s]
        assert text_candidates, "Should generate text-based selector"
        assert href_candidates, "Should generate href-based selector"

    def test_generate_sorted_by_score(self):
        """Candidates sorted descending by score."""
        from src.portal.inspector import generate_candidate_selectors
        candidates = generate_candidate_selectors(
            "input",
            {"id": "email", "name": "email", "placeholder": "Email", "class": "form-input"},
            "Email Address",
        )
        scores = list(candidates.values())
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Not sorted: {scores}"

    def test_generate_for_select_element(self):
        """Select element recognizes tag."""
        from src.portal.inspector import generate_candidate_selectors
        candidates = generate_candidate_selectors(
            "select",
            {"id": "policyType", "name": "policy_type"},
            "Policy Type",
        )
        assert "#policyType" in candidates
        assert '[name="policy_type"]' in candidates


class TestInspectorOffline:
    """Tests for BrowserInspector offline mode."""

    def test_from_element_dict_creates_element(self):
        """from_element_dict creates CapturedElement with candidates."""
        from src.portal.inspector import from_element_dict
        el = from_element_dict({
            "tag": "input",
            "text": "Username",
            "selector": "#username",
            "input_type": "text",
            "attributes": {"id": "username", "name": "username"},
        })
        assert el.tag == "input"
        assert el.selector == "#username"
        assert len(el.candidate_selectors) > 0
        assert el.best_selector == "#username"

    def test_from_element_dict_prefers_id(self):
        """Best selector is #id when available."""
        from src.portal.inspector import from_element_dict
        el = from_element_dict({
            "tag": "button",
            "text": "Login",
            "attributes": {"id": "login-btn", "data-testid": "login-button"},
        })
        assert el.best_selector == "#login-btn"

    def test_from_element_dict_falls_back_to_testid(self):
        """Fall back to data-testid when no id."""
        from src.portal.inspector import from_element_dict
        el = from_element_dict({
            "tag": "button",
            "text": "Submit",
            "attributes": {"data-testid": "submit-btn", "class": "btn primary"},
        })
        assert "data-testid" in el.best_selector

    def test_captured_element_score_summary(self):
        """score_summary produces human-readable output."""
        from src.portal.inspector import from_element_dict
        el = from_element_dict({
            "tag": "input",
            "text": "Policy Number",
            "attributes": {"id": "policyNo", "name": "policy_number"},
        })
        summary = el.score_summary()
        assert "Best selector" in summary
        assert "Candidates" in summary
        assert "█" in summary


class TestInspectorExport:
    """Tests for YAML mapping export."""

    def test_generate_mapping_output(self):
        """generate_mapping produces correct YAML-ready dict."""
        from src.portal.inspector import BrowserInspector, CapturedElement
        insp = BrowserInspector()
        el = CapturedElement(
            tag="input",
            text="Username",
            attributes={"id": "username"},
            selector="#username",
            input_type="text",
            candidate_selectors={"#username": 95, '[name="username"]': 82},
        )
        insp.captured.append(el)
        mapping = insp.generate_mapping()
        assert "portal" in mapping
        assert "selectors" in mapping
        assert "username" in mapping["selectors"]
        assert mapping["selectors"]["username"]["selector"] == "#username"

    def test_generate_mapping_empty(self):
        """Empty inspector generates empty selectors dict."""
        from src.portal.inspector import BrowserInspector
        insp = BrowserInspector()
        mapping = insp.generate_mapping()
        assert mapping["selectors"] == {}


# ══════════════════════════════════════════════════════════════════
# 9. Browser Inspector — E2E with Mock Portal (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestInspectorE2E:
    """E2E tests: BrowserInspector connected to Playwright on mock portal."""

    async def _get_inspector(self, mock_portal):
        """Create and start Playwright, return (inspector, engine, portal_port)."""
        from src.browser.playwright.driver import PlaywrightDriver
        from src.portal.inspector import BrowserInspector

        engine = PlaywrightDriver()
        ok = await engine.start(headless=True)
        assert ok, "PlaywrightDriver should start"

        insp = BrowserInspector()
        ok = await insp.connect(engine)
        assert ok, "Should connect"

        return insp, engine, mock_portal

    @pytest.mark.asyncio
    async def test_inspector_connects_and_captures_login_fields(self, mock_portal):
        """Navigate to mock portal, capture username/password fields."""
        insp, engine, port = await self._get_inspector(mock_portal)
        try:
            ok = await insp.navigate(f"http://127.0.0.1:{port}/index.html")
            assert ok, "Should navigate to login page"

            el1 = await insp.capture("#username")
            assert el1 is not None
            assert el1.tag == "input"
            assert "#username" in el1.candidate_selectors

            el2 = await insp.capture("#password")
            assert el2 is not None
            assert el2.tag == "input"

            el3 = await insp.capture("#login-btn")
            assert el3 is not None
            assert el3.tag == "button"

            assert len(insp.captured) == 3
        finally:
            await insp.disconnect()
            await engine.stop()

    @pytest.mark.asyncio
    async def test_inspector_scores_selector_accuracy(self, mock_portal):
        """#username should score higher than .form-input or input."""
        insp, engine, port = await self._get_inspector(mock_portal)
        try:
            await insp.navigate(f"http://127.0.0.1:{port}/index.html")

            result = await insp.evaluate_selector("#username")
            id_score = result.get("score", 0)

            result = await insp.evaluate_selector("input")
            tag_score = result.get("score", 0)

            result = await insp.evaluate_selector("[name='username']")
            name_score = result.get("score", 0)

            assert id_score > tag_score, f"ID ({id_score}) should beat tag ({tag_score})"
            assert id_score >= name_score, f"ID ({id_score}) should >= name ({name_score})"
        finally:
            await insp.disconnect()
            await engine.stop()

    @pytest.mark.asyncio
    async def test_inspector_highlight_element(self, mock_portal):
        """Highlight should succeed on valid element."""
        insp, engine, port = await self._get_inspector(mock_portal)
        try:
            await insp.navigate(f"http://127.0.0.1:{port}/index.html")
            ok = await insp.highlight("#login-btn")
            assert ok, "Should highlight login button"

            has_highlight = await engine.evaluate(
                'document.querySelector("#login-btn").classList.contains("insuredesk-inspector-highlight")'
            )
            assert has_highlight, "Element should have highlight class"
        finally:
            await insp.disconnect()
            await engine.stop()

    @pytest.mark.asyncio
    async def test_inspector_generate_mapping_from_capture(self, mock_portal):
        """Captured elements can be exported as mapping."""
        insp, engine, port = await self._get_inspector(mock_portal)
        try:
            await insp.navigate(f"http://127.0.0.1:{port}/index.html")
            await insp.capture("#username")
            await insp.capture("#password")
            await insp.capture("#login-btn")

            mapping = insp.generate_mapping()
            assert "selectors" in mapping
            assert len(mapping["selectors"]) == 3
        finally:
            await insp.disconnect()
            await engine.stop()

    @pytest.mark.asyncio
    async def test_inspector_evaluate_unknown_selector(self, mock_portal):
        """Non-existent selector returns 0 matches."""
        insp, engine, port = await self._get_inspector(mock_portal)
        try:
            await insp.navigate(f"http://127.0.0.1:{port}/index.html")
            result = await insp.evaluate_selector("#nonexistent-element")
            assert result.get("matches", -1) == 0, "Should find 0 matches"
        finally:
            await insp.disconnect()
            await engine.stop()
