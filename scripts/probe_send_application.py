"""Dump send dialog raw HTML."""
import asyncio

from playwright.async_api import async_playwright

CDP = "http://127.0.0.1:9333"
QUOTE_URL = ("https://gears-my.greateasterngeneral.com/MY/AgencySales/"
             "quotations/PMOT/VPC/2eed392c-0e6b-472b-822d-70627e2f8153/detail")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "gears-my" in pg.url and "quotations" in pg.url:
                page = pg
                break
        if page is None:
            page = ctx.pages[0]

        await page.goto(QUOTE_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(22000)
        await page.evaluate("() => document.getElementById('send-application').click()")
        await page.wait_for_timeout(4000)

        html = await page.evaluate(
            "() => { const o = document.querySelector('.cdk-overlay-container');"
            " return o ? o.innerHTML.slice(0, 5000) : '(none)' }"
        )
        print(html)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
