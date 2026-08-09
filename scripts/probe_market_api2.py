"""Probe #2: capture the market POST request BODY + full response quoteModel.

Determines whether the empty market result is caused by WRONG vehicle data
being sent (e.g. forced TOYOTA/CAMRY vs real SA767M registration).
"""
import asyncio
import json

from playwright.async_api import async_playwright

CDP = "http://127.0.0.1:9333"
QUOTE_URL = ("https://gears-my.greateasterngeneral.com/MY/AgencySales/"
             "quotations/PMOT/VPC/b20ebcee-01dd-4325-b6c8-67d17fbdac7d/detail")
MARKET_URL = "https://store-my.greateasterngeneral.com/my/v1/ife/general/quotations/PMOT/VPC/market"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = await ctx.new_page()
        captured = {}

        async def on_request(req):
            if req.url.startswith(MARKET_URL) and req.method == "POST":
                try:
                    captured["req_body"] = req.post_data or ""
                except Exception:
                    captured["req_body"] = "<no post data>"

        async def on_response(resp):
            if resp.url.startswith(MARKET_URL):
                try:
                    captured["resp_body"] = await resp.text()
                except Exception:
                    captured["resp_body"] = "<no body>"

        page.on("request", on_request)
        page.on("response", on_response)
        await page.goto(QUOTE_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(18000)

        clicked = await page.evaluate(
            """() => {
              const b = document.getElementById('check-market-value');
              if (b && !b.disabled) { b.click(); return true; }
              return false;
            }"""
        )
        print("clicked:", clicked)
        await page.wait_for_timeout(7000)

        req = captured.get("req_body", "<none>")
        print("=== MARKET POST REQUEST BODY ===")
        try:
            d = json.loads(req)
            # print vehicle-relevant keys only
            def walk(o, prefix=""):
                if isinstance(o, dict):
                    for k, v in o.items():
                        if isinstance(v, (dict, list)):
                            walk(v, f"{prefix}{k}.")
                        else:
                            print(f"  {prefix}{k} = {v!r}"[:120])
            walk(d)
        except Exception:
            print(req[:1500])

        resp = captured.get("resp_body", "<none>")
        print("=== RESPONSE: result + vehicle fields ===")
        try:
            rd = json.loads(resp)
            print("result:", json.dumps(rd.get("result"))[:300])
            qm = rd.get("quoteModel", {})
            # find vehicle-ish keys
            for k, v in qm.items():
                if any(s in k.lower() for s in ("vehicle", "make", "model", "chassis", "engine", "year", "body", "nvic", "market", "sum")):
                    print(f"  {k} = {json.dumps(v)[:120]}")
        except Exception:
            print(resp[:800])
        await browser.close()


asyncio.run(main())
