"""Reusable Playwright CDP adapter for live GEARS filling.

Exposes the BrowserEngine-like interface that FillStrategy expects
(fill/click/evaluate/get_attribute/get_value/is_checked/wait_for_selector).

Selector support:
  - standard CSS (querySelector)
  - Playwright-style :has-text() on the base element, e.g.
    mat-checkbox:has-text("acknowledge") input[type=checkbox]
    (resolved via JS for is_checked/get_attribute; Playwright handles it
    natively for click/wait_for_selector)
"""
from __future__ import annotations


class GearsPageAdapter:
    """Minimal BrowserEngine-compatible adapter over a Playwright page."""

    def __init__(self, page):
        self._page = page

    # -- selector resolution -------------------------------------------

    @staticmethod
    def _resolve_js(selector: str) -> str:
        """JS snippet that resolves a (possibly :has-text) selector to an element."""
        return f"""(() => {{
            const raw = {selector!r};
            const m = raw.match(/^([^:]+):has-text\\(["'](.+?)["']\\)\\s*(.*)$/);
            let el = null;
            if (m) {{
                const els = Array.from(document.querySelectorAll(m[1]));
                const hit = els.find(e => (e.textContent || '').includes(m[2]));
                if (hit) el = m[3] ? hit.querySelector(m[3]) : hit;
            }} else {{
                el = document.querySelector(raw);
            }}
            return el;
        }})()"""

    # -- BrowserEngine interface ---------------------------------------

    async def click(self, selector: str, timeout: int = 10000) -> bool:
        try:
            await self._page.click(selector, timeout=timeout)
            return True
        except Exception:
            # Fallback for hidden-but-interactive controls (Angular radio/
            # checkbox inputs are display:none; JS click updates their model —
            # verified on live GEARS. NOTE: mat-option is the EXCEPTION —
            # it requires native click, handled by AutocompleteStrategy.)
            try:
                await self._page.evaluate(
                    f"""(() => {{
                        const el = {self._resolve_js(selector)};
                        if (el) {{ el.click(); return true; }}
                        return false;
                    }})()"""
                )
                return True
            except Exception:
                return False

    async def fill(self, selector: str, value: str, delay_ms: int = 50) -> bool:
        try:
            await self._page.fill(selector, value, timeout=8000)
            return True
        except Exception:
            # Angular-friendly JS fallback (element covered/obscured → set value
            # + dispatch input events so Angular's model picks it up)
            try:
                await self._page.evaluate(
                    f"""(() => {{
                        const el = {self._resolve_js(selector)};
                        if (!el) return false;
                        el.focus();
                        el.value = {value!r};
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                        el.dispatchEvent(new Event('change', {{bubbles: true}}));
                        return true;
                    }})()"""
                )
                return True
            except Exception:
                return False

    async def evaluate(self, script: str):
        return await self._page.evaluate(script)

    async def get_attribute(self, selector: str, attr: str) -> str | None:
        if attr == "value":
            return await self._page.evaluate(
                f"""(() => {{
                    const el = {self._resolve_js(selector)};
                    return el ? (el.value !== undefined ? el.value : el.getAttribute('value')) : null;
                }})()"""
            )
        return await self._page.evaluate(
            f"""(() => {{
                const el = {self._resolve_js(selector)};
                return el ? el.getAttribute({attr!r}) : null;
            }})()"""
        )

    async def get_value(self, selector: str) -> str | None:
        return await self.get_attribute(selector, "value")

    async def is_checked(self, selector: str) -> bool:
        return await self._page.evaluate(
            f"""(() => {{
                const el = {self._resolve_js(selector)};
                return el ? !!el.checked : false;
            }})()"""
        )

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        try:
            await self._page.wait_for_selector(selector, state="attached", timeout=timeout)
            return True
        except Exception:
            return False
