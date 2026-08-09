"""Fetch IFE (Fire Quote) and EQ (House Quote) forms and scan them."""
import asyncio
import httpx
import yaml
import os
from datetime import datetime
from bs4 import BeautifulSoup

USERNAME = "fhl8125"
PASSWORD = "Uiop234<"
BASE_URL = "https://geglink.greateasterngeneral.com"

FIRE_QUOTE_URL = f"{BASE_URL}/geglink/getquote/fireQuote.html"
HOUSE_QUOTE_URL = f"{BASE_URL}/geglink/getquote/houseQuote.html"

LOGIN_URL = f"{BASE_URL}/geglink/userlogin.html"
LOGIN_ACTION = f"{BASE_URL}/geglink/submitlogin.html"


def parse_html_form_fields(html, source_url=""):
    """Parse form fields from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    fields = []
    field_index = 0

    for el in soup.find_all(['input', 'select', 'textarea']):
        tag = el.name
        if tag == 'input':
            input_type = (el.get('type', '') or 'text').lower()
            if input_type in ('hidden', 'submit', 'button', 'image', 'reset'):
                continue

        name = el.get('name', '') or ''
        el_id = el.get('id', '') or ''
        placeholder = el.get('placeholder', '') or ''
        el_class = el.get('class', [])
        if isinstance(el_class, str):
            el_class = [el_class]

        key = name or el_id or f"field_{field_index}"

        # Label detection
        label = ''
        if el_id:
            label_el = soup.find('label', attrs={'for': el_id})
            if label_el:
                label = label_el.get_text(strip=True)
        if not label:
            parent = el.find_parent('label')
            if parent:
                label = parent.get_text(strip=True)
        if not label:
            label = el.get('aria-label', '') or ''
        if not label:
            # Try previous sibling text
            prev = el.find_previous_sibling(string=True)
            if prev:
                label = prev.strip()

        # Field type
        field_type = 'text'
        if tag == 'select':
            field_type = 'select'
        elif tag == 'textarea':
            field_type = 'textarea'
        elif tag == 'input':
            field_type = input_type

        # Options for select
        options = []
        if tag == 'select':
            for opt in el.find_all('option'):
                val = opt.get('value', '')
                options.append({
                    'value': val or opt.get_text(strip=True),
                    'label': opt.get_text(strip=True),
                })

        # Required
        required = el.has_attr('required') or el.get('aria-required', '') == 'true'
        # Also check if the label or TD has an asterisk
        parent_td = el.find_parent('td')
        if parent_td and '*' in parent_td.get_text():
            required = True

        # Validation
        min_length = el.get('minlength')
        max_length = el.get('maxlength')
        max_val = el.get('max')
        min_val = el.get('min')
        pattern = el.get('pattern', '')

        field = {
            'key': key,
            'label': label or placeholder or key,
            'selector': f"#{el_id}" if el_id else f"[name='{name}']" if name else tag,
            'tag': tag,
            'field_type': field_type,
            'required': required,
            'placeholder': placeholder,
        }
        if options:
            field['options'] = options
        if min_length:
            field['min_length'] = int(min_length)
        if max_length:
            field['max_length'] = int(max_length)
        if max_val:
            field['max_value'] = str(max_val)
        if min_val:
            field['min_value'] = str(min_val)
        if pattern:
            field['pattern'] = pattern

        fields.append(field)
        field_index += 1

    # Detect buttons
    buttons = []
    for btn in soup.find_all(['button', 'input']):
        if btn.name == 'input':
            btn_type = (btn.get('type', '') or '').lower()
            if btn_type not in ('submit', 'button'):
                continue
            btn_text = btn.get('value', '') or ''
        else:
            btn_text = btn.get_text(strip=True) or btn.get('value', '') or ''

        if not btn_text:
            continue

        buttons.append({
            'key': btn_text.lower().replace(' ', '_').replace('/', '_'),
            'text': btn_text.strip(),
            'selector': f"[value='{btn.get('value', '')}']" if btn.get('value') else '',
            'type': btn.name,
        })

    return {'fields': fields, 'actions': buttons, 'url': source_url}


def write_profile(result, channel):
    """Write profile YAML."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    elements = {}
    for f in result['fields']:
        d = dict(f)
        k = d.pop('key')
        elements[k] = d

    page = {
        'description': f'{channel} quote form page',
        'url_pattern': result['url'],
        'elements': elements,
    }
    if result['actions']:
        page['actions'] = [{'key': a['key'], 'selector': a['selector'], 'type': a['type']} for a in result['actions']]

    profile = {
        'version': '1.0',
        'portal': 'great_eastern',
        'quote_channel': channel,
        'captured_at': now,
        'pages': {'quote_form': page},
    }

    path = os.path.expanduser(f"~/InsureDesk/profiles/{channel.lower()}_quote.yaml")
    with open(path, 'w') as f:
        yaml.dump(profile, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"  ✓ Saved to {path}")
    return path


async def main():
    print("=" * 60)
    print("C1 — Real Portal Discovery (HTTPX)")
    print(f"  Time: {datetime.utcnow().isoformat()}")
    print("=" * 60)

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        # Login
        print("\n1. Logging in...")
        await client.get(LOGIN_URL)
        resp = await client.post(
            LOGIN_ACTION,
            data={"oac_username": USERNAME, "oac_intpwd": PASSWORD},
            headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"}
        )

        # PDPA
        if "pdpa" in str(resp.url).lower():
            resp = await client.post(
                f"{BASE_URL}/oacportal/group/geglink/home",
                data={"decl_eparid": "DONE"},
                headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"}
            )
        print(f"   Logged in: {resp.url}")

        # --- IFE: Fire Quotation ---
        print(f"\n2. Fetching IFE (Fire Quote) form...")
        resp = await client.get(FIRE_QUOTE_URL)
        print(f"   Status: {resp.status_code}, URL: {resp.url}")

        if resp.status_code == 200 and 'login' not in str(resp.url).lower():
            result = parse_html_form_fields(resp.text, str(resp.url))
            print(f"   Found {len(result['fields'])} fields, {len(result['actions'])} actions")

            required = [f for f in result['fields'] if f['required']]
            print(f"   Required: {len(required)}")

            for f in result['fields'][:25]:
                req = "🔴" if f['required'] else "⚪"
                label = str(f.get('label', ''))[:35]
                print(f"     {req} {f['key'][:25]:25s} {f['field_type']:10s} '{label}'")
            if len(result['fields']) > 25:
                print(f"     ... and {len(result['fields']) - 25} more fields")

            write_profile(result, 'IFE')
        else:
            print(f"   ❌ Failed: status={resp.status_code}, redirected to login: {'login' in str(resp.url).lower()}")

        # --- EQ: Houseowner/Householder Quotation ---
        print(f"\n3. Fetching EQ (Houseowner Quote) form...")
        resp = await client.get(HOUSE_QUOTE_URL)
        print(f"   Status: {resp.status_code}, URL: {resp.url}")

        if resp.status_code == 200 and 'login' not in str(resp.url).lower():
            result = parse_html_form_fields(resp.text, str(resp.url))
            print(f"   Found {len(result['fields'])} fields, {len(result['actions'])} actions")

            required = [f for f in result['fields'] if f['required']]
            print(f"   Required: {len(required)}")

            for f in result['fields'][:25]:
                req = "🔴" if f['required'] else "⚪"
                label = str(f.get('label', ''))[:35]
                print(f"     {req} {f['key'][:25]:25s} {f['field_type']:10s} '{label}'")
            if len(result['fields']) > 25:
                print(f"     ... and {len(result['fields']) - 25} more fields")

            write_profile(result, 'EQ')
        else:
            print(f"   ❌ Failed: redirected to login")

    print(f"\n{'=' * 60}")
    print("C1 Complete!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
