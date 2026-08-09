"""Wait for ChatGPT reply and extract text."""
import asyncio, sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://127.0.0.1:9230')
        ctx = browser.contexts[0]
        target = None
        for page in ctx.pages:
            if '6a6b6ba6' in page.url:
                target = page
                break
        if not target:
            print("ERROR: conversation tab not found")
            await browser.close()
            return

        # Wait for generation to finish (stop button disappears)
        for i in range(60):
            state = await target.evaluate("""() => {
                const stopBtn = document.querySelector('button[data-testid="stop-button"]');
                return !!stopBtn;
            }""")
            if not state:
                print(f"Generation done after {i*5}s")
                break
            await target.wait_for_timeout(5000)
        else:
            print("TIMEOUT waiting for generation")

        await target.wait_for_timeout(2000)

        # Extract all assistant messages
        text = await target.evaluate("""() => {
            const msgs = document.querySelectorAll('div[data-message-author-role="assistant"]');
            const out = [];
            for (const m of msgs) {
                out.push(m.innerText);
            }
            return out;
        }""")
        print(f"Total assistant messages: {len(text)}")
        if text:
            print("=== LAST REPLY ===")
            print(text[-1][:6000])
        await browser.close()

asyncio.run(main())
