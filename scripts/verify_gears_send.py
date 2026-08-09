"""Verify GearsQuoteSender with a real quote (already sent once — checks repeat behaviour)."""
import asyncio
import json
import sys

from playwright.async_api import async_playwright

sys.path.insert(0, "/home/antkk/InsureDesk")
from src.quote.gears_send import GearsQuoteSender

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

        sender = GearsQuoteSender(page)
        outcome = await sender.send_application(expect_email="fionn.liang@gmail.com")
        print("=== SEND OUTCOME ===")
        print(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=1))
        print("SEND OK:", outcome.ok)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
