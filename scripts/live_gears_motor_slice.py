"""LIVE vertical slice: FormSpec → FillEngine → GEARS quotation_details.

Fills the 7 confirmed fields on the REAL GEARS PMOT quotation details page
using the EXACT FormSpec + FillEngine path (no portal-specific hacks).

Adapter: thin Playwright page wrapper exposing the BrowserEngine interface
that FillStrategy expects (fill/click/evaluate/get_attribute/wait_for_selector).
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/home/antkk/InsureDesk")

from playwright.async_api import async_playwright

from src.fill.engine import FillEngine
from src.portal.formspec import MotorPrivateCarSpec

MOTOR_YAML = "/home/antkk/InsureDesk/src/portal/forms/motor_private_car.yaml"

SAMPLE_DATA = {
    "applicant_type": "individual",
    "condition": "REGISTERED",       # options: REGISTERED / NEW REGISTERED / REGISTERED-TRANSFER OWNER
    "id_type": "NRIC",
    "id_number": "881212-14-5678",
    "sst_number": "",            # optional
    "vehicle_number": "WQK 1234",    # NOTE: disabled when condition=NEW REGISTERED (new car, no plate yet)
    "place": "KUALA LUMPUR",
}


class PageAdapter:
    """Minimal BrowserEngine-compatible adapter over a Playwright page."""

    def __init__(self, page):
        self._page = page

    async def click(self, selector: str, timeout: int = 10000) -> bool:
        try:
            await self._page.click(selector, timeout=timeout)
            return True
        except Exception:
            # Fallback for hidden-but-interactive controls (Angular radio/
            # checkbox inputs are display:none; JS click updates their model —
            # verified on live GEARS. NOTE: mat-option is the EXCEPTION —
            # it requires native click, handled by AutocompleteStrategy
            # via Playwright click, never this fallback.)
            try:
                await self._page.evaluate(
                    f"""(() => {{
                        const el = document.querySelector({selector!r});
                        if (el) {{ el.click(); return true; }}
                        return false;
                    }})()"""
                )
                return True
            except Exception:
                return False

    async def fill(self, selector: str, value: str, delay_ms: int = 50) -> bool:
        try:
            await self._page.fill(selector, value, timeout=10000)
            return True
        except Exception:
            return False

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        try:
            # Angular Material hides native radio/checkbox inputs
            # (display:none) and shows styled labels — use "attached" so
            # hidden-but-interactive controls still resolve.
            await self._page.wait_for_selector(selector, timeout=timeout, state="attached")
            return True
        except Exception:
            return False

    async def evaluate(self, script: str):
        try:
            return await self._page.evaluate(script)
        except Exception:
            return None

    async def get_attribute(self, selector: str, attr: str):
        try:
            if attr == "value":
                # Angular Material inputs store value as a JS property,
                # NOT a DOM attribute — get_attribute returns None.
                return await self._page.evaluate(
                    f"""(() => {{
                        const el = document.querySelector({selector!r});
                        return el ? el.value : null;
                    }})()"""
                )
            return await self._page.get_attribute(selector, attr)
        except Exception:
            return None

    async def get_text(self, selector: str) -> str:
        try:
            el = await self._page.query_selector(selector)
            return await el.inner_text() if el else ""
        except Exception:
            return ""

    async def get_value(self, selector: str) -> str:
        val = await self.get_attribute(selector, "value")
        return val or ""

    async def is_checked(self, selector: str) -> bool:
        try:
            return await self._page.is_checked(selector)
        except Exception:
            return False

    async def set_checked(self, selector: str, checked: bool) -> bool:
        try:
            if checked:
                await self._page.check(selector)
            else:
                await self._page.uncheck(selector)
            return True
        except Exception:
            return False


async def main():
    spec = MotorPrivateCarSpec.from_yaml_file(MOTOR_YAML)
    schema = spec.live_schema("quotation_details")
    if schema is None:
        print("❌ No confirmed fields — live gate blocks the run")
        return

    print(f"Live-ready schema: {list(schema.fields.keys())}")
    print(f"Gate check: quotation_details confirmed fields only\n")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9333")
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "gears" in pg.url and "PMOT" in pg.url:
                page = pg
                break
        if page is None:
            for pg in ctx.pages:
                if "gears" in pg.url:
                    page = pg
                    break
        if page is None:
            print("❌ No GEARS tab found")
            await browser.close()
            return

        print("Target page:", page.url[:120])
        # Ensure we're on the quotation details page
        if "/detail" not in page.url:
            print("⚠️  Not on a /detail page — navigating via product list...")
            await page.goto(
                "https://gears-my.greateasterngeneral.com/MY/AgencySales/quotations/introduce/product-list?id=PMOT",
                wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(5000)
            await page.evaluate("""() => {
                const btns = document.querySelectorAll('.btn-primary');
                for (const b of btns) {
                    if ((b.innerText||'').includes('Get quote')) { b.click(); return true; }
                }
                return false;
            }""")
            await page.wait_for_timeout(10000)
            print("Now at:", page.url[:140])

        driver = PageAdapter(page)

        engine = FillEngine()
        result = await engine.fill_section(driver, schema, SAMPLE_DATA)

        print("\n=== FILL RESULTS (FormSpec → FillEngine → GEARS) ===")
        for f in result.fields:
            status = "✅" if f.success else "❌"
            err = f" — {f.error}" if f.error else ""
            print(f"  {status} {f.field}: {f.message or 'OK'}{err} ({f.duration_ms}ms)")

        print(f"\nTOTAL: {result.succeeded}/{result.total_fields} ok, {result.failed} failed")

        # Independent read-back verification
        print("\n=== INDEPENDENT READ-BACK (page state) ===")
        for fd in schema.fields.values():
            val = await driver.get_attribute(fd.selector, "value")
            print(f"  {fd.name} ({fd.selector}) = {val!r}")

        await browser.close()


asyncio.run(main())
