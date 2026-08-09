"""Check 9230 GEGLink session state + dump page to find portal options.
Reuses existing tabs — NO new login (avoids concurrentLogout risk)."""
import asyncio, sys, json
sys.path.insert(0, "/home/antkk/InsureDesk")

from src.browser import create_browser_engine

DUMP_JS = """
(() => {
    const out = {url: location.href, title: document.title, links: [], iframes: [], text: ''};
    document.querySelectorAll('a').forEach(a => {
        const href = a.href || '';
        const txt = (a.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
        if (href || txt) out.links.push({href: href.slice(0, 140), txt: txt.slice(0, 60)});
    });
    document.querySelectorAll('iframe').forEach(f => {
        out.iframes.push({src: (f.src || '').slice(0, 160), id: f.id, name: f.name});
    });
    out.text = document.body ? document.body.innerText.slice(0, 4000) : '';
    return JSON.stringify(out);
})()
"""

async def main():
    engine = create_browser_engine()
    ok = await engine.start(headless=False, port=9230)  # connect to user's Chrome
    print(f"Engine connect 9230: {ok}")
    if not ok:
        print("FAILED to connect 9230")
        return

    n = await engine.get_tabs()
    print(f"Tabs: {n}")

    # Find geglink tab, dump each one briefly
    for i in range(n):
        await engine.switch_tab(i)
        await asyncio.sleep(0.5)
        url = await engine.get_url()
        if "geglink" in url or "gears" in url:
            print(f"\n=== TAB {i}: {url} ===")
            r = await engine.evaluate(DUMP_JS)
            if r:
                data = json.loads(r)
                print(f"TITLE: {data['title']}")
                print(f"TEXT (first 1500):\n{data['text'][:1500]}")
                # Portal-relevant links only
                print(f"LINKS ({len(data['links'])}):")
                for l in data['links']:
                    low = (l['txt'] + ' ' + l['href']).lower()
                    if any(k in low for k in ['portal', 'quote', 'quotation', 'fire', 'home', 'logout', 'general', 'life', 'motor', 'e-', 'eq', 'ife']):
                        print(f"  [{l['txt']}] -> {l['href']}")
                print(f"IFRAMES ({len(data['iframes'])}):")
                for f in data['iframes']:
                    print(f"  id={f['id']} name={f['name']} src={f['src']}")
            else:
                print("  evaluate returned None")

    await engine.stop()

asyncio.run(main())
