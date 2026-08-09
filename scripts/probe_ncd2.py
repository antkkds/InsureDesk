"""Probe #2: full vehicle-ncd response — find ENQ077 reason + NCD result."""
import asyncio
import json

from playwright.async_api import async_playwright

CDP = "http://127.0.0.1:9333"
QUOTE_URL = ("https://gears-my.greateasterngeneral.com/MY/AgencySales/"
             "quotations/PMOT/VPC/d4bd452d-2a21-4e92-b18a-ec4c3255a72d/detail")
NCD_URL = "vehicle-ncd"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = await ctx.new_page()
        resp_body = {"data": None}

        async def on_response(resp):
            if NCD_URL in resp.url:
                try:
                    resp_body["data"] = await resp.text()
                except Exception:
                    pass

        page.on("response", on_response)
        await page.goto(QUOTE_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(15000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollTo(0, 0)")

        clicked = await page.evaluate(
            """() => {
              const b = Array.from(document.querySelectorAll('button'))
                .find(b => /Check NCD/.test(b.innerText||''));
              if (b) { b.click(); return true; }
              return false;
            }"""
        )
        print("clicked:", clicked)
        await page.wait_for_timeout(7000)

        data = resp_body["data"]
        if not data:
            print("no response captured")
            return
        try:
            d = json.loads(data)
        except Exception:
            print(data[:3000])
            return

        # search for ncd / reason / ENQ077 anywhere
        def find_keys(o, path=""):
            hits = []
            if isinstance(o, dict):
                for k, v in o.items():
                    kl = k.lower()
                    if any(s in kl for s in ("ncd", "reason", "enq", "discount", "claim", "result", "percentage", "reset")):
                        hits.append((f"{path}{k}", json.dumps(v)[:200]))
                    hits += find_keys(v, f"{path}{k}.")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    hits += find_keys(v, f"{path}[{i}].")
            return hits

        print("=== NCD-RELATED KEYS ===")
        for k, v in find_keys(d):
            print(f"  {k} = {v}")
        await browser.close()


asyncio.run(main())
