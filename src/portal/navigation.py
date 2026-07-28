"""InsureDesk — Navigation Engine.

Provides adapter.navigate("route.name") API that maps logical route names
to portal-specific navigation steps defined in YAML mapping files.

Routes are defined under a `navigation:` key in each portal's YAML:
    navigation:
        quote.new:
            steps:
                - action: click
                  selector: menu.quotes
                - action: click
                  selector: menu.new_quote
        policy.search:
            url: /policy/search
"""

from __future__ import annotations
import asyncio
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field


class NavigationError(Exception):
    """Raised when a navigation route cannot be completed."""


@dataclass
class NavigationStep:
    """A single step in a navigation route."""
    action: str = ""               # click | type | wait | navigate | select
    selector: str = ""             # CSS/XPath selector reference
    value: str = ""                # value to type (for type action)
    url: str = ""                  # URL to navigate to (for navigate action)
    timeout: int = 10              # max seconds to wait (for wait action)
    optional: bool = False         # if True, skip silently on failure


@dataclass
class NavigationRoute:
    """A complete navigation route with fallback alternatives."""
    name: str = ""
    steps: List[NavigationStep] = field(default_factory=list)
    url: str = ""                  # direct URL alternative (skip steps)
    fallback_steps: List[NavigationStep] = field(default_factory=list)
    description: str = ""


class NavigationEngine:
    """Maps logical route names → portal navigation steps.

    Usage:
        nav = NavigationEngine(adapter)
        await nav.navigate("quote.new")
        await nav.navigate("policy.search")
    """

    def __init__(self, adapter):
        self._adapter = adapter
        self._routes: Dict[str, NavigationRoute] = {}
        self._load_routes()

    # ── Public API ──

    async def navigate(self, route_name: str) -> bool:
        """Navigate to a logical route. Returns True on success."""
        route = self._routes.get(route_name)
        if not route:
            raise NavigationError(f"Unknown route: {route_name}")

        # Try direct URL first (fastest)
        if route.url:
            success = await self._try_url(route)
            if success:
                return True
            # Fall through to step-by-step navigation

        # Step-by-step navigation
        return await self._execute_steps(route.steps)

    def get_available_routes(self) -> List[str]:
        """Return list of all available route names."""
        return list(self._routes.keys())

    def has_route(self, route_name: str) -> bool:
        return route_name in self._routes

    # ── Internal ──

    def _load_routes(self):
        """Parse route definitions from the adapter's portal mapping YAML."""
        mapping = getattr(self._adapter, "mapping", None)
        if not mapping:
            return

        raw_nav = getattr(mapping, "navigation", None) or {}
        for name, config in raw_nav.items():
            route = NavigationRoute(name=name)

            if isinstance(config, str):
                # Simple URL mapping: quote.new: /quotes/new
                route.url = config
            elif isinstance(config, dict):
                route.url = config.get("url", "")
                route.description = config.get("description", "")
                route.steps = self._parse_steps(config.get("steps", []))
                route.fallback_steps = self._parse_steps(
                    config.get("fallback_steps", [])
                )

            self._routes[name] = route

    def _parse_steps(self, raw_steps: List[dict]) -> List[NavigationStep]:
        steps = []
        for raw in raw_steps:
            if isinstance(raw, str):
                # Shorthand: "click:selector.name"
                action, _, selector = raw.partition(":")
                steps.append(NavigationStep(action=action, selector=selector))
            elif isinstance(raw, dict):
                steps.append(NavigationStep(
                    action=raw.get("action", ""),
                    selector=raw.get("selector", ""),
                    value=raw.get("value", ""),
                    url=raw.get("url", ""),
                    timeout=raw.get("timeout", 10),
                    optional=raw.get("optional", False),
                ))
        return steps

    async def _try_url(self, route: NavigationRoute) -> bool:
        """Navigate directly via URL."""
        try:
            engine = getattr(self._adapter, "engine", None)
            if engine:
                full_url = route.url
                if not full_url.startswith("http") and self._adapter.start_url:
                    base = self._adapter.start_url.rstrip("/")
                    full_url = base + route.url
                await engine.goto(full_url)
                return True
        except Exception:
            return False
        return False

    async def _execute_steps(
        self, steps: List[NavigationStep]
    ) -> bool:
        """Execute a sequence of navigation steps."""
        for step in steps:
            try:
                await self._execute_step(step)
            except Exception as e:
                if step.optional:
                    continue
                raise NavigationError(
                    f"Step failed: {step.action}:{step.selector} — {e}"
                ) from e
        return True

    async def _execute_step(self, step: NavigationStep):
        """Execute a single navigation step."""
        adapter = self._adapter
        engine = getattr(adapter, "engine", None)
        if not engine:
            raise NavigationError("No browser engine available")

        if step.action == "navigate":
            url = step.url
            if not url.startswith("http") and adapter.start_url:
                base = adapter.start_url.rstrip("/")
                url = base + url
            await engine.goto(url)

        elif step.action == "click":
            selector = adapter.get_sel(step.selector)
            element = await engine.wait_for(selector)
            await element.click()

        elif step.action == "type":
            selector = adapter.get_sel(step.selector)
            element = await engine.wait_for(selector)
            await element.fill(step.value)

        elif step.action == "wait":
            if step.selector:
                selector = adapter.get_sel(step.selector)
                await engine.wait_for(selector, timeout=step.timeout * 1000)
            else:
                await asyncio.sleep(step.timeout)

        elif step.action == "select":
            # For dropdown/select elements
            selector = adapter.get_sel(step.selector)
            element = await engine.wait_for(selector)
            await element.select_option(step.value)

        else:
            raise NavigationError(f"Unknown action: {step.action}")
