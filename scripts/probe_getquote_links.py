"""Dump full links from geglink get-quote tab (9230)."""
import asyncio, sys, json
sys.path.insert(0, "/home/antkk/InsureDesk")
from src.browser import create_browser_engine

DUMP_JS = """
(() => {
    const out = {url: location.href, links: []};
    document.querySelectorAll('a, input[type=image], input[type=submit], button').forEach(a => {
        const href = a.href || a.src || '';
        const txt = (a.textContent || a.value || a.name || a.alt || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
        const onclick = (a.getAttribute && a.getAttribute('onclick')) || '';
        const name = a.name || '';
        const id = a.id || '';
        out.links.push({href: href.slice(0, 160), txt: txt.slice(0, 60), onclick: onclick.slice(0, 80), name, id});
    });
    return JSON.stringify(out);
})()
"""

async def main():
    engine = create_browser_engine()
    await engine.start(headless=False, port=9230)
    n = await engine.get_tabs()
    for i in range(n):
        await engine.switch_tab(i)
        await asyncio.sleep(0.3)
        url = await engine.get_url()
        if "get-quote" in url:
            print(f"\n=== TAB {i}: {url} ===")
            r = await engine.evaluate(DUMP_JS)
            if r:
                data = json.loads(r)
                for l in data['links']:
                    print(f"  txt=[{l['txt']}] name=[{l['name']}] id=[{l['id']}] href=[{l['href']}] onclick=[{l['onclick']}]")
            else:
                print("  evaluate None")
    await engine.stop()

asyncio.run(main())
