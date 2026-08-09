"""Probe the GEARS market-value API on a real-vehicle quote.

Goal: find out why #check-market-value returns empty market data even for a
registered plate (SA767M). Captures the request URL + response body.
"""
import asyncio
import json

from playwright.async_api import async_playwright

CDP = "http://127.0.0.1:9333"
QUOTE_URL = ("https://gears-my.greateasterngeneral.com/MY/AgencySales/"
             "quotations/PMOT/VPC/b20ebcee-01dd-4325-b6c8-67d17fbdac7d/detail")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = await ctx.new_page()
        captured = []

        async def on_response(resp):
            url = resp.url
            if any(k in url.lower() for k in ("market", "nvic", "valu", "motorvehicle")):
                try:
                    body = await resp.text()
                except Exception:
                    body = "<no body>"
                captured.append({
                    "url": url[:160],
                    "status": resp.status,
                    "method": resp.request.method,
                    "body": body[:400],
                })

        page.on("response", on_response)
        await page.goto(QUOTE_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(20000)
        print("URL:", page.url[:100])

        # navigate to Details step if not there
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(1000)

        # what's on this page?
        has_mv = await page.evaluate(
            "() => !!document.getElementById('marketValue')"
        )
        print("has marketValue field:", has_mv)
        if not has_mv:
            # try clicking Quotation Details / Details nav
            for txt in ("Details", "Quotation Details"):
                for b in await page.locator(f"button:has-text('{txt}')").all():
                    try:
                        if await b.is_visible():
                            await b.click()
                            await page.wait_for_timeout(6000)
                            break
                    except Exception:
                        pass
        has_mv = await page.evaluate(
            "() => !!document.getElementById('marketValue')"
        )
        print("after nav, has marketValue:", has_mv)

        # click check-market-value
        clicked = await page.evaluate(
            """() => {
              const b = document.getElementById('check-market-value');
              if (b && !b.disabled) { b.click(); return true; }
              return false;
            }"""
        )
        print("clicked check-market-value:", clicked)
        await page.wait_for_timeout(6000)

        mv = await page.evaluate(
            """() => {
              const el = document.getElementById('marketValue');
              const info = {
                value: el ? el.value : null,
                disabled: el ? el.disabled : null,
                placeholder: el ? el.placeholder : null,
              };
              // also read all inputs with 'market' in id/name
              const all = Array.from(document.querySelectorAll('input'))
                .filter(i => /market|nvic/i.test(i.id + ' ' + (i.name||'')))
                .map(i => ({id: i.id, name: i.name, value: i.value, disabled: i.disabled}));
              return {info, all};
            }"""
        )
        print("MARKET FIELD:", json.dumps(mv, indent=1))
        print("CAPTURED REQUESTS:", len(captured))
        for c in captured:
            print(json.dumps(c, indent=1)[:600])
        await browser.close()


asyncio.run(main())
