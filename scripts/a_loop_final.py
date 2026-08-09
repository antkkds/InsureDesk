"""DEFINITIVE: new TEST123 quote full flow → strict Save verification → dashboard status → Send.

Goal: determine WHY new quotes can't Send. Checks Save dialog result carefully.
"""
import asyncio
import json
import sys
import time

from playwright.async_api import async_playwright

sys.path.insert(0, "/home/antkk/InsureDesk")
from src.quote.gears_send import GearsQuoteSender

CDP = "http://127.0.0.1:9333"
DASH_URL = "https://gears-my.greateasterngeneral.com/MY/AgencySales/quotations/dashboard"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


async def pick_auto(page, field_id, target, wait=1800):
    await page.evaluate(
        """(id) => { const el = document.getElementById(id); if (el) el.click(); }""", field_id
    )
    await page.wait_for_timeout(wait)
    return await page.evaluate(
        """(t) => {
          const opts = Array.from(document.querySelectorAll('.mat-option'));
          const m = opts.find(o => (o.innerText||'').toUpperCase().includes(t.toUpperCase()));
          if (m) { m.click(); return 'ok:' + m.innerText.trim().slice(0, 30); }
          if (opts.length) { opts[0].click(); return 'first:' + opts[0].innerText.trim().slice(0, 30); }
          return 'none';
        }""",
        target,
    )


async def click_btn(page, text):
    for b in await page.locator(f"button:has-text('{text}')").all():
        try:
            if await b.is_visible():
                await b.click()
                return True
        except Exception:
            pass
    return False


async def close_overlay(page):
    await page.evaluate(
        """() => {
          const o = document.querySelector('.cdk-overlay-container');
          if (o) {
            const btns = Array.from(o.querySelectorAll('button'));
            const b = btns.find(x =>
              (x.innerText||'').includes('Continue with application') ||
              (x.innerText||'').trim() === 'Ok');
            if (b) b.click();
          }
        }"""
    )
    await page.wait_for_timeout(1000)


async def main():
    t0 = time.monotonic()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = await ctx.new_page()
        await page.goto(DASH_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(12000)

        # CREATE
        await page.evaluate("() => { const b = document.getElementById('add-button'); if (b) b.click(); }")
        await page.wait_for_timeout(6000)
        for el in await page.locator("text=Motor Insurance").all():
            try:
                if await el.is_visible():
                    await el.click()
                    break
            except Exception:
                pass
        await page.wait_for_timeout(6000)
        for el in await page.locator("text=Private Motor Insurance").all():
            try:
                if await el.is_visible():
                    await el.click()
                    break
            except Exception:
                pass
        await page.wait_for_timeout(3000)
        for b in await page.locator("button:has-text('Get quote')").all():
            try:
                if await b.is_visible():
                    await b.click()
                    break
            except Exception:
                pass
        await page.wait_for_timeout(18000)
        quote_url = page.url
        log(f"CREATE: {quote_url}")
        for i in range(6):
            if await page.evaluate("() => !!document.getElementById('idNumber')"):
                break
            await page.wait_for_timeout(3000)

        # STEP 1
        await page.locator("#idNumber").fill("881212145678")
        await page.locator("#idNumber").blur()
        await page.wait_for_timeout(2500)
        await pick_auto(page, "idType", "NRIC")
        await page.locator("#vehicleNumber").fill("TEST123")
        await page.locator("#vehicleNumber").blur()
        await page.wait_for_timeout(3000)
        await pick_auto(page, "place", "KUALA LUMPUR")
        await page.evaluate(
            """() => { const el = document.getElementById('condition'); el.disabled = false; el.click(); }"""
        )
        await page.wait_for_timeout(2000)
        await page.evaluate(
            """() => {
              const opts = Array.from(document.querySelectorAll('.mat-option'));
              const r = opts.find(o => /REGISTERED/.test(o.innerText||'') && !/NEW/.test(o.innerText||''));
              if (r) r.click(); else if (opts.length) opts[0].click();
            }"""
        )
        await page.wait_for_timeout(1000)
        await click_btn(page, "Continue")
        await page.wait_for_timeout(8000)
        log("STEP1 done")

        # STEP 2
        # scroll to bottom to trigger lazy render of lower fields, then back up
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3000)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(1000)
        log("STEP2 fill start")
        for fid, val in [("proposalFullName", "Fionn Liang"), ("year_experience", "10"),
                         ("proposalMobileNumber", "0123456789"),
                         ("proposalEmail", "fionn.liang@gmail.com"),
                         ("proposalPostalCode", "50000"),
                         ("proposalAddressLine1", "12, Jalan Merdeka"),
                         ("chassisNumber", "PN153BK3006001289"),
                         ("engineNumber", "2AZ3028068"),
                         ("engineCapacity", "2362")]:
            el = page.locator(f"#{fid}")
            await el.fill(val)
            await el.blur()
            await page.wait_for_timeout(300)
        for fid, target in [("proposalTitle", "Mr"), ("vehicleBodyType", "SEDAN"),
                            ("antiTheftDevice", "No Alarm"), ("safetyFeature", "ABS & Airbags (more than 2)"),
                            ("garage", "Locked Garage"), ("proposalMarital", "Single"),
                            ("proposalStateApplicant", "KUALA LUMPUR"),
                            ("vehicleIndicator", "LOCAL MANUFACTURE"),
                            ("vehicleCoverageType", "COMPREHENSIVE")]:
            await pick_auto(page, fid, target)
        # hire purchase company — original working approach (pick_auto, no fill)
        hp_pick = "field-missing"
        for _try in range(3):
            exists = await page.evaluate(
                "() => !!document.getElementById('hirePurchaseCompany')"
            )
            if not exists:
                if _try == 0:
                    ctx = await page.evaluate(
                        """() => {
                          const body = document.body.innerText;
                          const i = body.indexOf('hire purchase');
                          return {
                            has_text: i >= 0,
                            snippet: i >= 0 ? body.slice(i - 50, i + 200).replace(/\\n/g, ' | ') : '',
                            has_field_any: !!document.querySelector('[id*=irePurchase]'),
                            scrollY: window.scrollY,
                            h: document.body.scrollHeight,
                          };
                        }"""
                    )
                    log(f"HP diag: {json.dumps(ctx, ensure_ascii=False)[:250]}")
                await page.wait_for_timeout(2000)
                continue
            hp_pick = await pick_auto(page, "hirePurchaseCompany", "PUBLIC BANK")
            if hp_pick.startswith(("ok:", "first:")):
                break
            await page.wait_for_timeout(1500)
        log(f"hirePurchaseCompany: {hp_pick}")
        await page.locator("#seatingCapacity").fill("5")
        await page.locator("#seatingCapacity").blur()
        await page.locator("#yearManufacture").fill("2024")
        await page.locator("#yearManufacture").blur()
        await pick_auto(page, "vehicleMake", "TOYOTA")
        await pick_auto(page, "vehicleModel", "CAMRY")
        await pick_auto(page, "number_Claims", "0")
        # dates JS
        for fid, val in [("start-date", "10 Sep 2026"), ("end-date", "09 Sep 2027")]:
            await page.evaluate(
                """(d) => {
                  const el = document.getElementById(d.id);
                  if (!el) return 'missing';
                  const setter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, 'value').set;
                  setter.call(el, d.v);
                  el.dispatchEvent(new Event('input', {bubbles: true}));
                  el.dispatchEvent(new Event('change', {bubbles: true}));
                  return el.value;
                }""",
                {"id": fid, "v": val},
            )
        # hire purchase question (btn_0/btn_1): answer NO (btn_1) like 2eed392c
        # (Send-OK quote has btn_1 checked → no company field required, passes)
        hp_ans = await page.evaluate(
            """() => {
              const b = document.getElementById('btn_1');
              if (b) { if (!b.checked) b.click(); return 'No selected'; }
              return 'btn_1 missing';
            }"""
        )
        log(f"hire purchase answer: {hp_ans}")
        await page.wait_for_timeout(1000)
        # declaration checkbox
        await page.evaluate(
            """() => {
              const c = document.getElementById('mat-checkbox-1-input');
              if (c && !c.checked) { const l = c.closest('label'); if (l) l.click(); }
            }"""
        )
        await page.wait_for_timeout(1000)
        # PDS email
        for b in await page.locator("#emailPDSandPDPN").all():
            try:
                if await b.is_visible() and not await b.is_disabled():
                    await b.click()
                    break
            except Exception:
                pass
        await page.wait_for_timeout(4000)
        await page.evaluate(
            """() => {
              const o = document.querySelector('.cdk-overlay-container');
              if (o) {
                const b = Array.from(o.querySelectorAll('button'))
                  .find(x => (x.innerText||'').trim() === 'Ok');
                if (b) b.click();
              }
            }"""
        )
        await page.wait_for_timeout(1500)
        # Check NCD
        for b in await page.locator("button:has-text('Check NCD')").all():
            try:
                if await b.is_visible() and not await b.is_disabled():
                    await b.click()
                    break
            except Exception:
                pass
        await page.wait_for_timeout(4000)
        await page.evaluate(
            """() => {
              const o = document.querySelector('.cdk-overlay-container');
              if (o) {
                const b = Array.from(o.querySelectorAll('button'))
                  .find(x => (x.innerText||'').trim() === 'Ok');
                if (b) b.click();
              }
            }"""
        )
        await page.wait_for_timeout(1500)
        # marketValue JS
        await page.evaluate(
            """() => {
              const el = document.getElementById('marketValue');
              if (!el) return;
              const setter = Object.getOwnPropertyDescriptor(
                HTMLInputElement.prototype, 'value').set;
              setter.call(el, '50000');
              el.dispatchEvent(new Event('input', {bubbles: true}));
              el.dispatchEvent(new Event('change', {bubbles: true}));
            }"""
        )
        await page.wait_for_timeout(1500)
        # Continue → step 3 (may need 2 clicks)
        await click_btn(page, "Continue")
        await page.wait_for_timeout(6000)
        await close_overlay(page)
        has_si = await page.evaluate("() => !!document.getElementById('desiredSI')")
        if not has_si:
            await click_btn(page, "Continue")
            await page.wait_for_timeout(6000)
            await close_overlay(page)
            has_si = await page.evaluate("() => !!document.getElementById('desiredSI')")
        log(f"STEP2→3 has_desiredSI={has_si}")
        if not has_si:
            errs = await page.evaluate(
                """() => Array.from(document.querySelectorAll('.errorMessage, .mat-error'))
                  .map(e => (e.innerText||'').trim().slice(0, 60)).filter(Boolean)"""
            )
            log(f"STUCK errors: {errs}")
            await browser.close()
            return

        # STEP 3: add-ons + declarations
        for pid, target in [("select_plan_0", "21 days-MYR200"), ("select_plan_1", "ICCA PLAN-A")]:
            await pick_auto(page, pid, target)
        for cid in ["add-on-btn-2-input", "add-on-btn-3-input", "add-on-btn-4-input",
                    "add-on-btn-5-input", "add-on-btn-6-input", "add-on-btn-7-input",
                    "add-on-btn-8-input", "add-on-btn-10-input"]:
            await page.evaluate(
                """(id) => {
                  const c = document.getElementById(id);
                  if (c && !c.checked) { const l = c.closest('label'); if (l) l.click(); }
                }""",
                cid,
            )
        si = page.locator("#sumInsured_4")
        if await si.count() and await si.is_visible() and not await si.is_disabled():
            await si.fill("5000")
        for cid in ("mat-checkbox-4-input", "mat-checkbox-5-input"):
            await page.evaluate(
                """(id) => {
                  const c = document.getElementById(id);
                  if (c && !c.checked) { const l = c.closest('label'); if (l) l.click(); }
                }""",
                cid,
            )
        await page.wait_for_timeout(1500)
        log("STEP3 done")

        # SUMMARY
        await click_btn(page, "Quotation Summary")
        await page.wait_for_timeout(8000)
        body = await page.evaluate("() => document.body.innerText.slice(0, 600)")
        log(f"SUMMARY: {'Referred' if 'Referred application' in body else 'NOT referred'}")

        # SAVE — strict: click Save as draft, handle "update Details?" Yes,
        # confirm dialog, capture PUT
        await close_overlay(page)
        await page.evaluate(
            """() => {
              const btns = Array.from(document.querySelectorAll('button'))
                .filter(b => b.offsetParent && (b.innerText||'').includes('Save as draft'));
              if (btns.length) btns[0].click();
            }"""
        )
        await page.wait_for_timeout(4000)
        dlg = await page.evaluate(
            "() => { const o = document.querySelector('.cdk-overlay-container');"
            " return o ? o.innerText.slice(0, 400) : '(none)' }"
        )
        log(f"save dialog: {dlg[:250]}")
        # handle "Are you going to update the Details section?" → Yes
        if "update the Details section" in dlg or "update the Details" in dlg:
            yes_done = await page.evaluate(
                """() => {
                  const o = document.querySelector('.cdk-overlay-container');
                  if (!o) return false;
                  const b = Array.from(o.querySelectorAll('button'))
                    .find(x => (x.innerText||'').trim() === 'Yes');
                  if (b) { b.click(); return true; }
                  return false;
                }"""
            )
            log(f"update Details Yes: {yes_done}")
            await page.wait_for_timeout(2500)
        # confirm Save
        await page.evaluate(
            """() => {
              const o = document.querySelector('.cdk-overlay-container');
              if (o) {
                const b = Array.from(o.querySelectorAll('button'))
                  .find(x => (x.innerText||'').trim() === 'Save');
                if (b) b.click();
              }
            }"""
        )
        await page.wait_for_timeout(9000)
        log(f"after save url: {page.url[:100]}")

        # dashboard status check
        await page.goto(DASH_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(15000)
        await page.evaluate(
            """() => {
              const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
              let n;
              while (n = walker.nextNode()) {
                if ((n.textContent||'').trim() === 'Draft quotation') {
                  n.parentElement.click(); return;
                }
              }
            }"""
        )
        await page.wait_for_timeout(6000)
        rows = await page.evaluate(
            """() => Array.from(document.querySelectorAll('tr'))
              .map(t => (t.innerText||'').trim().replace(/\\n/g, ' | '))
              .filter(x => x && !x.startsWith('Policy number')).slice(0, 6)"""
        )
        log("dashboard rows:")
        for r in rows:
            log(f"  {r[:180]}")

        # SEND
        log(">>> SEND")
        sender = GearsQuoteSender(page)
        outcome = await sender.send_application(quote_url=quote_url)
        log(json.dumps(outcome.to_dict(), ensure_ascii=False))
        log(f"ELAPSED {time.monotonic()-t0:.0f}s")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
