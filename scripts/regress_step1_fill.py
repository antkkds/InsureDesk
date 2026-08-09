"""Fill quotation_details (TEST 123) → Continue → verify Details reached.
Uses FillEngine + modified GearsPageAdapter (regression check for autocomplete)."""
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
        has_cond = await page.evaluate("document.getElementById('condition') ? true : false")
        if not has_cond:
            print("NOT ON quotation_details"); return
        print("ON quotation_details ✅ quote:", page.url.split("/")[-2][:8])

        from src.fill.engine import FillEngine
        from src.portal.formspec import MotorPrivateCarSpec
        from gears_live_adapter import GearsPageAdapter
        spec = MotorPrivateCarSpec.from_yaml_file("/home/antkk/InsureDesk/src/portal/forms/motor_private_car.yaml")
        engine = FillEngine()
        adapter = GearsPageAdapter(page)

        schema = spec.live_schema("quotation_details")
        result = await engine.fill_section(adapter, schema, STEP1_DATA)
        print("\nquotation_details fill:")
        for fr in result.fields:
            print(f"  {'✅' if fr.success else '❌'} {fr.field:20s} {(fr.message or fr.error or '')[:70]}")

        v = await page.evaluate("""(() => {
            const g = id => { const el = document.getElementById(id); return el ? el.value : 'MISSING'; };
            return {condition: g('condition'), vehicleNumber: g('vehicleNumber'), idNumber: g('idNumber'), place: g('place')};
        })()""")
        print("verify:", json.dumps(v, ensure_ascii=False))

        invalid = await page.evaluate("""(() => {
            const out = [];
            document.querySelectorAll('.ng-invalid').forEach(el => {
                const id = el.id || el.tagName;
                if (id && !out.includes(id)) out.push(id);
            });
            return out.slice(0, 10);
        })()""")
        print("ng-invalid:", json.dumps(invalid))

        # Continue → Details
        await page.evaluate("""(() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const hit = btns.find(e => (e.textContent || '').trim() === 'Continue');
            if (hit) { hit.click(); return true; }
            return false;
        })()""")
        await asyncio.sleep(5)
        has_prop = await page.evaluate("document.getElementById('proposalTitle') ? true : false")
        print("\nOn Details:", has_prop, "| url:", page.url[:90])
        if has_prop:
            auto = await page.evaluate("""(() => {
                const g = id => { const el = document.getElementById(id); return el ? el.value : 'MISSING'; };
                return {title: g('proposalTitle'), vehicle: g('vehicleNumber')};
            })()""")
            print("details state:", json.dumps(auto, ensure_ascii=False))


asyncio.run(main())
