"""Capture market API response on d355ec1b — why no premium?"""
import asyncio
import json

from playwright.async_api import async_playwright

CDP = "http://127.0.0.1:9333"
QUOTE_URL = ("https://gears-my.greateasterngeneral.com/MY/AgencySales/"
             "quotations/PMOT/VPC/d355ec1b-3d70-4cd1-82a8-7ff1689ea623/detail")

CAP = []


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "gears-my" in pg.url:
                page = pg
                break
        if page is None:
            page = ctx.pages[0]

        async def on_resp(r):
            u = r.url
            if "market" in u or "execution-vpms" in u or "vehicle-ncd" in u:
                try:
                    b = await r.text()
                except Exception:
                    b = ""
                CAP.append((r.status, u.split("?")[0][-55:], b[:600]))

        page.on("response", on_resp)
        await page.goto(QUOTE_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(20000)
        await page.evaluate(
            """() => {
              const o = document.querySelector('.cdk-overlay-container');
              if (o) {
                const b = Array.from(o.querySelectorAll('button'))
                  .find(x => (x.innerText||'').includes('Continue') || (x.innerText||'').trim() === 'Ok');
                if (b) b.click();
              }
            }"""
        )
        await page.wait_for_timeout(1500)
        CAP.clear()
        for b in await page.locator("button:has-text('Check market value')").all():
            try:
                if await b.is_visible() and not await b.is_disabled():
                    await b.click()
                    break
            except Exception:
                pass
        await page.wait_for_timeout(8000)
        for b in await page.locator("button:has-text('Check NCD')").all():
            try:
                if await b.is_visible() and not await b.is_disabled():
                    await b.click()
                    break
            except Exception:
                pass
        await page.wait_for_timeout(6000)

        print(f"=== {len(CAP)} responses ===")
        for st, u, b in CAP:
            print(f"\n{st} {u}")
            print(f"  {b[:400]}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
