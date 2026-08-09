"""FULL fresh re-run: new quote TEST 123 → Step 1 → Details (all manual vehicle
fields) → check-market-value(0) → Continue(LOADING, expected fail) → manual
50000 → Continue → Step 3. Mirrors the FIRST successful run exactly."""
import asyncio, json, sys, time
sys.path.insert(0, "/home/antkk/InsureDesk")
sys.path.insert(0, "/home/antkk/InsureDesk/scripts")
from playwright.async_api import async_playwright

STEP1 = {
    "applicant_type": "individual",
    "condition": "REGISTERED",
    "id_type": "NRIC",
    "id_number": "881212145678",
    "vehicle_number": "TEST 123",
    "place": "KUALA LUMPUR",
}
DETAILS = {
    "salutation": "Mr", "fullname": "Fionn Liang", "gender": "M",
    "marital_status": "Single", "years_driving_exp": "5",
    "mobile": "0123456789", "email": "fionn.liang@gmail.com", "pds_consent": True,
    "postcode": "50000", "state": "KUALA LUMPUR", "address1": "12, Jalan Merdeka",
    "body_type": "SEDAN", "seating_capacity": "5",
    "safety_feature": "ABS & Airbags (more than 2)", "hire_purchase": "N",
}
VEH_EXTRA = {
    "vehicle_indicator": "LOCAL MANUFACTURE",
    "coverage_type": "COMPREHENSIVE",
    "chassis_no": "JTNB22HK203000001",
    "engine_no": "2ZR1234567",
    "engine_capacity": "1500",
    "make": "TOYOTA",
    "year_manufacture": "2024",
}


def log(msg): print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


async def js_click(page, text, tag="button"):
    return await page.evaluate(f"""(() => {{
        const els = Array.from(document.querySelectorAll('{tag}'));
        const hit = els.find(e => (e.textContent || '').trim().includes({text!r}));
        if (hit) {{ hit.click(); return true; }}
        return false;
    }})()""")


async def set_auto(page, el_id, value, opt_text):
    await page.evaluate(f"""(() => {{
        const el = document.getElementById({el_id!r});
        if (!el) return 'missing';
        el.removeAttribute('disabled');
        el.focus();
        el.value = {value!r};
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
    }})()""")
    await asyncio.sleep(2.5)
    return await page.evaluate(f"""(() => {{
        const opts = Array.from(document.querySelectorAll('mat-option'));
        const hit = opts.find(o => (o.textContent || '').includes({opt_text!r}));
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
            print("NO TAB"); return

        # dashboard → New
        await page.goto("https://gears-my.greateasterngeneral.com/MY/AgencySales/quotations/dashboard")
        await asyncio.sleep(4)
        await js_click(page, "New")
        await asyncio.sleep(4)
        log("1. introduce: " + page.url[:80])

        await js_click(page, "Motor Insurance", "[class*=item_product]")
        await asyncio.sleep(3)
        log("2. product-list: " + page.url[:90])
        await page.evaluate("""(() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const hit = btns.find(e => (e.textContent || '').includes('Get quote'));
            if (hit) { hit.click(); return true; }
            return false;
        })()""")
        await asyncio.sleep(5)
        log("3. after get-quote: " + page.url[:90])

        # confirm modal / NVIC
        await js_click(page, "Ok")
        await asyncio.sleep(3)
        nvic = await page.evaluate("document.getElementById('vehicle-NVIC-dialog') ? true : false")
        if nvic:
            await page.evaluate("""(() => {
                const btns = Array.from(document.querySelectorAll('#vehicle-NVIC-dialog button'));
                const hit = btns.find(e => (e.textContent || '').includes('Select'));
                if (hit) hit.click();
            })()""")
            await asyncio.sleep(2.5)
        has_cond = await page.evaluate("document.getElementById('condition') ? true : false")
        log(f"4. on quotation_details: {has_cond} | {page.url[:80]}")

        # Step 1 fill
        from src.fill.engine import FillEngine
        from src.portal.formspec import MotorPrivateCarSpec
        from gears_live_adapter import GearsPageAdapter
        spec = MotorPrivateCarSpec.from_yaml_file("/home/antkk/InsureDesk/src/portal/forms/motor_private_car.yaml")
        engine = FillEngine()
        adapter = GearsPageAdapter(page)
        r = await engine.fill_section(adapter, spec.live_schema("quotation_details"), STEP1)
        ok = sum(1 for f in r.fields if f.success)
        log(f"5. Step1 fill {ok}/{len(r.fields)}")
        await js_click(page, "Continue")
        await asyncio.sleep(5)
        has_prop = await page.evaluate("document.getElementById('proposalTitle') ? true : false")
        log(f"6. on Details: {has_prop}")

        # Details sections
        for sec in ["owner", "address", "vehicle"]:
            r = await engine.fill_section(adapter, spec.live_schema(sec), DETAILS)
            ok = sum(1 for f in r.fields if f.success)
            bad = [f.field for f in r.fields if not f.success and "Skipped" not in (f.message or "")]
            log(f"7. {sec} fill {ok}/{len(r.fields)} bad={bad}")

        # radio fix
        await page.evaluate("document.querySelector(\"input[name='radioBasic'][value='M']\").click()")
        await asyncio.sleep(0.3)
        await page.evaluate("document.querySelector(\"input[name='radioBasic'][value='N']\").click()")
        await asyncio.sleep(0.3)
        await page.evaluate("document.querySelector(\"input[name='radioBasic'][value='M']\").click()")
        await asyncio.sleep(0.3)
        await page.evaluate("document.querySelector(\"input[name='radioBasic'][value='N']\").click()")
        await asyncio.sleep(0.8)
        log("8. radio fix done")

        # manual vehicle fields
        r = await engine.fill_section(adapter, spec.live_schema("vehicle"), VEH_EXTRA)
        bad = [f.field for f in r.fields if not f.success and "Skipped" not in (f.message or "")]
        log(f"9. vehicle extra fill bad={bad}")

        # model autocomplete (after make)
        await set_auto(page, "vehicleModel", "TOYOTA ALTIS", "ALTIS")
        log("10. model set")

        # engine capacity JS
        await page.evaluate("""(() => {
            const el = document.getElementById('engineCapacity');
            if (!el) return;
            el.removeAttribute('disabled'); el.focus();
            el.value = '1500';
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true})); el.blur();
        })()""")
        await asyncio.sleep(1)
        # dates (future)
        for sid, val in [("start-date", "10 Aug 2026"), ("end-date", "09 Aug 2027")]:
            await page.evaluate(f"""(() => {{
                const el = document.getElementById({sid!r});
                if (!el) return;
                el.focus(); el.value = {val!r};
                el.dispatchEvent(new Event('input', {{bubbles:true}}));
                el.dispatchEvent(new Event('change', {{bubbles:true}})); el.blur();
            }})()""")
            await asyncio.sleep(1)
        # claims enable (auto '0'), anti-theft, garage
        await page.evaluate("(() => { const el = document.getElementById('number_Claims'); if (el) el.removeAttribute('disabled'); })()")
        await asyncio.sleep(1)
        await set_auto(page, "antiTheftDevice", "W/O Mech - No Alarm", "No Alarm")
        await set_auto(page, "garage", "Locked Garage", "Locked Garage")
        log("11. vehicle manual fields done")

        # market value manual
        await page.evaluate("""(() => {
            const el = document.getElementById('marketValue');
            if (!el) return;
            el.removeAttribute('disabled'); el.focus();
            el.value = '50000';
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true})); el.blur();
        })()""")
        await asyncio.sleep(1.5)
        mv = await page.evaluate("document.getElementById('marketValue') ? document.getElementById('marketValue').value : '?'")
        log(f"12. marketValue={mv}")

        # PDS
        consent = await adapter.is_checked('mat-checkbox:has-text("acknowledge and declare") input[type=checkbox]')
        if consent:
            await page.evaluate("document.getElementById('emailPDSandPDPN').click()")
            await asyncio.sleep(3)
            await js_click(page, "Ok")
            await asyncio.sleep(1.5)
            log("13. PDS sent")
        else:
            log("13. PDS consent MISSING")

        # check-market-value (returns 0 for TEST123) — expected fail loop
        await page.evaluate("document.getElementById('check-market-value').click()")
        await asyncio.sleep(3)
        mv0 = await page.evaluate("document.getElementById('marketValue') ? document.getElementById('marketValue').value : '?'")
        log(f"14. check-market-value → mv={mv0}")

        # Continue #1 (marketValue=0) → expect LOADING → back to Details
        await js_click(page, "Continue")
        for i in range(10):
            await asyncio.sleep(3)
            loading = await page.evaluate("document.querySelectorAll('app-loading-indicator, [class*=loading]').length")
            if i % 2 == 0:
                log(f"15. continue#1 t={i*3}s loading={loading}")
            if loading == 0 and i > 1:
                break
        await asyncio.sleep(3)
        mv1 = await page.evaluate("document.getElementById('marketValue') ? document.getElementById('marketValue').value : 'GONE'")
        has_plan = await page.evaluate("document.getElementById('select_plan_0') ? true : false")
        log(f"16. after continue#1: step3={has_plan} mv={mv1}")

        if not has_plan:
            # manual 50000 again → Continue #2
            await page.evaluate("""(() => {
                const el = document.getElementById('marketValue');
                if (!el) return;
                el.removeAttribute('disabled'); el.focus();
                el.value = '50000';
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true})); el.blur();
            })()""")
            await asyncio.sleep(1.5)
            mv2 = await page.evaluate("document.getElementById('marketValue') ? document.getElementById('marketValue').value : '?'")
            log(f"17. re-manual mv={mv2}")
            await js_click(page, "Continue")
            for i in range(14):
                await asyncio.sleep(5)
                has_plan = await page.evaluate("document.getElementById('select_plan_0') ? true : false")
                loading = await page.evaluate("document.querySelectorAll('app-loading-indicator, [class*=loading]').length")
                if i % 2 == 0:
                    log(f"18. continue#2 t={i*5}s step3={has_plan} loading={loading}")
                if has_plan:
                    break
        log("19. FINAL step3=" + str(has_plan))
        if has_plan:
            body = await page.evaluate("document.body ? document.body.innerText.replace(/\\s+/g,' ').slice(0, 300) : ''")
            log("20. " + body[:280])


asyncio.run(main())
