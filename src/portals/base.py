"""InsureDesk — Portal Adapter System.

Base adapter + concrete implementations using:
- YAML-based portal mappings (not hardcoded selectors)
- BrowserEngine abstraction (Playwright dev / QtWebEngine production)
- SessionManager (persistent sessions with cookie serialization)
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from src.portal.mapping import load_portal_mapping, get_selector, list_available_portals, PortalMapping
from src.portal.form_engine import FormEngine
from src.portal.session import SessionManager
from src.portal.navigation import NavigationEngine
from src.browser.driver import BrowserEngine
from src.fill.engine import FillEngine
from src.fill.schema import FillSchema, schemas_from_yaml
from src.fill.transformer import TransformerRegistry


@dataclass
class PortalCredentials:
    username: str = ""
    password: str = ""
    otp_secret: str = ""


class PortalAdapter(ABC):
    """Base class for all insurance portal adapters.

    Uses:
    - BrowserEngine (abstract — swap between Playwright and QtWebEngine)
    - YAML mapping for selectors (not hardcoded)
    - FormEngine for all browser interactions
    - SessionManager for persistent login
    """

    def __init__(self, mapping: Optional[PortalMapping] = None,
                 engine: Optional[BrowserEngine] = None):
        # Auto-load mapping from adapter_name if not provided
        if mapping is None:
            mapping = load_portal_mapping(self.adapter_name)
        self.mapping = mapping
        self._engine = engine
        self.form = FormEngine(engine)
        self.session = SessionManager()
        self.nav = NavigationEngine(self)
        self._fill: Optional[FillEngine] = None
        self._fill_schemas: dict[str, FillSchema] = {}
        self._transformers: Optional[TransformerRegistry] = None
        self._logged_in = False

    @property
    def engine(self) -> Optional[BrowserEngine]:
        return self._engine

    @engine.setter
    def engine(self, new_engine: Optional[BrowserEngine]):
        self._engine = new_engine
        self.form.engine = new_engine

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        ...

    @property
    def portal_name(self) -> str:
        """Human-readable portal name from mapping."""
        return self.mapping.name if self.mapping else self.adapter_name

    @property
    def start_url(self) -> str:
        """URL to navigate to when starting this portal."""
        if self.mapping and self.mapping.login_url:
            return self.mapping.login_url
        if self.mapping and self.mapping.base_url:
            return self.mapping.base_url
        return ""

    def get_sel(self, *path: str) -> str:
        """Get a selector from the mapping by path."""
        sel = get_selector(self.mapping, *path)
        return sel or ""

    async def navigate(self, route_name: str) -> bool:
        """Navigate to a logical route (delegates to NavigationEngine)."""
        return await self.nav.navigate(route_name)

    # ── Fill Engine (Phase 4.2) ──

    @property
    def fill(self) -> FillEngine:
        """Lazy-initialized FillEngine for this portal."""
        if self._fill is None:
            self._init_fill()
        return self._fill

    @property
    def fill_schemas(self) -> dict[str, FillSchema]:
        """Lazy-loaded fill schemas from YAML mapping."""
        if not self._fill_schemas and self.mapping and self.mapping.schemas:
            # self.mapping.schemas is raw YAML dict, need to parse
            for section_name, section_data in self.mapping.schemas.items():
                if isinstance(section_data, dict):
                    from src.fill.schema import fill_schema_from_dict
                    self._fill_schemas[section_name] = fill_schema_from_dict(
                        section_name, section_data
                    )
        return self._fill_schemas

    def _init_fill(self):
        """Initialize the FillEngine and its dependencies."""
        # Create transformer registry from YAML
        transformers = TransformerRegistry()
        if self.mapping and self.mapping.transformers:
            transformers.register_from_yaml(self.mapping.transformers)

        self._transformers = transformers
        self._fill = FillEngine(transformer_registry=transformers)

    # ── Connection ──

    async def connect(self):
        """Start the browser engine."""
        if self._engine:
            await self._engine.start()

    async def disconnect(self):
        """Save session and stop engine."""
        if self._logged_in and self._engine:
            try:
                cookies = await self._engine.get_cookies()
                self.session.save_cookies(self.adapter_name, [
                    {"name": c.name, "value": c.value, "domain": c.domain,
                     "path": c.path, "secure": c.secure, "httpOnly": c.http_only,
                     "sameSite": c.same_site, "expires": c.expires}
                    for c in cookies
                ])
            except Exception:
                pass
        self._logged_in = False

    # ── Login ──

    async def login(self, credentials: PortalCredentials) -> bool:
        """Log into the portal."""
        await self.connect()

        # Try restoring session first
        if await self._restore_session():
            self._logged_in = True
            return True

        # Navigate to login page
        url = self.start_url
        if not url:
            return False

        ok = await self._engine.navigate(url) if self._engine else False
        if not ok:
            return False

        # Fill in credentials
        username_sel = self.get_sel("login", "username")
        password_sel = self.get_sel("login", "password")
        submit_sel = self.get_sel("login", "submit")

        if not username_sel or not password_sel:
            # Manual login mode — let user do it
            return False

        await self.form.fill_text(username_sel, credentials.username)
        await self.form.fill_text(password_sel, credentials.password)

        if submit_sel:
            await self.form.click(submit_sel)
            # Wait for navigation after login
            if self._engine:
                await self._engine.wait_for_navigation(timeout=15000)

        # Check if login was successful
        if await self._check_login_success():
            self._logged_in = True
            return True

        return False

    async def logout(self):
        """Log out of the portal."""
        logout_sel = self.get_sel("dashboard", "logout_link")
        if logout_sel:
            await self.form.click(logout_sel)
        self._logged_in = False

    # ── Operations ──

    async def search_policy(self, policy_no: str) -> Optional[Dict[str, Any]]:
        """Search for a policy by policy number."""
        if not await self._ensure_logged_in():
            return None

        # Click policy nav link
        nav_sel = self.get_sel("policy_search", "nav_link")
        search_sel = self.get_sel("policy_search", "search_input")
        button_sel = self.get_sel("policy_search", "search_button")

        if nav_sel:
            await self.form.click(nav_sel)

        if search_sel:
            await self.form.fill_text(search_sel, policy_no)

        if button_sel:
            await self.form.click(button_sel)
            await self._engine.wait_for_navigation(timeout=10000)

        return {"policy_no": policy_no, "status": "searched"}

    async def get_policy_details(self) -> Optional[Dict[str, Any]]:
        """Extract policy details from the current page."""
        if not await self._ensure_logged_in():
            return None

        return {
            "policy_number": await self.form.get_text(self.get_sel("policy_details", "policy_number")),
            "status": await self.form.get_text(self.get_sel("policy_details", "status")),
            "premium": await self.form.get_text(self.get_sel("policy_details", "premium")),
            "start_date": await self.form.get_text(self.get_sel("policy_details", "start_date")),
            "end_date": await self.form.get_text(self.get_sel("policy_details", "end_date")),
        }

    async def submit_claim(self, claim_data: Dict[str, str]) -> bool:
        """Submit a claim."""
        if not await self._ensure_logged_in():
            return False

        nav_sel = self.get_sel("claims", "nav_link")
        if nav_sel:
            await self.form.click(nav_sel)

        for field, selector_key in [
            ("policy_no", "claims.policy_no_field"),
            ("incident_date", "claims.incident_date"),
            ("claim_type", "claims.claim_type"),
            ("description", "claims.description"),
        ]:
            sel = self.get_sel(*selector_key.split("."))
            if sel and claim_data.get(field):
                await self.form.fill_text(sel, claim_data[field])

        submit_sel = self.get_sel("claims", "submit_button")
        if submit_sel:
            await self.form.click(submit_sel)
            return True
        return False

    async def renew_policy(self) -> bool:
        """Trigger policy renewal."""
        if not await self._ensure_logged_in():
            return False

        nav_sel = self.get_sel("renewal", "nav_link")
        if nav_sel:
            await self.form.click(nav_sel)

        renew_sel = self.get_sel("renewal", "renew_button")
        if renew_sel:
            await self.form.click(renew_sel)
            return True
        return False

    async def upload_document(self, file_path: str,
                               doc_type: str = "") -> bool:
        """Upload a document."""
        if not await self._ensure_logged_in():
            return False

        nav_sel = self.get_sel("documents", "nav_link")
        if nav_sel:
            await self.form.click(nav_sel)

        upload_sel = self.get_sel("documents", "upload_button")
        if upload_sel:
            await self.form.click(upload_sel)

        file_sel = self.get_sel("documents", "file_input")
        if file_sel:
            await self.form.upload_file(file_sel, file_path)

        if doc_type:
            type_sel = self.get_sel("documents", "document_type")
            if type_sel:
                await self.form.select_option(type_sel, doc_type)

        submit_sel = self.get_sel("documents", "submit_upload")
        if submit_sel:
            await self.form.click(submit_sel)
            return True
        return False

    async def check_health(self) -> Dict[str, Any]:
        """Check if portal is accessible and logged in."""
        return {
            "adapter": self.adapter_name,
            "portal": self.portal_name,
            "logged_in": self._logged_in,
            "engine": self._engine.name if self._engine else "none",
            "has_mapping": self.mapping is not None,
            "start_url": self.start_url,
        }

    # ── Internal ──

    async def _ensure_logged_in(self) -> bool:
        """Ensure user is logged in, attempt restore if not."""
        if self._logged_in:
            return True
        if await self._restore_session():
            self._logged_in = True
            return True
        return False

    async def _restore_session(self) -> bool:
        """Try to restore a saved session (cookies + navigate to dashboard)."""
        saved = self.session.load_cookies(self.adapter_name)
        if not saved:
            return False

        if not self._engine:
            return False

        if not await self._engine.navigate(self.start_url):
            return False

        # Check if login page shows (meaning session expired)
        username_sel = self.get_sel("login", "username")
        if username_sel:
            still_login = await self._engine.is_visible(username_sel)
            if still_login:
                return False  # Session expired

        return True

    async def _check_login_success(self) -> bool:
        """Check if we're logged in (dashboard elements visible)."""
        welcome_sel = self.get_sel("dashboard", "welcome_message")
        profile_sel = self.get_sel("dashboard", "user_profile")
        if welcome_sel:
            return await self._engine.is_visible(welcome_sel) if self._engine else False
        if profile_sel:
            return await self._engine.is_visible(profile_sel) if self._engine else False
        # No dashboard selectors defined — assume success
        return True


# ── Concrete Adapters ──

class GreatEasternAdapter(PortalAdapter):
    """Great Eastern Malaysia (i-Connect) Portal Adapter."""

    @property
    def adapter_name(self) -> str:
        return "great_eastern"


class AllianzAdapter(PortalAdapter):
    """Allianz Malaysia Life e-Service Portal Adapter."""

    @property
    def adapter_name(self) -> str:
        return "allianz"


class AIAAdapter(PortalAdapter):
    """AIA Malaysia e-Care Portal Adapter."""

    @property
    def adapter_name(self) -> str:
        return "aia"


# ── Registry ──

_ADAPTER_MAP: Dict[str, type] = {
    "great_eastern": GreatEasternAdapter,
    "allianz": AllianzAdapter,
    "aia": AIAAdapter,
}


def get_adapter(portal_id: str,
                mapping: Optional[PortalMapping] = None,
                engine: Optional[BrowserEngine] = None) -> Optional[PortalAdapter]:
    """Get a portal adapter by ID, auto-loading mapping."""
    adapter_cls = _ADAPTER_MAP.get(portal_id)
    if not adapter_cls:
        return None

    if mapping is None:
        mapping = load_portal_mapping(portal_id)

    return adapter_cls(mapping=mapping, engine=engine)


def list_adapters() -> List[Dict[str, Any]]:
    """List all available portal adapters with their info."""
    results = []
    portals = list_available_portals()
    for p in portals:
        adapter_id = p.get("adapter", p.get("file", "").replace(".yaml", ""))
        results.append({
            "name": p.get("name", adapter_id),
            "short_name": p.get("short_name", adapter_id),
            "adapter": adapter_id,
            "file": p.get("file", f"{adapter_id}.yaml"),
            "has_adapter": adapter_id in _ADAPTER_MAP,
        })
    return results
