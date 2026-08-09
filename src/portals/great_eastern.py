"""InsureDesk — Great Eastern General Insurance (GEGLink) Portal Adapter.

Concrete implementation of PortalAdapter for GEGLink.
Handles: login (POST-based), PDPA acceptance, navigation, page detection.

Usage:
    adapter = GEGLinkAdapter()
    adapter.engine = browser_engine  # BrowserEngine instance
    await adapter.login(credentials)
    await adapter.goto_get_quote()
"""

from __future__ import annotations

from typing import Optional
import asyncio

from src.portal.mapping import load_portal_mapping, PortalMapping
from src.portals.base import PortalAdapter, PortalCredentials, SessionMode
from src.browser.driver import BrowserEngine


# ──────────────────────────────────────────────────────────────
# Page identifiers — used by identify_current_page()
# ──────────────────────────────────────────────────────────────

PAGE_SIGNATURES = {
    "home":       {"url_contains": "/home"},
    "get_quote":  {"url_contains": "/get-quote"},
    "make_claim": {"url_contains": "/make-a-claim"},
    "my_profile": {"url_contains": "/my-profile"},
    "my_account": {"url_contains": "/my-account"},
    "my_client":  {"url_contains": "/my-client"},
    "forms":      {"url_contains": "/forms"},
    "login":      {"url_contains": "/userlogin.html"},
    "pdpa":       {"url_contains": "/pdpa-terms"},
    "products":   {"url_contains": "/product"},
    "training":   {"url_contains": "/training"},
    "guidelines": {"url_contains": "/guidelines"},
}

# Base URLs
BASE_URL = "https://geglink.greateasterngeneral.com"
LOGIN_URL = f"{BASE_URL}/geglink/userlogin.html"
LOGIN_ACTION = f"{BASE_URL}/geglink/submitlogin.html"
DASHBOARD_URL = f"{BASE_URL}/oacportal/group/geglink/home"
PDPA_URL_PREFIX = f"{BASE_URL}/oacportal/group/geglink/pdpa-terms"


class GEGLinkAdapter(PortalAdapter):
    """Portal adapter for Great Eastern General Insurance GEGLink.

    Navigation map:
        login → PDPA (first time) → Dashboard
        Dashboard → [Get Quote | Make A Claim | My Profile | My Account | My Client | Forms]
        Get Quote → iframe → agent_home.html → external quote system (redirectJSP)
    """

    def __init__(self, mapping: Optional[PortalMapping] = None,
                 engine: Optional[BrowserEngine] = None,
                 mode: SessionMode = SessionMode.READ_WRITE,
                 login_url: Optional[str] = None):
        if mapping is None:
            mapping = load_portal_mapping("great_eastern")
        super().__init__(mapping, engine, mode, login_url)

    @property
    def adapter_name(self) -> str:
        return "great_eastern"

    # ── Login ────────────────────────────────────────────────

    async def login(self, credentials: PortalCredentials) -> bool:
        """Full GEGLink login flow.

        1. Navigate to login page
        2. Fill username/password (fields are outside the <form> tag in DOM)
        3. Click the image submit button
        4. Handle PDPA terms if presented
        5. Verify we reached the dashboard
        """
        if not self._engine:
            raise RuntimeError("BrowserEngine not set. Set adapter.engine first.")

        engine = self._engine

        # 1. Navigate to login page
        await engine.navigate(LOGIN_URL)
        await asyncio.sleep(2)

        # 2. Fill credentials
        username_sel = self.get_sel("login", "username")
        password_sel = self.get_sel("login", "password")

        await engine.fill(username_sel, credentials.username)
        await engine.fill(password_sel, credentials.password)

        # 3. Click login button (image type input)
        submit_sel = self.get_sel("login", "submit")
        await engine.click(submit_sel)
        await asyncio.sleep(5)

        # 4. Check for PDPA terms page
        current_url = await engine.get_url()
        if PDPA_URL_PREFIX in current_url:
            await self._accept_pdpa()
            await asyncio.sleep(3)

        # 5. Verify login
        return await self.is_logged_in()

    async def login_via_post(self, credentials: PortalCredentials) -> bool:
        """Alternative login via direct HTTP POST (more reliable).

        Some GEGLink pages have input fields outside the <form> tag,
        making regular form submission unreliable. This method uses
        httpx to POST credentials directly, then transfers cookies.
        """
        import httpx

        if not self._engine:
            raise RuntimeError("BrowserEngine not set.")

        engine = self._engine

        # Navigate to login page first (to get initial cookies)
        await engine.navigate(LOGIN_URL)
        await asyncio.sleep(2)

        # Get session cookies from browser
        cookies = await self._get_cookies()

        # POST login via httpx
        async with httpx.AsyncClient(cookies=cookies, follow_redirects=True) as client:
            resp = await client.post(
                LOGIN_ACTION,
                data={
                    "oac_username": credentials.username,
                    "oac_intpwd": credentials.password,
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": BASE_URL,
                    "Referer": LOGIN_URL,
                }
            )

            final_url = str(resp.url)
            # Transfer cookies back to browser
            for cookie in resp.cookies.jar:
                if hasattr(cookie, 'name') and hasattr(cookie, 'value'):
                    try:
                        await self._set_cookie(
                            cookie.name, cookie.value,
                            domain=getattr(cookie, 'domain', '.greateasterngeneral.com'),
                            path=getattr(cookie, 'path', '/'),
                        )
                    except Exception:
                        pass

        # Navigate to PDPA or Dashboard
        if PDPA_URL_PREFIX in final_url:
            await engine.navigate(final_url)
            await asyncio.sleep(3)
            await self._accept_pdpa()
            await asyncio.sleep(3)

        # Go to dashboard
        await engine.navigate(DASHBOARD_URL)
        await asyncio.sleep(3)

        return await self.is_logged_in()

    async def _accept_pdpa(self):
        """Accept PDPA terms page."""
        engine = self._engine
        if not engine:
            return

        try:
            await engine.click("input[value='I Agree']")
        except Exception:
            try:
                await engine.click("button:has-text('Agree')")
            except Exception:
                # Fallback: JS click
                await engine.evaluate("""() => {
                    const btns = document.querySelectorAll('input, button, a');
                    for (const btn of btns) {
                        const txt = (btn.value || btn.textContent || '').toLowerCase();
                        if (txt.includes('agree') || txt.includes('accept')) {
                            btn.click(); return;
                        }
                    }
                }""")

    async def logout(self):
        """Logout from GEGLink."""
        engine = self._engine
        if not engine:
            return
        logout_sel = self.get_sel("dashboard", "logout_link")
        if logout_sel:
            await engine.click(logout_sel)
            await asyncio.sleep(2)

    # ── Session ──────────────────────────────────────────────

    async def is_logged_in(self) -> bool:
        """Check if currently on the GEGLink dashboard."""
        engine = self._engine
        if not engine:
            return False
        url = await engine.get_url()
        return "oacportal" in url and "login" not in url.lower()

    async def ensure_session(self) -> bool:
        """Ensure we have an active session. Return True if valid."""
        if await self.is_logged_in():
            return True
        # Try to refresh session or re-login would be handled by caller
        return False

    # ── Navigation ───────────────────────────────────────────

    async def goto_dashboard(self):
        engine = self._engine
        if not engine:
            return
        await engine.navigate(DASHBOARD_URL)
        await asyncio.sleep(3)

    async def goto_get_quote(self):
        engine = self._engine
        if not engine:
            return
        await engine.navigate(f"{BASE_URL}/oacportal/group/geglink/get-quote")
        await asyncio.sleep(3)

    async def goto_make_claim(self):
        engine = self._engine
        if not engine:
            return
        await engine.navigate(f"{BASE_URL}/oacportal/group/geglink/make-a-claim")
        await asyncio.sleep(3)

    async def goto_my_profile(self):
        engine = self._engine
        if not engine:
            return
        await engine.navigate(f"{BASE_URL}/oacportal/group/geglink/my-profile")
        await asyncio.sleep(3)

    async def goto_my_account(self):
        engine = self._engine
        if not engine:
            return
        await engine.navigate(f"{BASE_URL}/oacportal/group/geglink/my-account")
        await asyncio.sleep(3)

    async def goto_my_client(self):
        engine = self._engine
        if not engine:
            return
        await engine.navigate(f"{BASE_URL}/oacportal/group/geglink/my-client")
        await asyncio.sleep(3)

    async def goto_forms(self):
        engine = self._engine
        if not engine:
            return
        await engine.navigate(f"{BASE_URL}/oacportal/group/geglink/forms")
        await asyncio.sleep(3)

    # ── Page Detection ──────────────────────────────────────

    async def identify_current_page(self) -> str:
        """Detect which page we're currently on.

        Returns one of: 'home', 'get_quote', 'make_claim', 'my_profile',
        'my_account', 'my_client', 'forms', 'login', 'pdpa', 'products',
        'training', 'guidelines', or 'unknown'.
        """
        engine = self._engine
        if not engine:
            return "unknown"

        url = await engine.get_url()
        for page_name, signature in PAGE_SIGNATURES.items():
            if signature["url_contains"] in url:
                return page_name
        return "unknown"

    # ── iframe Helpers ──────────────────────────────────────

    async def get_quote_iframe_actions(self) -> list[dict]:
        """List available eQuotation actions from the Get Quote iframe.

        Returns list like:
            [{"name": "IFE", "label": "Fire/Engineering", "channel_type": "IFE"},
             {"name": "EQ", "label": "E-Quotation", "channel_type": "EQ"}]
        """
        engine = self._engine
        if not engine:
            return []

        # The eQuotation buttons are in an iframe (agent_home.html)
        iframes = await engine.get_frames()
        results = []
        for f in iframes:
            try:
                forms = await f.query_selector_all("form")
                for form in forms:
                    channel = await form.evaluate(
                        "el => el.querySelector('input[name=\"channelType\"]')?.value"
                    )
                    if channel:
                        results.append({
                            "name": "eQuotation",
                            "label": "IFE" if channel == "IFE" else "EQ",
                            "channel_type": channel,
                            "form_action": await form.get_attribute("action") or "",
                        })
            except Exception:
                pass
        return results

    # ── Quote Engine Integration ────────────────────────────

    def launch_ife_quote(self):
        """Create an IFE (Fire & Engineering) quote adapter.

        Returns:
            IFEQuoteAdapter instance (engine shared).
        """
        from src.quote.ge_adapters import IFEQuoteAdapter
        adapter = IFEQuoteAdapter(self._engine)
        return adapter

    def launch_eq_quote(self):
        """Create an EQ (E-Quotation) quote adapter.

        Returns:
            EQQuoteAdapter instance (engine shared).
        """
        from src.quote.ge_adapters import EQQuoteAdapter
        adapter = EQQuoteAdapter(self._engine)
        return adapter

    # ── Internal helpers ────────────────────────────────────

    async def _get_cookies(self) -> dict:
        """Get cookies from the browser engine."""
        engine = self._engine
        if not engine:
            return {}
        try:
            cookies = await engine.get_cookies()
            return {c["name"]: c["value"] for c in cookies
                    if "greateastern" in c.get("domain", "")}
        except Exception:
            return {}

    async def _set_cookie(self, name: str, value: str,
                          domain: str = ".greateasterngeneral.com",
                          path: str = "/"):
        """Set a cookie in the browser engine."""
        engine = self._engine
        if not engine:
            return
        try:
            await engine.set_cookie({"name": name, "value": value,
                                      "domain": domain, "path": path})
        except Exception:
            pass


# ── Backward-compat alias ──────────────────────────────────────
# Remote tests/callers reference GreatEasternAdapter; the concrete
# implementation class is GEGLinkAdapter.
GreatEasternAdapter = GEGLinkAdapter
