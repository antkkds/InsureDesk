"""InsureDesk — Portal Capture Engine.

Interactive browser-based capture tool for generating Portal Profiles.
Users click on elements in the browser, name them, and the engine
generates a scored YAML Portal Profile automatically.

Flow:
    start_session() → navigate to portal
      → inject capture JS (click elements to capture)
      → name each captured element
      → generate_profile() → YAML output
      → validate_profile() → test selectors work

Usage:
    engine = create_browser_engine(prefer="playwright")
    await engine.start()
    capture = CaptureEngine(engine)
    await capture.start_session("https://portal.example.com/login")
    # User clicks elements → capture prompts for names
    profile = await capture.generate_profile()
    print(profile.to_yaml())
"""

from __future__ import annotations

import json
import os
import time
import yaml
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

from src.browser.driver import BrowserEngine
from src.portal.inspector import (
    BrowserInspector,
    CapturedElement,
    generate_candidate_selectors,
)


# ══════════════════════════════════════════════════════════════════
# PortalProfile — the output of a capture session
# ══════════════════════════════════════════════════════════════════

@dataclass
class CapturedPage:
    """A page within a portal that has been captured."""
    name: str = ""              # e.g. "login", "dashboard"
    url_pattern: str = ""       # URL pattern to identify this page
    title_pattern: str = ""     # Page title pattern
    elements: List[Dict[str, Any]] = field(default_factory=list)
    # elements: [{field_key, selector, tag, label, page_url, score}, ...]


@dataclass
class PortalProfile:
    """A complete portal profile generated from capture session.

    This is the output of CaptureEngine.generate_profile().
    Can be serialized to YAML and loaded as a portal mapping.
    """
    portal_name: str = ""
    short_name: str = ""
    base_url: str = ""
    login_url: str = ""
    login_action: str = ""
    adapter: str = ""
    version: str = "1.0.0"
    captured_at: str = ""
    pages: List[CapturedPage] = field(default_factory=list)

    def get_page(self, name: str) -> Optional[CapturedPage]:
        for p in self.pages:
            if p.name == name:
                return p
        return None

    def get_selector(self, page_name: str, field_key: str) -> Optional[str]:
        page = self.get_page(page_name)
        if not page:
            return None
        for el in page.elements:
            if el.get("field_key") == field_key:
                return el.get("best_selector") or el.get("selector")
        return None

    def to_yaml(self) -> str:
        """Export as YAML portal mapping file.

        Compatible with existing src/portal/mapping.py loader.
        """
        data = {
            "portal": {
                "name": self.portal_name,
                "short_name": self.short_name,
                "base_url": self.base_url,
                "login_url": self.login_url,
                "login_action": self.login_action or None,
                "adapter": self.adapter,
                "_profile_version": self.version,
                "_captured_at": self.captured_at or None,
            },
            "selectors": {},
        }

        for page in self.pages:
            page_selectors = {}
            for el in page.elements:
                key = el.get("field_key", "")
                if key:
                    page_selectors[key] = el.get("best_selector") or el.get("selector", "")
                    # Add descriptive comment via YAML
            if page_selectors:
                # Build nested structure: page_name → field_key → selector
                data["selectors"][page.name] = page_selectors

        return yaml.dump(data, default_flow_style=False, allow_unicode=True,
                         sort_keys=False, width=120)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "PortalProfile":
        """Load a PortalProfile from YAML string."""
        data = yaml.safe_load(yaml_str)
        portal = data.get("portal", {})
        profile = cls(
            portal_name=portal.get("name", ""),
            short_name=portal.get("short_name", ""),
            base_url=portal.get("base_url", ""),
            login_url=portal.get("login_url", ""),
            login_action=portal.get("login_action", ""),
            adapter=portal.get("adapter", ""),
            version=portal.get("_profile_version", "1.0.0"),
            captured_at=portal.get("_captured_at", ""),
        )

        selectors = data.get("selectors", {})
        for page_name, fields in selectors.items():
            page = CapturedPage(name=page_name)
            for field_key, selector in fields.items():
                page.elements.append({
                    "field_key": field_key,
                    "selector": selector,
                    "best_selector": selector,
                    "tag": "",
                    "label": "",
                })
            if page.elements:
                profile.pages.append(page)

        return profile

    def to_dict(self) -> dict:
        return asdict(self)


# ══════════════════════════════════════════════════════════════════
# CaptureEngine
# ══════════════════════════════════════════════════════════════════

CAPTURE_INJECT_JS = """
// InsureDesk Capture Mode — injected into the target portal page
(function() {
    if (window.__insuredesk_capture_active) return;
    window.__insuredesk_capture_active = true;

    let currentOverlay = null;
    let capturedElements = [];

    function createOverlay(el) {
        removeOverlay();
        const rect = el.getBoundingClientRect();
        const overlay = document.createElement('div');
        overlay.id = '__insuredesk_capture_overlay';
        overlay.style.cssText = `
            position: fixed;
            pointer-events: none;
            z-index: 999999;
            border: 2px solid #ff4444;
            background: rgba(255, 68, 68, 0.1);
            transition: all 0.15s ease;
            box-shadow: 0 0 0 9999px rgba(0,0,0,0.3);
        `;
        overlay.style.left = rect.left + 'px';
        overlay.style.top = rect.top + 'px';
        overlay.style.width = rect.width + 'px';
        overlay.style.height = rect.height + 'px';

        // Label
        const label = document.createElement('div');
        label.style.cssText = `
            position: absolute;
            top: -24px;
            left: 0;
            background: #ff4444;
            color: white;
            padding: 2px 8px;
            font: 12px/18px monospace;
            border-radius: 3px 3px 0 0;
            white-space: nowrap;
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
        `;
        const tag = el.tagName.toLowerCase();
        const text = (el.textContent || '').trim().substring(0, 40);
        const id = el.id || '';
        label.textContent = '<' + tag + '>' + (id ? ' #' + id : '') + (text ? ' "' + text + '"' : '');
        overlay.appendChild(label);
        document.body.appendChild(overlay);
        currentOverlay = overlay;
    }

    function removeOverlay() {
        const existing = document.getElementById('__insuredesk_capture_overlay');
        if (existing) existing.remove();
        currentOverlay = null;
    }

    document.addEventListener('mouseover', function(e) {
        if (!window.__insuredesk_capture_active) return;
        const el = e.target;
        if (el === document.body || el === document.documentElement) {
            removeOverlay();
            return;
        }
        if (el.closest('#__insuredesk_capture_overlay')) return;
        createOverlay(el);
    }, true);

    document.addEventListener('click', function(e) {
        if (!window.__insuredesk_capture_active) return;
        e.preventDefault();
        e.stopPropagation();

        const el = e.target;
        if (el.closest('#__insuredesk_capture_overlay')) return;

        // Collect element info
        const tag = el.tagName.toLowerCase();
        const text = (el.textContent || '').trim().substring(0, 200);
        const attrs = {};
        for (const a of el.attributes) {
            if (a.name !== 'style') attrs[a.name] = a.value;
        }
        const inputType = el.getAttribute('type') || '';
        const placeholder = el.getAttribute('placeholder') || '';
        const labelText = (() => {
            if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
            const id = el.getAttribute('id');
            if (id) {
                const lbl = document.querySelector('label[for="' + id + '"]');
                if (lbl) return (lbl.textContent || '').trim();
            }
            const parent = el.closest('label');
            if (parent) return (parent.textContent || '').trim();
            return '';
        })();
        const role = el.getAttribute('role') || '';

        // Generate candidate selectors
        const candidates = {};
        // Try ID
        if (attrs.id) candidates['#' + attrs.id] = 95;
        // data-testid
        if (attrs['data-testid']) candidates['[data-testid="' + attrs['data-testid'] + '"]'] = 92;
        // name
        if (attrs.name) candidates['[name="' + attrs.name + '"]'] = 82;
        // aria-label
        if (labelText) candidates['[aria-label="' + labelText + '"]'] = 80;
        // placeholder
        if (placeholder) candidates['[placeholder="' + placeholder + '"]'] = 75;
        // class-based
        const classes = (attrs.class || '').split(/\\s+/).filter(Boolean);
        const stableClasses = classes.filter(c => !/^[a-z]+-[a-f0-9]{4,}/.test(c));
        if (stableClasses.length > 0) {
            candidates['.' + stableClasses.join('.')] = 55;
        }
        // text-based
        if (text && text.length > 1 && text.length < 100) {
            candidates[':text-is("' + text.substring(0, 80) + '")'] = 60;
        }

        const bestSelector = Object.keys(candidates).sort((a,b) => candidates[b]-candidates[a])[0] || tag;

        const info = {
            tag: tag,
            text: text,
            attrs: attrs,
            inputType: inputType,
            placeholder: placeholder,
            label: labelText || '',
            role: role,
            candidates: candidates,
            bestSelector: bestSelector,
            pageUrl: window.location.href,
            pageTitle: document.title,
        };

        // Dispatch custom event for the capture engine to pick up
        window.dispatchEvent(new CustomEvent('insuredesk-captured', { detail: info }));

        removeOverlay();
    }, true);

    console.log('InsureDesk Capture Mode activated — click elements to capture');
})();
"""


class CaptureEngine:
    """Interactive portal capture engine.

    Injects click-to-capture JS into the target portal page.
    Each click captures the element, generates scored selectors,
    and stores it for profile generation.

    Usage:
        engine = create_browser_engine(prefer="playwright")
        capture = CaptureEngine(engine)
        await capture.start_session("https://portal.example.com/login")
        # User clicks elements on the page
        await capture.wait_for_captures(timeout=300)  # wait for user input
        profile = await capture.generate_profile()
        print(profile.to_yaml())
    """

    def __init__(self, engine: BrowserEngine):
        self._engine = engine
        self._inspector = BrowserInspector()
        self._captured: List[Dict[str, Any]] = []
        self._page_groups: Dict[str, List[Dict[str, Any]]] = {}
        self._session_url: str = ""
        self._session_title: str = ""
        self._active: bool = False
        self._field_names: Dict[str, str] = {}  # selector → field_key mapping

    @property
    def captured(self) -> List[Dict[str, Any]]:
        return list(self._captured)

    @property
    def page_groups(self) -> Dict[str, List[Dict[str, Any]]]:
        return dict(self._page_groups)

    @property
    def is_active(self) -> bool:
        return self._active

    async def start_session(self, url: str) -> bool:
        """Start a capture session by navigating to the portal URL.

        Injects the capture JS and waits for the page to be ready.
        """
        try:
            ok = await self._engine.navigate(url)
            if not ok:
                return False

            # Wait for page to load
            await self._engine.wait_for_navigation(timeout=15000)
            info = await self._engine.get_page_info()
            self._session_url = info.url
            self._session_title = info.title

            # Connect inspector
            await self._inspector.connect(self._engine)

            # Inject capture JS
            result = await self._engine.evaluate(CAPTURE_INJECT_JS)
            self._active = True

            # Listen for captured events via polling
            return True

        except Exception as e:
            self._active = False
            return False

    async def stop_session(self):
        """Stop the capture session and deactivate capture JS."""
        if self._engine:
            try:
                await self._engine.evaluate(
                    "window.__insuredesk_capture_active = false;"
                )
            except Exception:
                pass
        self._active = False
        await self._inspector.disconnect()

    async def poll_captured(self) -> List[Dict[str, Any]]:
        """Poll for newly captured elements since last call.

        Returns list of captured element info dicts.
        Each contains: tag, text, attrs, bestSelector, candidates, pageUrl, etc.
        """
        if not self._engine or not self._active:
            return []

        try:
            result = await self._engine.evaluate("""
                (() => {
                    const items = window.__insuredesk_captured_items || [];
                    window.__insuredesk_captured_items = [];
                    return items;
                })()
            """)
        except Exception:
            return []

        items = result if isinstance(result, list) else []

        # Convert captured items, generate proper selectors
        new_items = []
        for item in items:
            captured = await self._capture_from_info(item)
            if captured:
                new_items.append(captured)

        return new_items

    async def _capture_from_info(self, info: dict) -> Optional[Dict[str, Any]]:
        """Convert raw JS captured info to a structured capture record."""
        try:
            selector = info.get("bestSelector", "")
            if not selector:
                return None

            # Use the inspector for proper selector scoring
            el = await self._inspector.capture(selector)
            if el is None:
                # Build manually
                candidates = info.get("candidates", {})
                el = CapturedElement(
                    tag=info.get("tag", ""),
                    text=info.get("text", ""),
                    attributes=info.get("attrs", {}),
                    selector=selector,
                    input_type=info.get("inputType", ""),
                    page_url=info.get("pageUrl", ""),
                    placeholder=info.get("placeholder", ""),
                    label=info.get("label", ""),
                    role=info.get("role", ""),
                    candidate_selectors=candidates,
                )

            record = {
                "tag": el.tag,
                "selector": selector,
                "best_selector": el.best_selector,
                "candidate_selectors": el.candidate_selectors,
                "text": el.text[:80] if el.text else "",
                "label": el.label or "",
                "placeholder": el.placeholder or "",
                "input_type": el.input_type,
                "role": el.role,
                "page_url": el.page_url or self._session_url,
                "page_title": info.get("pageTitle", self._session_title),
                "timestamp": time.time(),
                "field_key": "",  # To be filled by user
            }

            self._captured.append(record)

            # Group by page URL
            page_key = self._page_key(record["page_url"])
            if page_key not in self._page_groups:
                self._page_groups[page_key] = []
            self._page_groups[page_key].append(record)

            return record

        except Exception:
            return None

    def set_field_name(self, index: int, field_key: str):
        """Set the field key/name for a captured element.

        Args:
            index: Index into self._captured list
            field_key: e.g. "username", "password", "submit"
        """
        if 0 <= index < len(self._captured):
            self._captured[index]["field_key"] = field_key
            self._field_names[self._captured[index]["selector"]] = field_key

    def get_unnamed(self) -> List[Tuple[int, Dict[str, Any]]]:
        """Get all captured elements that don't have a field_key yet.

        Returns list of (index, record) tuples.
        """
        return [(i, r) for i, r in enumerate(self._captured) if not r.get("field_key")]

    def remove_capture(self, index: int):
        """Remove a captured element by index."""
        if 0 <= index < len(self._captured):
            record = self._captured.pop(index)
            self._field_names.pop(record["selector"], None)

    def _page_key(self, url: str) -> str:
        """Extract a page key from URL for grouping captures."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        # Use last path segment
        segments = [s for s in path.split("/") if s]
        if segments:
            key = segments[-1]
            # Strip file extension
            if "." in key:
                key = key.rsplit(".", 1)[0]
            return key
        return "home"

    def _infer_page_name(self, url: str) -> str:
        """Infer a human-readable page name from URL."""
        key = self._page_key(url)
        # Common page names
        mapping = {
            "login": "login",
            "userlogin": "login",
            "signin": "login",
            "dashboard": "dashboard",
            "home": "home",
            "get-quote": "get_quote",
            "make-a-claim": "make_claim",
            "claim": "make_claim",
            "my-profile": "my_profile",
            "profile": "my_profile",
            "my-account": "my_account",
            "account": "my_account",
            "my-client": "my_client",
            "client": "my_client",
        }
        if key in mapping:
            return mapping[key]
        return key.replace("-", "_")

    async def generate_profile(self) -> PortalProfile:
        """Generate a PortalProfile from all captured elements.

        Groups elements by page, infers page names, and builds
        the complete profile structure.
        """
        profile = PortalProfile(
            portal_name=self._session_title or "Unknown Portal",
            short_name="",
            base_url=self._session_url,
            adapter="auto_captured",
            version="1.0.0",
            captured_at=datetime.utcnow().isoformat(),
        )

        # Group captures by page URL
        page_captures: Dict[str, List[Dict]] = {}
        for record in self._captured:
            url = record.get("page_url", self._session_url)
            if url not in page_captures:
                page_captures[url] = []
            page_captures[url].append(record)

        # Build pages
        for url, captures in page_captures.items():
            page_name = self._infer_page_name(url)
            page = CapturedPage(
                name=page_name,
                url_pattern=url,
            )
            for c in captures:
                if c.get("field_key"):
                    page.elements.append({
                        "field_key": c["field_key"],
                        "selector": c.get("selector", ""),
                        "best_selector": c.get("best_selector", c.get("selector", "")),
                        "tag": c.get("tag", ""),
                        "label": c.get("label", ""),
                        "placeholder": c.get("placeholder", ""),
                        "input_type": c.get("input_type", ""),
                        "page_url": c.get("page_url", ""),
                        "score": c.get("candidate_selectors", {}).get(
                            c.get("best_selector", ""), 0
                        ),
                    })
            if page.elements:
                profile.pages.append(page)

        return profile

    async def validate_profile(self, profile: PortalProfile) -> Dict[str, Any]:
        """Validate a generated profile by testing selectors against the live page.

        Returns dict with: total, success, failures, details.
        """
        results = {"total": 0, "success": 0, "failures": [], "details": []}

        for page in profile.pages:
            for el in page.elements:
                results["total"] += 1
                selector = el.get("best_selector") or el.get("selector", "")
                if not selector:
                    results["failures"].append({
                        "page": page.name,
                        "field": el.get("field_key", ""),
                        "error": "No selector",
                    })
                    continue

                try:
                    js = f"document.querySelectorAll({json.dumps(selector)}).length"
                    match_count = await self._engine.evaluate(js)
                    if match_count and match_count > 0:
                        results["success"] += 1
                        results["details"].append({
                            "page": page.name,
                            "field": el.get("field_key", ""),
                            "selector": selector,
                            "matches": match_count,
                            "status": "ok",
                        })
                    else:
                        results["failures"].append({
                            "page": page.name,
                            "field": el.get("field_key", ""),
                            "selector": selector,
                            "error": f"0 matches",
                        })
                except Exception as e:
                    results["failures"].append({
                        "page": page.name,
                        "field": el.get("field_key", ""),
                        "selector": selector,
                        "error": str(e),
                    })

        return results


# ══════════════════════════════════════════════════════════════════
# TUI Capture Session — interactive terminal UI
# ══════════════════════════════════════════════════════════════════

class CaptureSession:
    """Interactive capture session using terminal prompts.

    Guides the user through:
    1. Start capture mode on the portal
    2. Click elements in the browser
    3. Name each captured element
    4. Review and organize captures
    5. Generate and save the portal profile

    Usage:
        engine = create_browser_engine(prefer="playwright")
        session = CaptureSession(engine)
        profile = await session.run("https://portal.example.com/login")
        print(profile.to_yaml())
    """

    def __init__(self, engine: BrowserEngine):
        self._engine = engine
        self._capture = CaptureEngine(engine)
        self._quiet = False

    async def run(
        self,
        url: str,
        timeout: int = 600,
        quiet: bool = False,
    ) -> Optional[PortalProfile]:
        """Run an interactive capture session.

        Args:
            url: Portal URL to capture
            timeout: Max seconds to wait for captures
            quiet: If True, skip prompts (for automated testing)

        Returns:
            PortalProfile or None if cancelled
        """
        self._quiet = quiet

        # Start session
        ok = await self._capture.start_session(url)
        if not ok:
            return None

        if not quiet:
            print(f"\n🔍 Capture Mode activated!")
            print(f"  URL: {url}")
            print(f"  Click elements on the page to capture them")
            print(f"  After each click, name the field in the terminal")
            print(f"  Type 'done' when finished\n")

        # Poll for captures
        import asyncio
        start_time = time.time()
        last_poll = 0

        while time.time() - start_time < timeout:
            await asyncio.sleep(0.5)

            # Poll for new captures
            new_items = await self._capture.poll_captured()
            for item in new_items:
                if quiet:
                    # Auto-name: use tag_text pattern
                    field_key = f"{item['tag']}_{item.get('label') or item.get('placeholder') or item.get('text', 'unknown')[:20]}"
                    field_key = field_key.lower().replace(" ", "_").replace("-", "_")
                    self._capture.set_field_name(len(self._capture.captured) - 1, field_key)
                else:
                    self._prompt_for_name(item)

            # Check for done signal via browser
            try:
                done = await self._engine.evaluate(
                    "window.__insuredesk_capture_active === false || "
                    "document.querySelector('#__insuredesk_capture_done') !== null"
                )
                if done:
                    break
            except Exception:
                pass

        # Generate profile
        profile = await self._capture.generate_profile()

        if not quiet:
            print(f"\n✅ Captured {len(self._capture.captured)} elements across {len(profile.pages)} pages")

        await self._capture.stop_session()
        return profile

    def _prompt_for_name(self, item: dict):
        """Prompt user to name a captured element."""
        tag = item.get("tag", "?")
        text = (item.get("label") or item.get("placeholder") or item.get("text", ""))[:40]
        selector = item.get("best_selector", "")[:60]
        print(f"\n📸 Captured: <{tag}> \"{text}\"")
        print(f"   Selector: {selector}")
        print(f"   Enter field name (e.g. username, password, submit): ", end="")
        name = input().strip()
        if name and name.lower() != "skip":
            idx = len(self._capture.captured) - 1
            field_key = name.lower().replace(" ", "_").replace("-", "_")
            self._capture.set_field_name(idx, field_key)
            print(f"   ✅ Saved as '{field_key}'")
