"""Test: navigate to fireQuote.html with valid session (9230)."""
import asyncio, sys, json
sys.path.insert(0, "/home/antkk/InsureDesk")
from src.browser import create_browser_engine

async def main():
    engine = create_browser_engine()
    await engine.start(headless=False, port=9230)
    n = await engine.get_tabs()
    # Find a geglink get-quote tab
    target = None
    for i in range(n):
        await engine.switch_tab(i)
        await asyncio.sleep(0.3)
        url = await engine.get_url()
        if "get-quote" in url:
            target = i
            break
    if target is None:
        print("No get-quote tab found")
        return

    print(f"Using TAB {target}")
    # Navigate to fireQuote.html
    ok = await engine.navigate("https://geglink.greateasterngeneral.com/geglink/getquote/fireQuote.html")
    print(f"Navigate fireQuote.html: {ok}")
    await asyncio.sleep(5)
    url = await engine.get_url()
    print(f"URL now: {url}")

    # Dump page state
    js = """
    (() => {
        const out = {url: location.href, title: document.title, text: '', formCount: document.forms.length, inputs: []};
        out.text = document.body ? document.body.innerText.slice(0, 1500) : '';
        document.querySelectorAll('input, select').forEach(el => {
            out.inputs.push({tag: el.tagName, name: el.name || '', id: el.id || '', type: el.type || '', value: (el.value || '').slice(0, 40)});
        });
        return JSON.stringify(out);
    })()
    """
    r = await engine.evaluate(js)
    if r:
        data = json.loads(r)
        print(f"TITLE: {data['title']}")
        print(f"FORMS: {data['formCount']}")
        print(f"TEXT:\n{data['text'][:1200]}")
        print(f"INPUTS ({len(data['inputs'])}):")
        for i in data['inputs'][:40]:
            print(f"  {i['tag']} name={i['name']} id={i['id']} type={i['type']} value={i['value']}")
    else:
        print("evaluate None")
        print(f"url: {url}")

    await engine.stop()

asyncio.run(main())
