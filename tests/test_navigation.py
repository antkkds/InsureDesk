"""Tests for NavigationEngine."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.portal.navigation import (
    NavigationEngine, NavigationRoute, NavigationStep, NavigationError,
)


# ── Fixtures ──


@pytest.fixture
def mock_adapter():
    """Create a mock PortalAdapter with navigation routes."""
    adapter = MagicMock()
    adapter.adapter_name = "great_eastern"
    adapter.start_url = "https://geglink.greateasterngeneral.com/geglink/userlogin.html"
    
    # Mock mapping with navigation routes
    adapter.mapping = MagicMock()
    adapter.mapping.navigation = {
        "quote.new": {
            "description": "Navigate to new quote",
            "steps": [
                {"action": "click", "selector": "quotation.nav_link"},
                {"action": "wait", "selector": "quotation.product_select.selector", "timeout": 5},
            ],
            "fallback_steps": [
                {"action": "navigate", "url": "/geglink/Quotation.html"},
            ]
        },
        "policy.search": {
            "url": "/geglink/PolicyInquiry.html",
            "steps": [
                {"action": "navigate", "url": "/geglink/PolicyInquiry.html"},
            ]
        },
        "dashboard": {
            "url": "/geglink/",
        }
    }
    
    # Mock engine
    mock_element = MagicMock()
    mock_element.click = AsyncMock()
    mock_element.fill = AsyncMock()
    mock_element.select_option = AsyncMock()
    
    adapter.engine = MagicMock()
    adapter.engine.goto = AsyncMock()
    adapter.engine.wait_for = AsyncMock(return_value=mock_element)
    
    # Mock get_sel
    def fake_get_sel(*path):
        return f"css={'.'.join(path)}"
    adapter.get_sel = fake_get_sel
    
    return adapter


@pytest.fixture
def nav(mock_adapter):
    return NavigationEngine(mock_adapter)


# ── Route Loading Tests ──


class TestRouteLoading:
    def test_loads_routes_from_mapping(self, nav):
        routes = nav.get_available_routes()
        assert "quote.new" in routes
        assert "policy.search" in routes
        assert "dashboard" in routes

    def test_has_route(self, nav):
        assert nav.has_route("quote.new") is True
        assert nav.has_route("nonexistent") is False

    def test_unknown_route_raises_error(self, nav):
        import asyncio
        with pytest.raises(NavigationError, match="Unknown route"):
            asyncio.run(nav.navigate("nonexistent"))

    def test_empty_mapping_no_routes(self):
        """Adapter with no navigation config should have empty routes."""
        adapter = MagicMock()
        adapter.mapping = MagicMock()
        adapter.mapping.navigation = {}
        engine = NavigationEngine(adapter)
        assert engine.get_available_routes() == []

    def test_no_mapping_no_routes(self):
        """Adapter with no mapping should have empty routes."""
        adapter = MagicMock()
        adapter.mapping = None
        engine = NavigationEngine(adapter)
        assert engine.get_available_routes() == []


# ── URL-based Navigation Tests ──


@pytest.mark.asyncio
class TestUrlNavigation:
    async def test_url_route_navigates_directly(self, nav, mock_adapter):
        """Routes with url (and no steps) should call engine.goto."""
        result = await nav.navigate("dashboard")
        assert result is True
        mock_adapter.engine.goto.assert_called_once()

    async def test_url_route_uses_absolute_url(self, nav, mock_adapter):
        """URL should be resolved relative to base_url."""
        await nav.navigate("dashboard")
        args, _ = mock_adapter.engine.goto.call_args
        # Should prepend base URL
        assert "geglink" in args[0]

    async def test_url_route_full_url_no_prepend(self, nav, mock_adapter):
        """Full URL should not be prepended."""
        # Add a route with full URL
        nav._routes["external"] = NavigationRoute(
            name="external",
            url="https://other.com/page"
        )
        await nav.navigate("external")
        args, _ = mock_adapter.engine.goto.call_args
        assert args[0] == "https://other.com/page"


# ── Step-based Navigation Tests ──


@pytest.mark.asyncio
class TestStepNavigation:
    async def test_step_navigation_executes_all_steps(self, nav, mock_adapter):
        """Each step should trigger the right engine method."""
        result = await nav.navigate("quote.new")
        assert result is True
        # Should have called wait_for twice (click needs wait_for + element, wait needs wait_for)
        assert mock_adapter.engine.wait_for.call_count >= 2

    async def test_optional_step_does_not_fail(self, nav, mock_adapter):
        """Optional steps should be skipped silently on failure."""
        nav._routes["test"] = NavigationRoute(
            name="test",
            steps=[
                NavigationStep(action="click", selector="nonexistent", optional=True),
                NavigationStep(action="click", selector="quotation.nav_link"),
            ]
        )
        # First step should fail silently, second should succeed
        mock_element = MagicMock()
        mock_element.click = AsyncMock()
        mock_adapter.engine.wait_for.side_effect = [
            Exception("Not found"),  # First click fails
            mock_element,             # Second click succeeds
        ]
        result = await nav.navigate("test")
        assert result is True

    async def test_non_optional_step_failure_raises(self, nav, mock_adapter):
        """Non-optional steps should raise NavigationError."""
        mock_adapter.engine.wait_for.side_effect = Exception("Element not found")
        with pytest.raises(NavigationError, match="Step failed"):
            await nav.navigate("quote.new")


# ── Fallback Tests ──


@pytest.mark.asyncio
class TestFallbackNavigation:
    async def test_fallback_used_when_url_fails(self, nav, mock_adapter):
        """If URL navigation fails, steps should be executed."""
        # Create a route where URL is wrong but fallback steps exist
        nav._routes["test_fallback"] = NavigationRoute(
            name="test_fallback",
            url="/bad_url",
            steps=[
                NavigationStep(action="click", selector="quotation.nav_link"),
            ]
        )
        result = await nav.navigate("test_fallback")
        assert result is True

    async def test_no_engine_raises_error(self, nav, mock_adapter):
        """Navigation without engine should raise NavigationError."""
        mock_adapter.engine = None
        with pytest.raises(NavigationError, match="No browser engine"):
            await nav.navigate("quote.new")


# ── Edge Cases ──


class TestNavigationStep:
    def test_shorthand_step_parsing(self):
        """Shorthand format 'action:selector.path' should parse correctly."""
        nav = NavigationEngine(MagicMock())
        steps = nav._parse_steps(["click:menu.quotes", "wait:form.loaded"])
        assert len(steps) == 2
        assert steps[0].action == "click"
        assert steps[0].selector == "menu.quotes"
        assert steps[1].action == "wait"
        assert steps[1].selector == "form.loaded"

    def test_unknown_action_in_step(self):
        """Unknown action should raise NavigationError."""
        nav = NavigationEngine(MagicMock())
        step = NavigationStep(action="fly", selector="somewhere")
        import asyncio
        with pytest.raises(NavigationError, match="Unknown action"):
            asyncio.run(nav._execute_step(step))
