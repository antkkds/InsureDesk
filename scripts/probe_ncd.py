"""Probe NCD check failure on quote d4bd452d (SJT4705).

Goal: understand ENQ077 (NCD percentage has been reset) — capture the NCD
enquiry request/response and the form's NCD field state.
"""
import asyncio
import json

from playwright.async_api import async_playwright

CDP = "http://127.0.0.1:9333"
QUOTE_URL = ("https://gears-my.greateasterngeneral.com/MY/AgencySales/"
             "quotations/PMOT/VPC/d4bd452d-2a21-4e92-b18a-ec4c3255a72d/detail")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = await ctx.new_page()
        captured = {}

        async def on_request(req):
            u = req.url
            if any(k in u.lower() for k in ("ncd", "claim", "enquiry", "discount")):
                try:
                    captured[req.method + " " + u[-80:]] = (req.post_data or "")[:800]
                except Exception:
                    pass

        async def on_response(resp):
            u = resp.url
            if any(k in u.lower() for k in ("ncd", "claim", "enquiry", "discount")):
                try:
                    captured["RESP " + u[-80:]] = (await resp.text())[:800]
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)
        await page.goto(QUOTE_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(18000)

        # scroll to reveal NCD area
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2500)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(800)

        # NCD field state + errors
        state = await page.evaluate("""() => {
          const els = {};
          for (const id of ['ncdPercentage','ncd','number_Claims','check-ncd','checkNCD']) {
            const el = document.getElementById(id);
            if (el) els[id] = {value: el.value, disabled: el.disabled, tag: el.tagName};
          }
          // find inputs with ncd in id
          const all = Array.from(document.querySelectorAll('input'))
            .filter(i => /ncd/i.test(i.id))
            .map(i => ({id: i.id, value: i.value, disabled: i.disabled}));
          const errs = Array.from(document.querySelectorAll('.errorMessage, .mat-error'))
            .map(e => (e.innerText||'').trim()).filter(Boolean).slice(0, 8);
          const overlay = document.querySelector('.cdk-overlay-container');
          const ob = overlay ? Array.from(overlay.querySelectorAll('button')).map(b => (b.innerText||'').trim()).filter(Boolean) : [];
          return {els, all, errs, overlayBtns: ob.slice(0, 10)};
        }""")
        print("STATE:", json.dumps(state, indent=1))

        # click check NCD again to capture the request
        clicked = await page.evaluate("""() => {
          const b = document.getElementById('check-ncd') ||
                    document.getElementById('checkNCD') ||
                    Array.from(document.querySelectorAll('button')).find(b => /Check NCD/.test(b.innerText||''));
          if (b) { b.click(); return true; }
          return false;
        }""")
        print("clicked Check NCD:", clicked)
        await page.wait_for_timeout(6000)
        print("=== CAPTURED ===")
        for k, v in captured.items():
            print(k, "→", v[:400])
        await browser.close()


asyncio.run(main())
