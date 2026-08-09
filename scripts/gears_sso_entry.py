"""Full SSO: loginForm -> redirectJSP -> eqForm.submit() -> GEARS home."""
import asyncio, json
from playwright.async_api import async_playwright

BASE = "https://geglink.greateasterngeneral.com"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9333")
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "geglink" in pg.url:
                page = pg
                break
        await page.goto(BASE + "/geglink/agent/agent_home.html", wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        # 1. Get eqForm HTML via same-origin fetch
        html = await page.evaluate("""async () => {
            const resp = await fetch('/geglink/agent/redirectJSP.html', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'channelType=IFE'
            });
            return await resp.text();
        }""")
        # 2. Rebuild eqForm in DOM and submit (cross-origin form.submit works)
        submitted = await page.evaluate("""(html) => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const form = doc.querySelector('form[name="eqForm"]');
            if (!form) return false;
            // Append to current page
            document.body.appendChild(form);
            form.submit();
            return true;
        }""", html)
        print("EQFORM SUBMITTED:", submitted)
        await page.wait_for_timeout(12000)
        print("FINAL URL:", page.url[:130])
        text = await page.evaluate("document.body ? document.body.innerText.slice(0,400) : ''")
        print("BODY:", text.replace(chr(10), ' | ')[:300])
        await page.screenshot(path="/tmp/gears_home.png")
        await browser.close()

asyncio.run(main())
