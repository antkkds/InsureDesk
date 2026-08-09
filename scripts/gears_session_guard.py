"""GEARS session guard: detect expiry → auto-recover via GEGLink SSO chain → retry.

Why: GEARS sessions expire (forcelogout) and have interrupted real quote runs
twice (2026-08-09). This module is the recovery layer for any GEARS automation:

    from gears_session_guard import ensure_gears_session, with_session_recovery

    # At task start (before touching GEARS):
    page = await ensure_gears_session(ctx, page, quote_url=QUOTE_URL)

    # Wrap operations that can hit session expiry mid-run:
    await with_session_recovery(ctx, page, quote_url, my_operation, arg1)

IRON RULES (from geglink-portal-login skill):
- ONE GEGLink tab only. Never ctx.new_page() for GEGLink.
- Never logout manually — wait for automatic server logout.
- Re-login on the SAME tab via fetch POST submitlogin.html.
- Reuse the existing GEARS tab; SSO lands on the GEARS home.

Run standalone:  python3 gears_session_guard.py --check   (health only)
                 python3 gears_session_guard.py --recover --quote <quote_url>
"""
import asyncio
import json
import sys

from playwright.async_api import async_playwright

CDP = "http://127.0.0.1:9333"
GEGLINK_BASE = "https://geglink.greateasterngeneral.com"
GEARS_BASE = "https://gears-my.greateasterngeneral.com"
LOGIN_URL = GEGLINK_BASE + "/geglink/userlogin.html"
AGENT_HOME_URL = GEGLINK_BASE + "/geglink/agent/agent_home.html"

# TODO(cred-vault): pull from InsureDesk credential vault instead of constants
GEGLINK_USER = "FHL8125"
GEGLINK_PWD = "Cvbn123!"

# Signals that the current page is a login/logout trap (session gone)
EXPIRED_URL_MARKERS = ["forcelogout", "userlogin", "submitlogin", "login.html"]
EXPIRED_BODY_MARKERS = [
    "please login with your registered user id",
    "session has expired",
    "your session has expired",
    "session expired",
    "timeout",
    "sorry, we have encountered an issue",
    "you will be redirected back to home",
    "unable to process your request",
]
LOCKED_BODY_MARKERS = ["account has been locked", "account is locked"]

GEGLINK_MARKERS = ["geglink.greateasterngeneral.com"]
GEARS_MARKERS = ["gears-my.greateasterngeneral.com"]


class SessionExpiredError(RuntimeError):
    """Raised when an operation detects the GEARS session died mid-run."""


def is_geglink(url: str) -> bool:
    return any(m in url for m in GEGLINK_MARKERS)


def is_gears(url: str) -> bool:
    return any(m in url for m in GEARS_MARKERS)


# --------------------------------------------------------------------------
# 1. HEALTH DETECTION
# --------------------------------------------------------------------------
async def session_health(page) -> str:
    """Return 'OK' | 'EXPIRED' | 'LOCKED' | 'UNKNOWN'.

    Checks the current tab URL + body, then (if on GEARS) probes the
    dashboard with a same-origin fetch to confirm the session actually works.
    """
    try:
        url = page.url
    except Exception:
        return "UNKNOWN"
    lower_url = url.lower()

    for m in EXPIRED_URL_MARKERS:
        if m in lower_url:
            return "EXPIRED"
    if any(m in lower_url for m in LOCKED_BODY_MARKERS):
        return "LOCKED"

    try:
        body = await page.evaluate(
            "() => document.body ? document.body.innerText.slice(0, 800) : ''"
        )
    except Exception:
        body = ""
    lower = body.lower()
    if any(m in lower for m in LOCKED_BODY_MARKERS):
        return "LOCKED"
    if any(m in lower for m in EXPIRED_BODY_MARKERS):
        return "EXPIRED"

    # On GEARS: page-level signals only. (Direct store API probes are
    # unreliable: the API requires a per-session 'Token-Request' header that
    # Angular injects automatically but external fetch/XHR can't replicate —
    # probes return 500 IFE1008 even when the session is perfectly healthy.)
    if is_gears(url):
        try:
            tok = await page.evaluate("localStorage.getItem('access-data')")
        except Exception:
            tok = None
        if not tok:
            return "EXPIRED"
        # Angular still booting — give it a moment / mark UNKNOWN
        if "loading" in lower and "kk" not in lower:
            return "UNKNOWN"
        return "OK"

    # On GEGLink: treat any GEGLink page reachable as OK at GEGLink layer
    if is_geglink(url):
        if "houseQuote" in url or "agent_home" in url or "get-quote" in url:
            return "OK"
        # userlogin etc already caught above; a generic geglink page is ambiguous
        return "UNKNOWN"

    return "UNKNOWN"


# --------------------------------------------------------------------------
# 2. GEGLINK LAYER — single tab + login on same tab
# --------------------------------------------------------------------------
async def find_or_create_single_tab(ctx):
    """Return THE one GEGLink tab (close extras, never create a 2nd for GEGLink)."""
    pages = [p for p in ctx.pages if is_geglink(p.url)]
    if len(pages) > 1:
        print(f"⚠️  {len(pages)} GEGLink tabs — closing extras, keeping first")
        for extra in pages[1:]:
            try:
                await extra.close()
            except Exception:
                pass
        pages = [p for p in ctx.pages if is_geglink(p.url)]
    if pages:
        return pages[0]
    page = await ctx.new_page()
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
    return page


async def login_on_same_tab(page) -> str:
    """Login on THE SAME tab via fetch submitlogin. Returns 'OK'/'LOCKED'/'FAIL'."""
    result = await page.evaluate(
        """async (creds) => {
            const resp = await fetch('/geglink/submitlogin.html', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'oac_username=' + encodeURIComponent(creds.u)
                      + '&oac_intpwd=' + encodeURIComponent(creds.p),
                redirect: 'follow'
            });
            const text = await resp.text();
            const lower = text.toLowerCase();
            return {
                status: resp.status,
                locked: lower.includes('account has been locked'),
                loginForm: lower.includes('please login with your registered user id'),
                len: text.length
            };
        }""",
        {"u": GEGLINK_USER, "p": GEGLINK_PWD},
    )
    if result.get("locked"):
        return "LOCKED"
    if result.get("status") == 200 and not result.get("loginForm"):
        return "OK"
    return "FAIL"


# --------------------------------------------------------------------------
# 3. SSO LAYER — GEGLink → GEARS
# --------------------------------------------------------------------------
async def sso_into_gears(page) -> bool:
    """agent_home → redirectJSP(IFE) → eqForm submit → GEARS. Returns True if landed."""
    await page.goto(AGENT_HOME_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(3000)
    print(f"  sso: agent_home url={page.url[:100]}")
    html = await page.evaluate(
        """async () => {
            const resp = await fetch('/geglink/agent/redirectJSP.html', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'channelType=IFE'
            });
            return await resp.text();
        }"""
    )
    print(f"  sso: redirectJSP len={len(html)}")
    submitted = await page.evaluate(
        """(html) => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const form = doc.querySelector('form[name="eqForm"]');
            if (!form) return false;
            document.body.appendChild(form);
            form.submit();
            return true;
        }""",
        html,
    )
    print(f"  sso: eqForm submitted={submitted}")
    if not submitted:
        print("  ✗ eqForm not found in redirectJSP response")
        return False
    await page.wait_for_timeout(12000)
    print(f"  sso: after 12s url={page.url[:110]}")
    if is_gears(page.url):
        return True
    # GEARS home may be at /MY/AgencySales/P — give one more probe
    try:
        body = await page.evaluate("() => document.body ? document.body.innerText.slice(0, 300) : ''")
        print("  SSO landed on:", page.url[:90], "|", body.replace(chr(10), ' ')[:80])
    except Exception:
        pass
    return is_gears(page.url)


# --------------------------------------------------------------------------
# 4. FULL RECOVERY CHAIN
# --------------------------------------------------------------------------
async def ensure_gears_session(ctx, page=None, quote_url=None, max_attempts=2):
    """Ensure a healthy GEARS session; return the page to operate on.

    Chain: health check → (if needed) GEGLink login → SSO into GEARS →
    navigate back to quote_url if provided.
    """
    if page is None:
        page = ctx.pages[0]

    for attempt in range(1, max_attempts + 1):
        health = await session_health(page)
        print(f"[session] attempt {attempt}/{max_attempts} health={health} url={page.url[:80]}")
        if health == "OK":
            if quote_url and not page.url.startswith(quote_url):
                try:
                    await page.goto(quote_url, wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(6000)
                except Exception as e:
                    print(f"  ⚠️ goto quote_url failed: {str(e)[:80]}")
            return page
        if health == "LOCKED":
            raise RuntimeError("GEGLink account LOCKED — do NOT retry. Contact GE or wait for auto-unlock.")

        # ---- recovery chain ----
        print("  → recovering: GEGLink login → SSO → GEARS")
        geg_page = await find_or_create_single_tab(ctx)
        geg_health = await session_health(geg_page)
        print(f"  GEGLink health: {geg_health}")
        if geg_health == "EXPIRED":
            outcome = await login_on_same_tab(geg_page)
            print(f"  GEGLink login: {outcome}")
            if outcome == "LOCKED":
                raise RuntimeError("GEGLink account LOCKED during recovery.")
            if outcome != "OK":
                await asyncio.sleep(4)
                outcome2 = await login_on_same_tab(geg_page)
                print(f"  GEGLink login retry: {outcome2}")
                if outcome2 != "OK":
                    raise RuntimeError(f"GEGLink login failed: {outcome}/{outcome2}")
            await geg_page.wait_for_timeout(4000)

        ok = await sso_into_gears(geg_page)
        if not ok:
            raise RuntimeError("SSO into GEARS failed — landed on: " + geg_page.url[:100])

        page = geg_page  # SSO lands on the same tab; that tab is now the GEARS tab
        # After recovery, navigation target may be the GEARS home (/MY/AgencySales/P)
        if quote_url:
            try:
                await page.goto(quote_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(8000)
            except Exception as e:
                print(f"  ⚠️ goto quote_url after recovery failed: {str(e)[:80]}")
        # Recovery succeeded — hand back the page. Do NOT loop again (the
        # Angular app may still be LOADING, so a health re-check right now
        # can read UNKNOWN and trigger a redundant second recovery).
        return page

    raise RuntimeError(f"Session recovery failed after {max_attempts} attempts")


# --------------------------------------------------------------------------
# 5. OPERATION WRAPPER
# --------------------------------------------------------------------------
async def with_session_recovery(ctx, page, quote_url, op, *args, max_attempts=2, **kwargs):
    """Run op(*args) with session-expiry detection; recover + retry on failure.

    op must be an async callable. If the GEARS session dies mid-operation,
    either op raises SessionExpiredError or the page URL/body shows the
    login trap afterwards — both trigger recovery.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            result = await op(*args, **kwargs)
            # post-check: did we end up on a login trap?
            health = await session_health(page)
            if health == "EXPIRED":
                raise SessionExpiredError(f"session died during op (health={health})")
            return result
        except SessionExpiredError:
            if attempt >= max_attempts:
                raise
            print(f"[recovery] op failed with session expiry (attempt {attempt}) — recovering")
            page = await ensure_gears_session(ctx, page, quote_url=quote_url)
    raise RuntimeError("unreachable")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
async def main_cli():
    args = sys.argv[1:]
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if is_gears(pg.url):
                page = pg
                break
        if page is None:
            page = ctx.pages[0]

        if "--check" in args:
            print("HEALTH:", await session_health(page), "| url:", page.url[:100])
        elif "--recover" in args:
            qurl = None
            if "--quote" in args:
                qurl = args[args.index("--quote") + 1]
            page = await ensure_gears_session(ctx, page, quote_url=qurl)
            print("RECOVERED →", page.url[:100])
            print("HEALTH:", await session_health(page))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main_cli())
