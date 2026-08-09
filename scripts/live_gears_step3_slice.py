"""LIVE trial run v2: FillEngine fills Step 3 (sum_insured) with fixed selectors
(stable add-on-btn ids) + GearsPageAdapter (:has-text resolver). No Continue."""
import asyncio, json, sys
sys.path.insert(0, "/home/antkk/InsureDesk")
from playwright.async_api import async_playwright
sys.path.insert(0, "/home/antkk/InsureDesk/scripts")
from gears_live_adapter import GearsPageAdapter

DATA = {
    "courtesy_car_plan": "CART 21 days-MYR200/day",
    "icca_plan": "ICCA PLAN-A:7 days-MYR 75/day",
    "addon_strike_riot": True,
    "addon_passenger_liability": True,
    "addon_windscreen": True,
    "windscreen_sum_insured": "5000",
    "addon_thailand": True,
    "addon_ncd_relief": False,
    "addon_passenger_liability_2": False,
    "addon_special_perils": True,
    "intermediary_decl_1": True,
    "intermediary_decl_2": True,
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
            print("NO PAGE"); return
        if not await page.evaluate("document.getElementById('select_plan_0') ? true : false"):
            print("NOT ON STEP 3 (select_plan_0 missing)"); return
        print("ON STEP 3 ✅ (quote:", page.url.split("/")[-2], ")")

        from src.fill.engine import FillEngine
        from src.portal.formspec import MotorPrivateCarSpec
        spec = MotorPrivateCarSpec.from_yaml_file("/home/antkk/InsureDesk/src/portal/forms/motor_private_car.yaml")
        engine = FillEngine()
        adapter = GearsPageAdapter(page)

        print("\n=== sum_insured === (FillEngine production path)")
        schema = spec.live_schema("sum_insured")
        result = await engine.fill_section(adapter, schema, DATA)
        for fr in result.fields:
            print(f"  {'✅' if fr.success else '❌'} {fr.field:24s} {(fr.message or fr.error or '')[:90]}")

        # Verify real DOM state
        await asyncio.sleep(1.5)
        print("\n=== VERIFY DOM ===")
        txt_checks = {
            "courtesy_car_plan": "#select_plan_0",
            "icca_plan": "#select_plan_1",
            "windscreen_sum_insured": "#sumInsured_4",
        }
        for name, sel in txt_checks.items():
            v = await page.evaluate(f"(() => {{ const el = document.querySelector({sel!r}); return el ? el.value : 'MISSING'; }})()")
            print(f"  {name:24s} = {v!r}")

        cb_checks = {
            "addon_strike_riot": "#add-on-btn-2-input",
            "addon_passenger_liability": "#add-on-btn-3-input",
            "addon_windscreen": "#add-on-btn-4-input",
            "addon_thailand": "#add-on-btn-5-input",
            "addon_ncd_relief": "#add-on-btn-6-input",
            "addon_passenger_liability_2": "#add-on-btn-7-input",
            "addon_special_perils": "#add-on-btn-10-input",
            "intermediary_decl_1": 'mat-checkbox:has-text("intermediary for this application") input[type=checkbox]',
            "intermediary_decl_2": 'mat-checkbox:has-text("NRIC or passport was verified") input[type=checkbox]',
        }
        for name, sel in cb_checks.items():
            checked = await adapter.is_checked(sel)
            found = await adapter.wait_for_selector(sel, timeout=2000)
            print(f"  {name:24s} found={found} checked={checked}")

        invalid = await page.evaluate("""(() => {
            const out = [];
            document.querySelectorAll('.ng-invalid').forEach(el => {
                const id = el.id || el.tagName;
                if (id && !out.includes(id)) out.push(id);
            });
            return out.slice(0, 15);
        })()""")
        print("\n  ng-invalid fields:", json.dumps(invalid))


asyncio.run(main())
