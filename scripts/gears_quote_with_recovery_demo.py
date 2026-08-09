"""Demo: run a GEARS quote step with session-expiry auto-recovery + Save + Send.

Shows the intended integration pattern for the quote pipeline:
    ensure_gears_session()          once at task start
    with_session_recovery(...)      wrap EVERY long-running step
    GearsQuoteSaver.save_as_draft() structured save with PUT-level proof
    GearsQuoteSender.send_application() structured send with POST-level proof

If the GEARS session dies mid-step (forcelogout / token expiry), the guard
re-logins via GEGLink SSO and re-runs the step — the task continues instead
of dying. Save/Send return structured outcomes (docName/version/status),
not a UI-toast guess.

Run:  python3 gears_quote_with_recovery_demo.py
"""
import asyncio
import json
import sys

from playwright.async_api import async_playwright

from gears_session_guard import (
    CDP,
    ensure_gears_session,
    with_session_recovery,
    session_health,
)

sys.path.insert(0, "/home/antkk/InsureDesk")
from src.quote.gears_save import GearsQuoteSaver
from src.quote.gears_send import GearsQuoteSender

# A saved draft quote from the verification run (TEST123 / FIONN LIANG)
QUOTE_URL = ("https://gears-my.greateasterngeneral.com/MY/AgencySales/"
             "quotations/PMOT/VPC/2eed392c-0e6b-472b-822d-70627e2f8153/detail")


async def step_open_quote(page, quote_url):
    """Task step example: open the quote and wait for it to render."""
    await page.goto(quote_url, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(8000)
    body = await page.evaluate(
        "() => document.body ? document.body.innerText.slice(0, 300) : ''"
    )
    if "LOADING" in body.upper() and "kk" not in body:
        raise RuntimeError("quote page still loading")
    print(f"  [step] quote opened: {page.url[:80]}")
    print(f"  [step] page shows: {body[:60].replace(chr(10), ' ')}")
    return True


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "gears-my" in pg.url or "geglink" in pg.url:
                page = pg
                break
        if page is None:
            page = ctx.pages[0]

        # 1. Ensure a healthy session before starting the task
        page = await ensure_gears_session(ctx, page, quote_url=QUOTE_URL)
        print(f"session OK → {page.url[:80]}")

        # 2. Run task steps, each wrapped with session recovery
        ok = await with_session_recovery(ctx, page, QUOTE_URL,
                                         step_open_quote, page, QUOTE_URL)
        print(f"step result: {ok}")
        print(f"final health: {await session_health(page)}")

        # 3. Save as draft — structured outcome (PUT-level proof)
        saver = GearsQuoteSaver(page)
        outcome = await saver.save_as_draft()
        print("=== SAVE OUTCOME ===")
        print(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=1))
        print("SAVE OK:", outcome.ok)

        # 4. Send application — structured outcome (POST-level proof).
        # quote_url makes Send self-contained: after Save the app is on the
        # dashboard, so the sender navigates back to the quote itself.
        sender = GearsQuoteSender(page)
        send_out = await sender.send_application(quote_url=QUOTE_URL)
        print("=== SEND OUTCOME ===")
        print(json.dumps(send_out.to_dict(), ensure_ascii=False, indent=1))
        print("SEND OK:", send_out.ok)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
