"""Tests: Portal Profile Loading + ProfileData.

Tests for the new profiles/ directory and ProfileData class.
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestProfileData:
    """ProfileData — profile/loader from profiles/*.yaml."""

    def test_load_geglink_profile(self):
        from src.portal.mapping import load_portal_profile, ProfileData
        profile = load_portal_profile("geglink")
        assert profile is not None
        assert profile.portal == "great_eastern"
        assert "login" in profile.pages
        assert "dashboard" in profile.pages

    def test_geglink_login_selectors(self):
        from src.portal.mapping import load_portal_profile
        profile = load_portal_profile("geglink")
        assert profile.get_selector("login", "username") == "input[name='oac_username']"
        assert profile.get_selector("login", "password") == "input[name='oac_intpwd']"
        assert profile.get_selector("login", "submit") == "input[src*='loginbut.jpg']"

    def test_geglink_dashboard_selectors(self):
        from src.portal.mapping import load_portal_profile
        profile = load_portal_profile("geglink")
        assert profile.get_selector("dashboard", "logout_link") is not None

    def test_get_element_metadata(self):
        from src.portal.mapping import load_portal_profile
        profile = load_portal_profile("geglink")
        el = profile.get_element("login", "username")
        assert el is not None
        assert el["tag"] == "input"
        assert el["input_type"] == "text"

    def test_get_selector_not_found(self):
        from src.portal.mapping import load_portal_profile
        profile = load_portal_profile("geglink")
        assert profile.get_selector("nonexistent", "field") is None
        assert profile.get_selector("login", "nonexistent") is None

    def test_list_pages(self):
        from src.portal.mapping import load_portal_profile
        profile = load_portal_profile("geglink")
        pages = profile.list_pages()
        assert "login" in pages
        assert "dashboard" in pages
        assert len(pages) >= 5  # login, pdpa, dashboard, get_quote, etc.

    def test_list_fields(self):
        from src.portal.mapping import load_portal_profile
        profile = load_portal_profile("geglink")
        fields = profile.list_fields("login")
        assert "username" in fields
        assert "password" in fields
        assert "submit" in fields

    def test_load_nonexistent_profile(self):
        from src.portal.mapping import load_portal_profile
        profile = load_portal_profile("nonexistent")
        assert profile is None

    def test_load_ife_quote_profile(self):
        from src.portal.mapping import load_quote_profile
        profile = load_quote_profile("great_eastern", "IFE")
        assert profile is not None
        assert profile.quote_channel == "IFE"
        assert "quote_form" in profile.pages

    def test_load_eq_quote_profile(self):
        from src.portal.mapping import load_quote_profile
        profile = load_quote_profile("great_eastern", "EQ")
        assert profile is not None
        assert profile.quote_channel == "EQ"

    def test_list_available_profiles(self):
        from src.portal.mapping import list_available_profiles
        profiles = list_available_profiles()
        names = [p["profile"] for p in profiles]
        assert "geglink" in names
        assert "ife_quote" in names
        assert "eq_quote" in names

    def test_list_available_portals_has_profile_flag(self):
        from src.portal.mapping import list_available_portals
        portals = list_available_portals()
        ge = next((p for p in portals if p["adapter"] == "great_eastern"), None)
        assert ge is not None
        assert ge["has_profile"] is True
