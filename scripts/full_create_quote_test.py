"""Quote 50f03605 exact-tab: Quotation Summary → Save → Send."""
import asyncio
import json
import sys

from playwright.async_api import async_playwright

sys.path.insert(0, "/home/antkk/InsureDesk")
from src.quote.gears_save import GearsQuoteSaver
from src.quote.gears_send import GearsQuoteSender

CDP = "http://127.0.0.1:9333"
QUOTE_URL = ("https://gears-my.greateasterngeneral.com/MY/AgencySales/"
             "quotations/PMOT/VPC/50f03605-584e-4bfa-97e1-7c1a9c99d7a8/detail")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]

        # find page with EXACT quote id 50f03605
        page = None
        for pg in ctx.pages:
            if "50f03605" in pg.url:
                page = pg
                break
        if page is None:
            print("no page for 50f03605 — navigating")
            page = ctx.pages[0]
            await page.goto(QUOTE_URL, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(20000)

        print(f"using page: {page.url[:110]}")
        await page.bring_to_front()
        await page.wait_for_timeout(1500)

        # Quotation Summary
        for b in await page.locator("button:has-text('Quotation Summary')").all():
            try:
                if await b.is_visible():
                    print(">>> Quotation Summary")
                    await b.click()
                    break
            except Exception:
                pass
        await page.wait_for_timeout(8000)
        body = await page.evaluate("() => document.body.innerText.slice(0, 700)")
        print(f"body: {body[:500].replace(chr(10), ' / ')}")
        referred = "Referred application" in body
        print(f"REFERRED: {referred}")

        if referred:
            print(">>> referred — cannot Send (Submit for review path)")
            await browser.close()
            return

        # Save
        saver = GearsQuoteSaver(page)
        save_out = await saver.save_as_draft()
        print("=== SAVE OUTCOME ===")
        print(json.dumps(save_out.to_dict(), ensure_ascii=False, indent=1))
        print("SAVE OK:", save_out.ok)

        # Send
        sender = GearsQuoteSender(page)
        send_out = await sender.send_application(quote_url=QUOTE_URL)
        print("=== SEND OUTCOME ===")
        print(json.dumps(send_out.to_dict(), ensure_ascii=False, indent=1))
        print("SEND OK:", send_out.ok)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
