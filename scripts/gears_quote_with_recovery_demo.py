"""Demo: run a GEARS quote step with session-expiry auto-recovery.

Shows the intended integration pattern for the quote pipeline:
    ensure_gears_session()          once at task start
    with_session_recovery(...)      wrap EVERY long-running step

If the GEARS session dies mid-step (forcelogout / token expiry), the guard
re-logins via GEGLink SSO and re-runs the step — the task continues instead
of dying.

Run:  python3 gears_quote_with_recovery_demo.py
"""
import asyncio
import sys

from playwright.async_api import async_playwright

from gears_session_guard import (
    CDP,
    ensure_gears_session,
    with_session_recovery,
    session_health,
)

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
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
