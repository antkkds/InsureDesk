"""From introduce page: Motor Insurance → PMOT → Get quote → fill quotation_details
with NEW plate → Continue → Details. Prints state at each step."""
import asyncio, json, sys
sys.path.insert(0, "/home/antkk/InsureDesk")
from playwright.async_api import async_playwright

NEW_PLATE = "WQQ 1313"
SAMPLE = {
    "applicant_type": "individual",
    "condition": "REGISTERED",
    "id_type": "NRIC",
    "id_number": "881212145678",
    "sst_number": "",
    "vehicle_number": NEW_PLATE,
    "place": "KUALA LUMPUR",
}


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
        ctx = b.contexts[0]
        page = None
        for p in ctx.pages:
            if "gears" in p.url or "quotations" in p.url:
                page = p
                break
        if not page:
            print("NO PAGE"); return

        # 1. Click Motor Insurance product
        r = await page.evaluate("""(() => {
            const els = Array.from(document.querySelectorAll('a, button, div, span'));
            const target = els.find(e => (e.textContent||'').trim() === 'Motor Insurance' && e.children.length === 0);
            if (target) { target.click(); return 'clicked ' + target.tagName; }
            return 'not found';
        })()""")
        print("1. Motor Insurance:", r)
        await asyncio.sleep(4)
        print("   URL:", page.url[:130])

        # 2. Find Get quote for Private Motor Insurance
        links = await page.evaluate("""(() => {
            const out = [];
            document.querySelectorAll('a').forEach(a => {
                const t = (a.textContent||'').trim().replace(/\\s+/g,' ');
                if (t) out.push({t: t.slice(0,60), href: (a.href||'').slice(0,120)});
            });
            return out.slice(0, 30);
        })()""")
        print("2. LINKS:", json.dumps(links, indent=1))

        # click Get quote
        r2 = await page.evaluate("""(() => {
            const els = Array.from(document.querySelectorAll('a, button, div, span'));
            const target = els.find(e => {
                const t = (e.textContent||'').trim().replace(/\\s+/g,' ');
                return t.includes('Get quote') && e.children.length === 0;
            });
            if (target) { target.click(); return 'clicked: ' + (target.textContent||'').trim().slice(0,40); }
            return 'not found';
        })()""")
        print("3. Get quote:", r2)
        await asyncio.sleep(5)
        print("   URL:", page.url[:150])

        # 3. Fill quotation_details
        body = await page.evaluate("document.body ? document.body.innerText.slice(0,300) : ''")
        print("4. BODY:", body.replace(chr(10), ' | ')[:250])

        # check if quotation_details form present
        has_form = await page.evaluate("document.getElementById('condition') ? true : false")
        print("5. quotation_details form present:", has_form)
        if has_form:
            from src.fill.engine import FillEngine
            from src.portal.formspec import MotorPrivateCarSpec
            sys.path.insert(0, "/home/antkk/InsureDesk")

            class Adapter:
                def __init__(self, page): self._page = page
                async def click(self, selector, timeout=10000):
                    try:
                        await self._page.click(selector, timeout=timeout); return True
                    except Exception:
                        try:
                            await self._page.evaluate(f"""(() => {{ const el = document.querySelector({selector!r}); if (el) {{ el.click(); return true; }} return false; }})()""")
                            return True
                        except Exception: return False
                async def fill(self, selector, value, delay_ms=50):
                    try:
                        await self._page.fill(selector, value, timeout=8000); return True
                    except Exception:
                        try:
                            await self._page.evaluate(f"""(() => {{ const el = document.querySelector({selector!r}); if (!el) return false; el.focus(); el.value = {value!r}; el.dispatchEvent(new Event('input', {{bubbles:true}})); el.dispatchEvent(new Event('change', {{bubbles:true}})); return true; }})()""")
                            return True
                        except Exception: return False
                async def evaluate(self, script): return await self._page.evaluate(script)
                async def get_attribute(self, selector, attr):
                    if attr == "value":
                        return await self._page.evaluate(f"""(() => {{ const el = document.querySelector({selector!r}); return el ? (el.value !== undefined ? el.value : el.getAttribute('value')) : null; }})()""")
                    return await self._page.get_attribute(selector, attr)
                async def get_value(self, selector): return await self.get_attribute(selector, "value")
                async def is_checked(self, selector):
                    return await self._page.evaluate(f"""(() => {{ const el = document.querySelector({selector!r}); return el ? !!el.checked : false; }})()""")
                async def wait_for_selector(self, selector, timeout=10000):
                    try:
                        await self._page.wait_for_selector(selector, state="attached", timeout=timeout); return True
                    except Exception: return False

            spec = MotorPrivateCarSpec.from_yaml_file("/home/antkk/InsureDesk/src/portal/forms/motor_private_car.yaml")
            engine = FillEngine()
            schema = spec.live_schema("quotation_details")
            result = await engine.fill_section(Adapter(page), schema, SAMPLE)
            print("6. FILL RESULTS:")
            for fr in result.fields:
                print(f"   {'✅' if fr.success else '❌'} {fr.field:18s} {(fr.message or fr.error or '')[:80]}")

            # click Continue
            await page.click("button:has-text('Continue')", timeout=15000)
            await asyncio.sleep(5)
            print("7. URL:", page.url[:150])
            body = await page.evaluate("document.body ? document.body.innerText.slice(0,700) : ''")
            print("8. BODY:", body.replace(chr(10), ' | ')[:650])

        await b.close()


asyncio.run(main())
