"""C1 — Real Portal Discovery: Scan GEGLink IFE/EQ form fields.

This script:
1. Connects to existing Chrome via Playwright CDP
2. Navigates to GEGLink
3. Logs in with stored credentials
4. Launches IFE and scans form fields
5. Captures EQ as well
6. Saves profiles to profiles/ife_quote.yaml and profiles/eq_quote.yaml

SAFETY: READ_ONLY mode — no calculate, no submit, no save_draft.
"""

import asyncio
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ── Credentials ───────────────────────────────────────────────

GEGLINK_USERNAME = "fhl8125"
GEGLINK_PASSWORD = "Uiop234<"

# ── URLs ──────────────────────────────────────────────────────

BASE_URL = "https://geglink.greateasterngeneral.com"
LOGIN_URL = f"{BASE_URL}/geglink/userlogin.html"
DASHBOARD_URL = f"{BASE_URL}/oacportal/group/geglink/home"
GET_QUOTE_URL = f"{BASE_URL}/oacportal/group/geglink/get-quote"

# ── JS scanner (same as SCAN_FORM_JS in src/quote/discovery/scanner.py) ──

SCAN_FORM_JS = """
(() => {
    const fields = [];
    const formElements = document.querySelectorAll(
        'input, select, textarea, button, [role="button"], ' +
        'a.btn, a[class*="button"], [contenteditable="true"]'
    );

    for (const el of formElements) {
        const tag = el.tagName.toLowerCase();
        const type = (el.getAttribute('type') || 'text').toLowerCase();
        const name = el.getAttribute('name') || '';
        const id = el.getAttribute('id') || '';
        const placeholder = el.getAttribute('placeholder') || '';

        if (type === 'hidden') continue;
        if (tag === 'button' || (tag === 'input' && type === 'submit') || (tag === 'input' && type === 'image')) {
            continue;
        }

        let label = '';
        const labelEl = document.querySelector('label[for="' + id + '"]');
        if (labelEl) label = (labelEl.textContent || '').trim();
        if (!label) {
            const parent = el.closest('label');
            if (parent) label = (parent.textContent || '').trim();
        }
        if (!label) label = el.getAttribute('aria-label') || '';
        if (!label && placeholder) label = placeholder;

        let options = [];
        if (tag === 'select') {
            for (const opt of el.querySelectorAll('option')) {
                options.push({
                    value: opt.value,
                    label: (opt.textContent || '').trim(),
                    selected: opt.selected,
                });
            }
        }

        const required = el.hasAttribute('required') ||
            (el.getAttribute('aria-required') === 'true') ||
            (el.classList.contains('required')) || false;

        const minLength = el.getAttribute('minlength');
        const maxLength = el.getAttribute('maxlength');
        const min = el.getAttribute('min');
        const max = el.getAttribute('max');
        const pattern = el.getAttribute('pattern') || '';

        const candidates = {};
        if (id) {
            const sel = '#' + CSS.escape(id);
            const count = document.querySelectorAll(sel).length;
            candidates[sel] = count === 1 ? 95 : 80;
        }
        const testId = el.getAttribute('data-testid');
        if (testId) candidates['[data-testid="' + testId + '"]'] = 92;
        if (name) {
            const sel = '[name="' + name + '"]';
            const count = document.querySelectorAll(sel).length;
            candidates[sel] = count === 1 ? 82 : 70;
        }
        if (label && !candidates['[aria-label="' + label + '"]']) {
            candidates['[aria-label="' + label + '"]'] = 80;
        }
        if (placeholder) candidates['[placeholder="' + placeholder + '"]'] = 75;
        const classes = (el.className || '').split(/\\s+/).filter(Boolean);
        const stableClasses = classes.filter(c => !/^[a-z]+-[a-f0-9]{4,}/.test(c) && c !== '');
        if (stableClasses.length > 0) {
            const sel = tag + '.' + stableClasses.join('.');
            candidates[sel] = 55;
        }
        const bestSelector = Object.keys(candidates)
            .sort((a, b) => candidates[b] - candidates[a])[0] || tag;

        fields.push({
            key: name || id || (label ? label.toLowerCase().replace(/[^a-z0-9]+/g, '_') : '') || ('field_' + fields.length),
            tag: tag,
            type: type,
            name: name,
            id: id,
            label: label,
            placeholder: placeholder,
            selector: bestSelector,
            candidates: candidates,
            required: required,
            minLength: minLength || null,
            maxLength: maxLength || null,
            min: min || null,
            max: max || null,
            pattern: pattern || null,
            options: options,
            multiple: el.hasAttribute('multiple'),
        });
    }

    const actions = [];
    for (const el of document.querySelectorAll(
        'button, input[type="submit"], input[type="button"], ' +
        'a[class*="btn"], [role="button"]'
    )) {
        if (el.offsetParent === null) continue;
        const text = (el.textContent || el.value || '').trim().substring(0, 50);
        if (!text) continue;
        actions.push({
            key: text.toLowerCase().replace(/[^a-z0-9]+/g, '_'),
            text: text,
            selector: (el.id ? '#' + CSS.escape(el.id) : '') ||
                      '[value="' + (el.value || '') + '"]' ||
                      'button:has-text("' + text + '")',
            type: el.tagName.toLowerCase(),
        });
    }

    return {
        fields: fields,
        actions: actions,
        url: window.location.href,
        title: document.title,
    };
})();
"""


def scan_result_to_yaml(result, portal, channel, page_name):
    """Convert scan result to profile YAML format."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    fields_yaml = []
    for i, f in enumerate(result.get("fields", [])):
        field = {
            "key": f.get("key", f"field_{i}"),
            "label": f.get("label", ""),
            "selector": f.get("selector", ""),
            "tag": f.get("tag", "input"),
            "field_type": f.get("type", "text"),
            "required": f.get("required", False),
        }
        if f.get("placeholder"):
            field["placeholder"] = f["placeholder"]
        if f.get("options"):
            field["options"] = [{"value": o["value"], "label": o["label"]} for o in f["options"]]
        if f.get("multiple"):
            field["multiple"] = True
        if f.get("minLength"):
            field["min_length"] = f["minLength"]
        if f.get("maxLength"):
            field["max_length"] = f["maxLength"]
        if f.get("pattern"):
            field["pattern"] = f["pattern"]
        fields_yaml.append(field)

    pages_yaml = {
        page_name: {
            "description": f"{page_name} form page",
            "url_pattern": result.get("url", ""),
            "elements": {f["key"]: {k: v for k, v in f.items() if k != "key"} for f in fields_yaml},
        }
    }

    # Add actions if present
    actions = result.get("actions", [])
    if actions:
        pages_yaml[page_name]["actions"] = [
            {"key": a["key"], "selector": a["selector"], "type": a["type"]}
            for a in actions
        ]

    return {
        "version": "1.0",
        "portal": portal,
        "quote_channel": channel,
        "captured_at": now,
        "pages": pages_yaml,
    }


def write_yaml(data, path):
    """Write data as YAML to file."""
    import yaml
    with open(path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"  ✓ Saved to {path}")


async def main():
    from playwright.async_api import async_playwright

    print("=" * 60)
    print("C1 — Real Portal Discovery")
    print(f"  Target: GEGLink IFE / EQ")
    print(f"  Time:   {datetime.utcnow().isoformat()}")
    print(f"  Mode:   READ_ONLY (scan only, no writes)")
    print("=" * 60)

    async with async_playwright() as p:
        # 1. Connect to existing Chrome via CDP
        print("\n1. Connecting to Chrome via CDP (port 9222)...")
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]

        # 2. Check for existing GEGLink tab or create one
        print("2. Checking existing pages...")
        existing_page = None
        for page in ctx.pages:
            url = page.url
            print(f"  Found page: {url[:100]}")
            if "geglink" in url.lower() and "login" not in url.lower():
                existing_page = page
                print(f"  → Using existing GEGLink page")
                break

        if existing_page:
            page = existing_page
        else:
            # Use the first available page (can't create new pages in Electron)
            page = ctx.pages[0] if ctx.pages else None
            if not page:
                print("  ERROR: No pages available")
                return False

        # 3. Navigate to GEGLink login
        print(f"\n3. Navigating to GEGLink login...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        print(f"  Current URL: {page.url}")

        # 4. Check if already logged in
        current_url = page.url
        if "oacportal" in current_url and "login" not in current_url.lower():
            print("\n4. Already logged in! Skipping login...")
        else:
            print("\n4. Logging in...")
            # Fill credentials
            await page.fill("input[name='oac_username']", GEGLINK_USERNAME)
            await page.fill("input[name='oac_intpwd']", GEGLINK_PASSWORD)
            
            # Submit login via direct POST (fields are outside <form>, normal submit doesn't work)
            print("  Submitting login via direct POST...")
            result = await page.evaluate("""async ([username, password]) => {
                try {
                    const resp = await fetch('https://geglink.greateasterngeneral.com/geglink/submitlogin.html', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Origin': 'https://geglink.greateasterngeneral.com',
                        },
                        body: new URLSearchParams({
                            'oac_username': username,
                            'oac_intpwd': password,
                        }),
                        credentials: 'include',
                    });
                    return {status: resp.status, url: resp.url, ok: resp.ok};
                } catch(e) {
                    return {error: e.message};
                }
            }""", [GEGLINK_USERNAME, GEGLINK_PASSWORD])
            print(f"  POST result: {result}")

            # Navigate to the result URL — ignore navigation errors
            post_url = result.get('url', '')
            if post_url:
                print(f"  Navigating to: {post_url[:100]}")
                try:
                    await page.goto(post_url, wait_until='load', timeout=15000)
                except Exception as e:
                    print(f"  Goto note (expected): {type(e).__name__}")
                await page.wait_for_timeout(5000)

            # Check for PDPA or post-login page
            current_url = page.url
            print(f"  After login URL: {current_url[:120]}")
            if "pdpa" in current_url.lower():
                print("  PDPA page detected, accepting...")
                await page.evaluate("""() => {
                    const btns = document.querySelectorAll('input, button, a');
                    for (const btn of btns) {
                        const txt = (btn.value || btn.textContent || '').toLowerCase();
                        if (txt.includes('agree') || txt.includes('accept')) { btn.click(); return; }
                    }
                }""")
                await page.wait_for_timeout(5000)

            # Try navigating to dashboard
            current_url = page.url
            print(f"  After PDPA URL: {current_url[:120]}")

        # 5. Navigate to Get Quote page
        print(f"\n5. Navigating to Get Quote...")
        current_url = page.url
        if "get-quote" not in current_url:
            await page.evaluate(f"window.location.href = '{GET_QUOTE_URL}'")
            await page.wait_for_timeout(5000)
        print(f"  Current URL: {page.url[:120]}")

        # 6. Find iframe and scan
        print(f"\n6. Looking for eQuotation iframe...")
        iframes = page.frames
        quote_frames = []
        for f in iframes:
            try:
                url = f.url
                if "agent_home" in url or "eq_home" in url:
                    quote_frames.append(f)
            except:
                pass

        print(f"  Found {len(quote_frames)} quote iframe(s)")

        if not quote_frames:
            # Print all frames for debugging
            print("  All frames:")
            for f in iframes:
                try:
                    print(f"    - {f.name}: {f.url[:80]}")
                except:
                    print(f"    - {f.name}: <error>")

            # Try scanning the main page instead
            print("\n  Scanning main page for form fields...")
            result = await page.evaluate(SCAN_FORM_JS)
            print(f"  Found {len(result.get('fields', []))} fields, {len(result.get('actions', []))} actions")

            # Write main page scan
            yaml_data = scan_result_to_yaml(result, "great_eastern", "GENERAL", "get_quote")
            profile_path = os.path.expanduser("~/InsureDesk/profiles/geglink_getquote.yaml")
            write_yaml(yaml_data, profile_path)

        # 7. For IFE — need to launch it from the iframe
        print(f"\n7. Launching IFE...")
        if quote_frames:
            frame = quote_frames[0]
            # Find IFE form and submit
            try:
                # Use JS to find and submit the IFE form
                result = await frame.evaluate("""() => {
                    const forms = document.querySelectorAll('form');
                    for (const form of forms) {
                        const ch = form.querySelector('input[name="channelType"]');
                        if (ch && ch.value === 'IFE') {
                            return ch.value;
                        }
                    }
                    return null;
                }""")
                if result:
                    print(f"  Found IFE form, launching...")
                    await frame.evaluate("""() => {
                        const forms = document.querySelectorAll('form');
                        for (const form of forms) {
                            const ch = form.querySelector('input[name="channelType"]');
                            if (ch && ch.value === 'IFE') {
                                form.submit();
                                return;
                            }
                        }
                    }""")
                    await page.wait_for_timeout(5000)

                    # Scan all open pages
                    print(f"\n8. Scanning IFE form...")
                    for p in ctx.pages:
                        try:
                            await p.wait_for_timeout(1000)
                            result = await p.evaluate(SCAN_FORM_JS)
                            fields_count = len(result.get("fields", []))
                            actions_count = len(result.get("actions", []))
                            url = result.get("url", "")
                            print(f"  Page: {url[:80]}")
                            print(f"  Fields: {fields_count}, Actions: {actions_count}")

                            if fields_count > 0:
                                yaml_data = scan_result_to_yaml(
                                    result, "great_eastern", "IFE", "quote_form"
                                )
                                profile_path = os.path.expanduser(
                                    "~/InsureDesk/profiles/ife_quote.yaml"
                                )
                                write_yaml(yaml_data, profile_path)

                                # Print field summary
                                print(f"\n  Field summary:")
                                for f in result.get("fields", [])[:20]:
                                    req = "🔴" if f.get("required") else "⚪"
                                    print(f"    {req} {f.get('key', '?'):25s} {f.get('type', '?'):10s} label='{f.get('label', '')[:30]}'")
                                if len(result.get("fields", [])) > 20:
                                    print(f"    ... and {len(result.get('fields', [])) - 20} more fields")
                        except Exception as e:
                            print(f"  Error scanning page: {e}")
                else:
                    print("  IFE form not found in iframe")
            except Exception as e:
                print(f"  Error: {e}")

        # 8. Scan EQ if available
        print(f"\n9. Scanning EQ form...")
        try:
            # Navigate back to Get Quote via JS
            await page.evaluate(f"window.location.href = '{GET_QUOTE_URL}'")
            await page.wait_for_timeout(5000)

            # Find iframe again
            iframes = page.frames
            for f in iframes:
                try:
                    if "agent_home" in f.url:
                        frame = f
                        # Launch EQ
                        has_eq = await frame.evaluate("""() => {
                            const forms = document.querySelectorAll('form');
                            for (const form of forms) {
                                const ch = form.querySelector('input[name="channelType"]');
                                if (ch && ch.value === 'EQ') return true;
                            }
                            return false;
                        }""")
                        if has_eq:
                            print("  Found EQ form, launching...")
                            await frame.evaluate("""() => {
                                const forms = document.querySelectorAll('form');
                                for (const form of forms) {
                                    const ch = form.querySelector('input[name="channelType"]');
                                    if (ch && ch.value === 'EQ') {
                                        form.submit();
                                        return;
                                    }
                                }
                            }""")
                            await page.wait_for_timeout(5000)

                            for p in ctx.pages:
                                try:
                                    await p.wait_for_timeout(1000)
                                    result = await p.evaluate(SCAN_FORM_JS)
                                    fields_count = len(result.get("fields", []))
                                    if fields_count > 0:
                                        print(f"  EQ Fields: {fields_count}")
                                        yaml_data = scan_result_to_yaml(
                                            result, "great_eastern", "EQ", "quote_form"
                                        )
                                        profile_path = os.path.expanduser(
                                            "~/InsureDesk/profiles/eq_quote.yaml"
                                        )
                                        write_yaml(yaml_data, profile_path)
                                        for f in result.get("fields", [])[:15]:
                                            req = "🔴" if f.get("required") else "⚪"
                                            print(f"    {req} {f.get('key', '?'):25s} {f.get('type', '?'):10s} label='{f.get('label', '')[:30]}'")
                                        break
                                except:
                                    pass
                except:
                    pass
        except Exception as e:
            print(f"  Error scanning EQ: {e}")

        print(f"\n{'=' * 60}")
        print("C1 Complete! Profiles saved to profiles/")
        print(f"{'=' * 60}")

    return True


if __name__ == "__main__":
    asyncio.run(main())
