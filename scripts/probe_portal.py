"""Probe: login to GEGLink, dump complete page structure to find portal options."""
import asyncio, sys, json
sys.path.insert(0, "/home/antkk/InsureDesk")

from src.browser import create_browser_engine
from src.runtime.credential_service import CredentialService
from src.database.db_manager import get_session

async def main():
    # Get credentials from vault
    db = get_session()
    svc = CredentialService(db)
    cred = svc.get("great_eastern")
    if not cred:
        print("NO CREDENTIALS for great_eastern")
        return
    print(f"Got credentials: user={cred.username[:3]}*** enabled portal={cred.portal}")

    engine = create_browser_engine()
    ok = await engine.start(headless=False, port=0)
    print(f"Engine start: {ok}")
    if not ok:
        return

    # Navigate to login
    login_url = "https://geglink.greateasterngeneral.com/geglink/userlogin.html"
    await engine.navigate(login_url)
    await asyncio.sleep(3)
    url = await engine.get_url()
    print(f"After navigate: {url}")

    # Fill credentials
    filled_user = await engine.fill("input[name='oac_username']", cred.username)
    filled_pass = await engine.fill("input[name='oac_intpwd']", cred.password)
    print(f"Fill: user={filled_user} pass={filled_pass}")

    # Click submit
    clicked = await engine.click("input[src*='loginbut.jpg']")
    print(f"Click submit: {clicked}")
    await asyncio.sleep(6)

    url = await engine.get_url()
    print(f"After login: {url}")

    # Dump complete page: all links, text, iframes
    dump_js = """
    (() => {
        const out = {url: location.href, title: document.title, links: [], iframes: [], text: ''};
        document.querySelectorAll('a').forEach(a => {
            const href = a.href || '';
            const txt = (a.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
            if (href || txt) out.links.push({href: href.slice(0, 120), txt: txt.slice(0, 60)});
        });
        document.querySelectorAll('iframe').forEach(f => {
            out.iframes.push({src: (f.src || '').slice(0, 150), id: f.id, name: f.name});
        });
        out.text = document.body ? document.body.innerText.slice(0, 3000) : '';
        return JSON.stringify(out);
    })()
    """
    result = await engine.evaluate(dump_js)
    print("=== PAGE DUMP ===")
    if result:
        data = json.loads(result)
        print(f"TITLE: {data['title']}")
        print(f"TEXT:\n{data['text']}")
        print(f"LINKS ({len(data['links'])}):")
        for l in data['links'][:60]:
            print(f"  [{l['txt']}] -> {l['href']}")
        print(f"IFRAMES ({len(data['iframes'])}):")
        for f in data['iframes']:
            print(f"  id={f['id']} name={f['name']} src={f['src']}")
    else:
        print("DUMP FAILED - evaluate returned None")
        print(f"current_url: {url}")

    await engine.stop()

asyncio.run(main())
