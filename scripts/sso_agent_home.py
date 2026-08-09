"""SSO from agent_home.html (has loginForm) → redirectJSP → eqForm → GEARS."""
import asyncio, json
from playwright.async_api import async_playwright

REDIRECT_JS = """async (payload) => {
    const fd = new URLSearchParams();
    for (const [k, v] of Object.entries(payload)) fd.set(k, v);
    const r = await fetch(payload._action, {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: fd.toString(),
        credentials: 'include'
    });
    const txt = await r.text();
    return {status: r.status, hasEq: txt.includes('eqForm'), len: txt.length, body: txt.slice(0, 100)};
}"""

EQ_SUBMIT_JS = """async (payload) => {
    const fd = new URLSearchParams();
    for (const [k, v] of Object.entries(payload)) fd.set(k, v);
    const r = await fetch(payload._action, {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: fd.toString(),
        credentials: 'include'
    });
    const txt = await r.text();
    const doc = new DOMParser().parseFromString(txt, 'text/html');
    const eq = doc.querySelector('form[name=eqForm]');
    if (!eq) return {ok: false, reason: 'no eqForm', body: txt.slice(0, 150)};
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = eq.action;
    eq.querySelectorAll('input').forEach(i => {
        const h = document.createElement('input');
        h.type = 'hidden'; h.name = i.name; h.value = i.value;
        form.appendChild(h);
    });
    document.body.appendChild(form);
    form.submit();
    return {ok: true, action: eq.action.slice(0, 90)};
}"""


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://127.0.0.1:9333")
        ctx = b.contexts[0]
        page = None
        for p in ctx.pages:
            if "geglink" in p.url:
                page = p
                break
        if not page:
            print("NO GEGLINK TAB"); return

        # ensure on agent_home.html
        if "agent_home" not in page.url:
            await page.goto("https://geglink.greateasterngeneral.com/geglink/agent/agent_home.html")
            await asyncio.sleep(4)
        print("1. at:", page.url[:90])

        form_info = await page.evaluate("""(() => {
            const f = document.querySelector('form[name=loginForm]');
            if (!f) return null;
            const data = {};
            f.querySelectorAll('input').forEach(i => { if (i.name) data[i.name] = i.value; });
            return {action: f.action, data};
        })()""")
        print("2. loginForm:", json.dumps(form_info, ensure_ascii=False)[:350])
        if not form_info:
            body = await page.evaluate("document.body ? document.body.innerText.slice(0, 200) : ''")
            print("   no loginForm — body:", body.replace("\n", " | ")[:200])
            return

        payload = dict(form_info["data"])
        payload["_action"] = form_info["action"]
        r2 = await page.evaluate(REDIRECT_JS, payload)
        print("3. redirectJSP:", json.dumps(r2, ensure_ascii=False)[:300])
        if not r2.get("hasEq"):
            print("   ❌ no eqForm"); return

        r3 = await page.evaluate(EQ_SUBMIT_JS, payload)
        print("4. eqForm submit:", json.dumps(r3, ensure_ascii=False)[:200])
        await asyncio.sleep(12)
        print("5. final url:", page.url[:110])
        body = await page.evaluate("document.body ? document.body.innerText.slice(0, 250) : ''")
        print("   body:", body.replace("\n", " | ")[:250])


asyncio.run(main())
