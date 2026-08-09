"""Fill Details page on the NEW quote (WQQ1313, no policy) + handle radio
conflict + PDS modal + market value/NCD buttons → Continue → Step 3."""
import asyncio, json, sys
sys.path.insert(0, "/home/antkk/InsureDesk")
from playwright.async_api import async_playwright

DATA = {
    # owner
    "salutation": "Mr",
    "fullname": "Fionn Liang",
    "gender": "M",
    "marital_status": "Single",
    "years_driving_exp": "5",
    "mobile": "0123456789",
    "email": "fionn.liang@gmail.com",
    "pds_consent": True,
    # address
    "postcode": "50000",
    "state": "KUALA LUMPUR",
    "address1": "12, Jalan Merdeka",
    # vehicle
    "body_type": "SEDAN",
    "seating_capacity": "5",
    "safety_feature": "ABS & Airbags (more than 2)",
    "hire_purchase": "N",
}


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


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
        ctx = b.contexts[0]
        page = None
        for p in ctx.pages:
            if "quotations" in p.url and "detail" in p.url:
                page = p
                break
        if not page:
            print("NO PAGE"); return
        if not await page.evaluate("document.getElementById('proposalTitle') ? true : false"):
            print("NOT ON DETAILS"); return

        from src.fill.engine import FillEngine
        from src.portal.formspec import MotorPrivateCarSpec
        spec = MotorPrivateCarSpec.from_yaml_file("/home/antkk/InsureDesk/src/portal/forms/motor_private_car.yaml")
        engine = FillEngine()
        adapter = Adapter(page)

        for section_name in ["owner", "address", "vehicle"]:
            schema = spec.live_schema(section_name)
            print(f"\n=== {section_name} ===")
            result = await engine.fill_section(adapter, schema, DATA)
            for fr in result.fields:
                print(f"  {'✅' if fr.success else '❌'} {fr.field:20s} {(fr.message or fr.error or '')[:80]}")

        # Radio conflict fix: gender M + hire purchase N share name=radioBasic.
        # Click M first, then N; then re-assert both Angular models via native
        # click on each (last wins DOM; portal model check happens on submit).
        print("\n=== RADIO FIX ===")
        await page.evaluate("document.querySelector(\"input[name='radioBasic'][value='M']\").click()")
        await asyncio.sleep(0.4)
        await page.evaluate("document.querySelector(\"input[name='radioBasic'][value='N']\").click()")
        await asyncio.sleep(0.4)
        # re-click M so gender is set; hire-purchase N state will be re-checked
        await page.evaluate("document.querySelector(\"input[name='radioBasic'][value='M']\").click()")
        await asyncio.sleep(0.4)
        await page.evaluate("document.querySelector(\"input[name='radioBasic'][value='N']\").click()")
        await asyncio.sleep(1)
        state = await page.evaluate("""(() => {
            const out = {};
            document.querySelectorAll("input[name='radioBasic']").forEach(el => out[el.value] = el.checked);
            return out;
        })()""")
        print("RADIO STATE:", json.dumps(state))

        # Check market value + NCD buttons (vehicle section actions)
        print("\n=== ACTIONS ===")
        try:
            await page.click("#check-market-value", timeout=8000)
            print("  check-market-value clicked")
            await asyncio.sleep(3)
            mv = await page.evaluate("document.getElementById('marketValue') ? document.getElementById('marketValue').value : 'MISSING'")
            print("  marketValue:", repr(mv))
        except Exception as e:
            print("  check-market-value err:", str(e)[:80])
        try:
            await page.click("#check-ncd", timeout=8000)
            print("  check-ncd clicked")
            await asyncio.sleep(3)
            ncd = await page.evaluate("document.getElementById('ncd_Per') ? document.getElementById('ncd_Per').value : 'MISSING'")
            print("  ncd_Per:", repr(ncd))
        except Exception as e:
            print("  check-ncd err:", str(e)[:80])

        # PDS email button (business rule before Continue)
        print("\n=== PDS ===")
        try:
            await page.click("#emailPDSandPDPN", timeout=8000)
            print("  PDS button clicked")
            # Poll for loading overlay to clear (email send can take a while)
            for i in range(18):
                await asyncio.sleep(5)
                loading = await page.evaluate("""(() => {
                    const els = document.querySelectorAll('.loading-banner, .cdk-overlay-container mat-spinner, .mat-progress-spinner, [class*=loading][class*=overlay], .overlay-backdrop');
                    const visible = Array.from(els).filter(e => e.offsetParent !== null || e.getAttribute('role') === 'progressbar');
                    return visible.length;
                })()""")
                print(f"  loading poll {i+1}: {loading}")
                if loading == 0:
                    break
        except Exception as e:
            print("  PDS err:", str(e)[:100])

        # Dismiss any "Before you continue" modal
        try:
            await page.click("button:has-text('Ok')", timeout=4000)
            print("  dismissed Ok modal")
            await asyncio.sleep(1)
        except Exception:
            pass

        # Continue
        print("\n=== CONTINUE ===")
        try:
            await page.click("button:has-text('Continue')", timeout=15000)
            print("  clicked Continue")
            await asyncio.sleep(6)
        except Exception as e:
            print("  Continue err:", str(e)[:150])

        body = await page.evaluate("document.body.innerText.slice(0, 900)")
        print("\nBODY:", body.replace(chr(10), ' | ')[:850])
        errs = await page.evaluate("""(() => {
            const out = [];
            document.querySelectorAll('mat-error, .error, [class*=invalid]').forEach(e => {
                const t = (e.textContent||'').trim();
                if (t && e.offsetParent !== null) out.push(t.slice(0, 90));
            });
            return out.slice(0, 12);
        })()""")
        print("\nERRORS:", json.dumps(errs))
        on_step3 = await page.evaluate("document.body.innerText.includes('Sum insured, add-on')")
        print("ON STEP 3:", on_step3)
        await b.close()


asyncio.run(main())
