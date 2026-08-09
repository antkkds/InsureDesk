"""Test portal entries: direct nav houseQuote vs click Fire Quotation link."""
import asyncio, sys, json
sys.path.insert(0, "/home/antkk/InsureDesk")
from src.browser import create_browser_engine

async def main():
    engine = create_browser_engine()
    await engine.start(headless=False, port=9230)
    n = await engine.get_tabs()
    target = None
    for i in range(n):
        await engine.switch_tab(i)
        await asyncio.sleep(0.3)
        url = await engine.get_url()
        if "get-quote" in url:
            target = i
            break
    if target is None:
        print("No get-quote tab")
        return
    print(f"Using TAB {target}")

    # Test 1: houseQuote.html direct nav
    print("\n--- TEST 1: houseQuote.html direct nav ---")
    await engine.navigate("https://geglink.greateasterngeneral.com/geglink/getquote/houseQuote.html")
    await asyncio.sleep(4)
    url = await engine.get_url()
    title = await engine.get_title()
    print(f"URL: {url} | TITLE: {title}")

    # Test 2: back to get-quote, click Fire Quotation link
    print("\n--- TEST 2: click Fire Quotation link from get-quote ---")
    await engine.navigate("https://geglink.greateasterngeneral.com/oacportal/group/geglink/get-quote")
    await asyncio.sleep(4)
    # Find and click the Fire Quotation link via JS
    js_click = """
    (() => {
        const links = document.querySelectorAll('a');
        for (const a of links) {
            if ((a.textContent || '').trim().includes('Fire Quotation')) {
                a.click();
                return 'clicked: ' + a.href;
            }
        }
        return 'not found';
    })()
    """
    r = await engine.evaluate(js_click)
    print(f"Click result: {r}")
    await asyncio.sleep(6)
    url = await engine.get_url()
    title = await engine.get_title()
    print(f"URL after click: {url} | TITLE: {title}")

    # Dump page
    js = """
    (() => {
        const out = {url: location.href, title: document.title, text: '', forms: document.forms.length};
        out.text = document.body ? document.body.innerText.slice(0, 1200) : '';
        return JSON.stringify(out);
    })()
    """
    r = await engine.evaluate(js)
    if r:
        data = json.loads(r)
        print(f"FORMS: {data['forms']}")
        print(f"TEXT:\n{data['text'][:1000]}")
    else:
        print("evaluate None")

    await engine.stop()

asyncio.run(main())
