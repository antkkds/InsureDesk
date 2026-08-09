"""Fill Details (owner/address/vehicle) with FillEngine + modified adapter,
radio fix, market value manual, PDS → Continue → Step 3."""
import asyncio, json, sys
sys.path.insert(0, "/home/antkk/InsureDesk")
sys.path.insert(0, "/home/antkk/InsureDesk/scripts")
from playwright.async_api import async_playwright

DETAILS_DATA = {
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
    # vehicle (TEST123 = no plate lookup → all manual)
    "body_type": "SEDAN",
    "seating_capacity": "5",
    "safety_feature": "ABS & Airbags (more than 2)",
    "hire_purchase": "N",
}


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
            print("NO QUOTE TAB"); return
        if not await page.evaluate("document.getElementById('proposalTitle') ? true : false"):
            print("NOT ON DETAILS"); return
        print("ON DETAILS ✅ quote:", page.url.split("/")[-2][:8])

        from src.fill.engine import FillEngine
        from src.portal.formspec import MotorPrivateCarSpec
        from gears_live_adapter import GearsPageAdapter
        spec = MotorPrivateCarSpec.from_yaml_file("/home/antkk/InsureDesk/src/portal/forms/motor_private_car.yaml")
        engine = FillEngine()
        adapter = GearsPageAdapter(page)

        for section_name in ["owner", "address", "vehicle"]:
            schema = spec.live_schema(section_name)
            print(f"\n=== {section_name} ===")
            result = await engine.fill_section(adapter, schema, DETAILS_DATA)
            for fr in result.fields:
                print(f"  {'✅' if fr.success else '❌'} {fr.field:20s} {(fr.message or fr.error or '')[:70]}")

        # Radio fix: gender M + hire_purchase N share name=radioBasic
        print("\n=== RADIO FIX ===")
        await page.evaluate("document.querySelector(\"input[name='radioBasic'][value='M']\").click()")
        await asyncio.sleep(0.4)
        await page.evaluate("document.querySelector(\"input[name='radioBasic'][value='N']\").click()")
        await asyncio.sleep(0.4)
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

        # Market value: enable + set manually (do NOT click check — returns 0 for TEST123)
        print("\n=== MARKET VALUE ===")
        await page.evaluate("""(() => {
            const el = document.getElementById('marketValue');
            if (el) { el.removeAttribute('disabled'); el.focus(); el.value = '50000';
                      el.dispatchEvent(new Event('input', {bubbles:true}));
                      el.dispatchEvent(new Event('change', {bubbles:true})); el.blur(); }
        })()""")
        await asyncio.sleep(1)
        mv = await page.evaluate("document.getElementById('marketValue') ? document.getElementById('marketValue').value : 'MISSING'")
        print("marketValue:", repr(mv))

        # NCD check (benign)
        try:
            await page.click("#check-ncd", timeout=5000)
            await asyncio.sleep(2)
            print("check-ncd clicked")
        except Exception as e:
            print("check-ncd err:", str(e)[:60])

        # PDS: consent already checked via FillEngine; click emailPDSandPDPN
        print("\n=== PDS ===")
        consent = await adapter.is_checked('mat-checkbox:has-text("acknowledge and declare") input[type=checkbox]')
        print("consent:", consent)
        if consent:
            await page.evaluate("document.getElementById('emailPDSandPDPN').click()")
            await asyncio.sleep(4)
            # dismiss any success modal
            modal = await page.evaluate("""(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const ok = btns.find(e => (e.textContent || '').trim() === 'Ok');
                if (ok) { ok.click(); return true; }
                return false;
            })()""")
            print("PDS modal dismissed:", modal)
            await asyncio.sleep(2)

        # Continue → Step 3
        print("\n=== CONTINUE ===")
        await page.evaluate("""(() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const hit = btns.find(e => (e.textContent || '').trim() === 'Continue');
            if (hit) { hit.click(); return true; }
            return false;
        })()""")
        await asyncio.sleep(8)
        has_plan = await page.evaluate("document.getElementById('select_plan_0') ? true : false")
        print("On Step 3:", has_plan)
        body = await page.evaluate("document.body ? document.body.innerText.replace(/\\s+/g,' ').slice(0, 250) : ''")
        print("body:", body[:250])
        # any renew modal?
        renew = await page.evaluate("""(() => {
            const btns = Array.from(document.querySelectorAll('button'));
            return btns.some(e => (e.textContent || '').includes('Return to home'));
        })()""")
        print("renew modal present:", renew)


asyncio.run(main())
