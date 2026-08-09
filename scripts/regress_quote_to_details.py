"""Full regression run 1: home → new quote (TEST 123) → Step 1 → Continue →
Details. Verifies the modified adapter (element-type click detection) does not
break quotation_details autocompletes or navigation."""
import asyncio, json, sys
sys.path.insert(0, "/home/antkk/InsureDesk")
sys.path.insert(0, "/home/antkk/InsureDesk/scripts")
from playwright.async_api import async_playwright

STEP1_DATA = {
    "applicant_type": "individual",
    "condition": "REGISTERED",
    "id_type": "NRIC",
    "id_number": "881212145678",
    "vehicle_number": "TEST 123",
    "place": "KUALA LUMPUR",
}


async def js_click_text(page, text, tag="button"):
    return await page.evaluate(f"""(() => {{
        const els = Array.from(document.querySelectorAll('{tag}'));
        const hit = els.find(e => (e.textContent || '').trim().includes({text!r}));
        if (hit) {{ hit.click(); return true; }}
        return false;
    }})()""")


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
        ctx = b.contexts[0]
        page = None
        for p in ctx.pages:
            if "gears-my" in p.url:
                page = p
                break
        if not page:
            print("NO GEARS TAB"); return
        url = page.url
        print("1. current:", url[:100])

        # --- go home via Quotation menu if deep in a quote ---
        has_condition = await page.evaluate("document.getElementById('condition') ? true : false")
        has_proposal = await page.evaluate("document.getElementById('proposalTitle') ? true : false")
        has_plan = await page.evaluate("document.getElementById('select_plan_0') ? true : false")
        if has_condition or has_proposal or has_plan:
            print("   deep in quote — navigating to dashboard")
            await page.goto("https://gears-my.greateasterngeneral.com/MY/AgencySales/quotations/dashboard")
            await asyncio.sleep(3)
            print("   now at:", page.url[:80])
        else:
            print("   at:", page.url[:70])
            await page.goto("https://gears-my.greateasterngeneral.com/MY/AgencySales/quotations/dashboard")
            await asyncio.sleep(4)
            print("   dashboard:", page.url[:70])

        # --- New quote ---
        n = await js_click_text(page, "New")
        print("2. clicked New:", n)
        await asyncio.sleep(3)
        print("   url:", page.url[:90])

        # product select page: click Motor Insurance card (.item_product)
        await js_click_text(page, "Motor Insurance", "[class*=item_product]")
        await asyncio.sleep(3)
        print("3. after motor click:", page.url[:90])

        # product-list: hover card, click Get quote BUTTON
        info = await page.evaluate("""(() => {
            const cards = Array.from(document.querySelectorAll('mat-card, .card'));
            const out = [];
            cards.forEach((c, i) => {
                const t = (c.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
                out.push({i, t});
            });
            return out;
        })()""")
        print("4. cards:", json.dumps(info, ensure_ascii=False)[:300])
        ok = await page.evaluate("""(() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const hit = btns.find(e => (e.textContent || '').includes('Get quote'));
            if (hit) { hit.click(); return true; }
            return false;
        })()""")
        print("   get-quote JS click:", ok)
        await asyncio.sleep(4)
        print("5. url:", page.url[:100])

        # confirm modal if present ("information will be lost")
        modal_ok = await page.evaluate("""(() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const hit = btns.find(e => (e.textContent || '').trim() === 'Ok');
            if (hit) { hit.click(); return true; }
            return false;
        })()""")
        if modal_ok:
            print("   confirm modal Ok clicked")
            await asyncio.sleep(3)
            print("   url:", page.url[:100])

        # NVIC dialog if present
        nvic = await page.evaluate("document.getElementById('vehicle-NVIC-dialog') ? true : false")
        if nvic:
            sel = await page.evaluate("""(() => {
                const btns = Array.from(document.querySelectorAll('#vehicle-NVIC-dialog button'));
                const hit = btns.find(e => (e.textContent || '').includes('Select'));
                if (hit) { hit.click(); return true; }
                return false;
            })()""")
            print("   NVIC dialog Select:", sel)
            await asyncio.sleep(2.5)

        # --- Step 1 fill via FillEngine ---
        has_condition = await page.evaluate("document.getElementById('condition') ? true : false")
        if not has_condition:
            print("6. NOT on quotation_details — abort (url:", page.url[:80], ")")
            return
        print("6. ON quotation_details ✅")

        from src.fill.engine import FillEngine
        from src.portal.formspec import MotorPrivateCarSpec
        from gears_live_adapter import GearsPageAdapter
        spec = MotorPrivateCarSpec.from_yaml_file("/home/antkk/InsureDesk/src/portal/forms/motor_private_car.yaml")
        engine = FillEngine()
        adapter = GearsPageAdapter(page)

        schema = spec.live_schema("quotation_details")
        result = await engine.fill_section(adapter, schema, STEP1_DATA)
        print("\n7. quotation_details fill:")
        for fr in result.fields:
            print(f"   {'✅' if fr.success else '❌'} {fr.field:20s} {(fr.message or fr.error or '')[:70]}")

        # verify key fields landed
        v = await page.evaluate("""(() => {
            const g = id => { const el = document.getElementById(id); return el ? el.value : 'MISSING'; };
            return {condition: g('condition'), vehicleNumber: g('vehicleNumber'), idNumber: g('idNumber'), place: g('placeOfUse')};
        })()""")
        print("   verify:", json.dumps(v, ensure_ascii=False))

        # --- Continue → Details ---
        await js_click_text(page, "Continue")
        await asyncio.sleep(4)
        has_proposal = await page.evaluate("document.getElementById('proposalTitle') ? true : false")
        print("8. on Details:", has_proposal, "| url:", page.url[:80])

        # quick state dump
        if has_proposal:
            auto = await page.evaluate("""(() => {
                const g = id => { const el = document.getElementById(id); return el ? el.value : 'MISSING'; };
                return {title: g('proposalTitle'), name: g('proposalFullName'), postal: g('proposalPostalCode')};
            })()""")
            print("   details auto state:", json.dumps(auto, ensure_ascii=False))


asyncio.run(main())
