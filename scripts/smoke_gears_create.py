"""Smoke: GearsQuoteCreator.create_quote() → CREATED + step1 fill."""
import asyncio
import json
import sys

from playwright.async_api import async_playwright

sys.path.insert(0, "/home/antkk/InsureDesk")
from src.quote.gears_create import GearsQuoteCreator

CDP = "http://127.0.0.1:9333"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = await ctx.new_page()

        creator = GearsQuoteCreator(page)
        out = await creator.create_quote()
        print("CREATE:", json.dumps(out.to_dict(), ensure_ascii=False))
        if out.status == "CREATED":
            out1 = await creator.fill_step1()
            print("STEP1:", json.dumps(out1.to_dict(), ensure_ascii=False))
        await browser.close()


asyncio.run(main())
