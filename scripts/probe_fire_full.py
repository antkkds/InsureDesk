"""Full probe: fresh login -> get-quote -> click Fire Quotation -> dump form required fields."""
import asyncio, sys, json
sys.path.insert(0, "/home/antkk/InsureDesk")

from src.browser import create_browser_engine
from src.runtime.credential_service import CredentialService
from src.database.db_manager import get_session
from src.browser.chrome.tabs import list_tabs

async def main():
    db = get_session()
    svc = CredentialService(db)
    cred = svc.get("great_eastern")
    if not cred:
        print("NO CREDENTIALS")
        return
    print(f"Credentials: {cred.username[:3]}***")

    engine = create_browser_engine()
    ok = await engine.start(headless=False, port=0)
    print(f"Engine: {ok}")

    # 1. Login
    await engine.navigate("https://geglink.greateasterngeneral.com/geglink/userlogin.html")
    await asyncio.sleep(3)
    await engine.fill("input[name='oac_username']", cred.username)
    await engine.fill("input[name='oac_intpwd']", cred.password)
    await engine.click("input[src*='loginbut.jpg']")
    await asyncio.sleep(6)
    url = await engine.get_url()
    print(f"After login: {url}")

    # If PDPA page, accept
    pdpa = await engine.evaluate("document.body ? document.body.innerText.includes('I Agree') : false")
    if pdpa:
        await engine.click("input[value='I Agree']")
        await asyncio.sleep(3)
        url = await engine.get_url()
        print(f"PDPA accepted, now: {url}")

    # 2. Get Quote page
    await engine.navigate("https://geglink.greateasterngeneral.com/oacportal/group/geglink/get-quote")
    await asyncio.sleep(5)
    url = await engine.get_url()
    print(f"Get Quote page: {url}")

    # 3. Click Fire Quotation link
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
    print(f"Click Fire Quotation: {r}")
    await asyncio.sleep(6)

    # 4. Find fireQuote tab (may be new tab)
    tabs = list_tabs(engine._port)
    print(f"Tabs now: {len(tabs)}")
    fire_tab_idx = None
    for i, t in enumerate(tabs):
        print(f"  [{i}] {t.url[:90]}")
        if "fireQuote" in t.url or "houseQuote" in t.url:
            fire_tab_idx = i
    if fire_tab_idx is not None:
        await engine.switch_tab(fire_tab_idx)
        await asyncio.sleep(3)
        url = await engine.get_url()
        print(f"Switched to fire tab: {url}")
    else:
        url = await engine.get_url()
        print(f"Current URL (no fire tab found): {url}")

    # 5. Dump form: all inputs with required status
    dump_js = """
    (() => {
        const out = {url: location.href, title: document.title, text: '', fields: []};
        out.text = document.body ? document.body.innerText.slice(0, 2000) : '';
        const els = document.querySelectorAll('input, select, textarea');
        for (const el of els) {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            out.fields.push({
                tag: el.tagName, name: el.name || '', id: el.id || '', type: el.type || '',
                required: el.required || (el.className || '').includes('req') || (el.parentElement && (el.parentElement.className || '').includes('req')) || false,
                value: (el.value || '').slice(0, 30), maxlen: el.maxLength || ''
            });
        }
        return JSON.stringify(out);
    })()
    """
    r = await engine.evaluate(dump_js)
    if r:
        data = json.loads(r)
        print(f"\nTITLE: {data['title']}")
        print(f"TEXT:\n{data['text'][:1500]}")
        print(f"\nVISIBLE FIELDS ({len(data['fields'])}):")
        for f in data['fields']:
            req = "REQ " if f['required'] else "    "
            print(f"  {req}{f['tag']} name={f['name']} id={f['id']} type={f['type']} value={f['value']} maxlen={f['maxlen']}")
    else:
        print("evaluate None")

    await engine.stop()

asyncio.run(main())
