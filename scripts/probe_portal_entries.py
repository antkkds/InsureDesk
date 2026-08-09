"""Find portal entry elements on get-quote page — top-level + iframes."""
import asyncio, sys, json
sys.path.insert(0, "/home/antkk/InsureDesk")
from src.browser import create_browser_engine

DUMP_JS = """
(() => {
    const out = {url: location.href, found: []};
    const KEYS = ['quotation', 'house', 'fire', 'homeowner', 'householder', 'eqs', 'ife', 'quote', 'portal'];
    // Top-level links
    document.querySelectorAll('a, input[type=image], input[type=submit], button, area').forEach(a => {
        const href = a.href || a.src || '';
        const txt = (a.textContent || a.value || a.name || a.alt || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
        const hay = (href + ' ' + txt + ' ' + (a.onclick ? String(a.onclick) : '')).toLowerCase();
        if (KEYS.some(k => hay.includes(k))) {
            out.found.push({scope: 'top', txt: txt.slice(0, 50), href: href.slice(0, 160), onclick: String(a.onclick || '').slice(0, 100)});
        }
    });
    // Iframes
    document.querySelectorAll('iframe').forEach((f, fi) => {
        let doc = null;
        try { doc = f.contentDocument || f.contentWindow.document; } catch(e) {}
        if (!doc) { out.found.push({scope: 'iframe-' + fi, note: 'CROSS-ORIGIN or not loaded', src: (f.src || '').slice(0, 120)}); return; }
        doc.querySelectorAll('a, input[type=image], input[type=submit], button').forEach(a => {
            const href = a.href || a.src || '';
            const txt = (a.textContent || a.value || a.name || a.alt || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
            const hay = (href + ' ' + txt + ' ' + (a.onclick ? String(a.onclick) : '')).toLowerCase();
            if (KEYS.some(k => hay.includes(k))) {
                out.found.push({scope: 'iframe-' + fi + '[' + (f.src || '').slice(0, 60) + ']', txt: txt.slice(0, 50), href: href.slice(0, 160), onclick: String(a.onclick || '').slice(0, 100)});
            }
        });
        // Also dump iframe body text first 800 chars
        out.found.push({scope: 'iframe-' + fi + '-TEXT', txt: (doc.body ? doc.body.innerText.slice(0, 800) : '')});
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
                for f in data['found']:
                    print(f"  [{f['scope']}] {f.get('txt','')[:60]} | href={f.get('href','')[:100]} | onclick={f.get('onclick','')[:60]}")
            else:
                print("  evaluate None")
    await engine.stop()

asyncio.run(main())
