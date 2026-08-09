"""Tests: GEGLink Portal Adapter.

Scope: ~10 tests covering:
- Adapter creation & YAML mapping loading
- Page identification
- login_via_post (requires CDP or Playwright)
- Navigation methods
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ──────────────────────────────────────────────────────────────
# 1. Unit Tests — Adapter creation & mapping
# ──────────────────────────────────────────────────────────────

class TestGEGLinkAdapterUnit:
    """No browser needed — tests adapter structure."""

    def test_adapter_imports(self):
        """Adapter module imports cleanly."""
        from src.portals.great_eastern import GEGLinkAdapter
        assert GEGLinkAdapter is not None

    def test_adapter_name(self):
        """Adapter name is 'great_eastern'."""
        from src.portals.great_eastern import GEGLinkAdapter
        adapter = GEGLinkAdapter()
        assert adapter.adapter_name == "great_eastern"

    def test_adapter_mapping_loaded(self):
        """YAML mapping loads correctly."""
        from src.portals.great_eastern import GEGLinkAdapter
        adapter = GEGLinkAdapter()
        assert adapter.mapping is not None
        assert adapter.mapping.name == "Great Eastern"
        assert adapter.mapping.short_name == "GE"

    def test_adapter_login_selectors(self):
        """Login selectors exist in mapping."""
        from src.portals.great_eastern import GEGLinkAdapter
        adapter = GEGLinkAdapter()
        username_sel = adapter.get_sel("login", "username")
        password_sel = adapter.get_sel("login", "password")
        submit_sel = adapter.get_sel("login", "submit")
        assert username_sel is not None
        assert password_sel is not None
        assert submit_sel is not None

    def test_adapter_nav_selectors(self):
        """Navigation selectors exist."""
        from src.portals.great_eastern import GEGLinkAdapter
        adapter = GEGLinkAdapter()
        logout_sel = adapter.get_sel("dashboard", "logout_link")
        assert logout_sel is not None

    def test_adapter_page_signatures(self):
        """Page identification signatures are complete."""
        from src.portals.great_eastern import PAGE_SIGNATURES
        expected_pages = {
            "home", "get_quote", "make_claim", "my_profile",
            "my_account", "my_client", "forms", "login",
            "pdpa", "products", "training", "guidelines",
        }
        assert set(PAGE_SIGNATURES.keys()) == expected_pages

    def test_adapter_verify_urls(self):
        """All URLs are correctly formed."""
        from src.portals.great_eastern import (
            BASE_URL, LOGIN_URL, LOGIN_ACTION, DASHBOARD_URL
        )
        assert BASE_URL == "https://geglink.greateasterngeneral.com"
        assert "userlogin.html" in LOGIN_URL
        assert "submitlogin.html" in LOGIN_ACTION
        assert "home" in DASHBOARD_URL


# ──────────────────────────────────────────────────────────────
# 2. Unit Tests — Mock-based page identification
# ──────────────────────────────────────────────────────────────

class MockEngine:
    """Minimal BrowserEngine mock for page detection tests."""

    def __init__(self, url: str = ""):
        self._url = url

    async def get_url(self):
        return self._url

    async def navigate(self, url):
        self._url = url

    async def fill(self, sel, value):
        pass

    async def click(self, sel):
        pass

    async def evaluate(self, js, *args):
        return None

    async def get_cookies(self):
        return []

    async def set_cookie(self, cookie):
        pass

    async def get_frames(self):
        return []

    async def query_selector_all(self, sel):
        return []


@pytest.mark.asyncio
async def test_identify_home():
    from src.portals.great_eastern import GEGLinkAdapter
    adapter = GEGLinkAdapter(engine=MockEngine(
        "https://geglink.greateasterngeneral.com/oacportal/group/geglink/home"
    ))
    page = await adapter.identify_current_page()
    assert page == "home"


@pytest.mark.asyncio
async def test_identify_login():
    from src.portals.great_eastern import GEGLinkAdapter
    adapter = GEGLinkAdapter(engine=MockEngine(
        "https://geglink.greateasterngeneral.com/geglink/userlogin.html"
    ))
    page = await adapter.identify_current_page()
    assert page == "login"


@pytest.mark.asyncio
async def test_identify_get_quote():
    from src.portals.great_eastern import GEGLinkAdapter
    adapter = GEGLinkAdapter(engine=MockEngine(
        "https://geglink.greateasterngeneral.com/oacportal/group/geglink/get-quote"
    ))
    page = await adapter.identify_current_page()
    assert page == "get_quote"


@pytest.mark.asyncio
async def test_identify_make_claim():
    from src.portals.great_eastern import GEGLinkAdapter
    adapter = GEGLinkAdapter(engine=MockEngine(
        "https://geglink.greateasterngeneral.com/oacportal/group/geglink/make-a-claim"
    ))
    page = await adapter.identify_current_page()
    assert page == "make_claim"


@pytest.mark.asyncio
async def test_identify_pdpa():
    from src.portals.great_eastern import GEGLinkAdapter
    adapter = GEGLinkAdapter(engine=MockEngine(
        "https://geglink.greateasterngeneral.com/oacportal/group/geglink/pdpa-terms?oac_user=xxx"
    ))
    page = await adapter.identify_current_page()
    assert page == "pdpa"


@pytest.mark.asyncio
async def test_identify_unknown():
    from src.portals.great_eastern import GEGLinkAdapter
    adapter = GEGLinkAdapter(engine=MockEngine(
        "https://some-other-site.com"
    ))
    page = await adapter.identify_current_page()
    assert page == "unknown"


@pytest.mark.asyncio
async def test_is_logged_in_true():
    from src.portals.great_eastern import GEGLinkAdapter
    adapter = GEGLinkAdapter(engine=MockEngine(
        "https://geglink.greateasterngeneral.com/oacportal/group/geglink/home"
    ))
    assert await adapter.is_logged_in() is True


@pytest.mark.asyncio
async def test_is_logged_in_false():
    from src.portals.great_eastern import GEGLinkAdapter
    adapter = GEGLinkAdapter(engine=MockEngine(
        "https://geglink.greateasterngeneral.com/geglink/userlogin.html"
    ))
    assert await adapter.is_logged_in() is False
