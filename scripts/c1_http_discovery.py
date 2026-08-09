"""C1 — Real Portal Discovery: Scan IFE/EQ forms via HTTPX.

The Electron/Dyad CDP doesn't support navigation to GEGLink's internal pages.
Instead, we use httpx to:
1. Login via POST
2. Accept PDPA
3. Scrape Get Quote page
4. Extract IFE/EQ launch URL
5. Fetch the external quote form HTML directly
6. Parse HTML form fields
"""

import asyncio
import httpx
import re
import yaml
import os
from datetime import datetime
from bs4 import BeautifulSoup

USERNAME = "fhl8125"
PASSWORD = "Uiop234<"

BASE_URL = "https://geglink.greateasterngeneral.com"
LOGIN_URL = f"{BASE_URL}/geglink/userlogin.html"
LOGIN_ACTION = f"{BASE_URL}/geglink/submitlogin.html"
DASHBOARD_URL = f"{BASE_URL}/oacportal/group/geglink/home"
GET_QUOTE_URL = f"{BASE_URL}/oacportal/group/geglink/get-quote"


def parse_form_fields(html, source_url=""):
    """Parse form fields from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, 'html.parser')
    fields = []
    field_index = 0

    # Find all input, select, textarea elements
    for el in soup.find_all(['input', 'select', 'textarea']):
        tag = el.name
        if tag == 'input':
            input_type = el.get('type', 'text').lower()
            if input_type in ('hidden', 'submit', 'button', 'image'):
                continue
        
        name = el.get('name', '') or ''
        el_id = el.get('id', '') or ''
        placeholder = el.get('placeholder', '') or ''
        
        # Generate key
        key = name or el_id or f"field_{field_index}"
        
        # Find label
        label = ''
        if el_id:
            label_el = soup.find('label', attrs={'for': el_id})
            if label_el:
                label = label_el.get_text(strip=True)
        if not label:
            # Check parent label
            parent = el.find_parent('label')
            if parent:
                label = parent.get_text(strip=True)
        if not label:
            # Check aria-label
            label = el.get('aria-label', '') or ''
        if not label:
            label = placeholder
        
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
                options.append({
                    'value': opt.get('value', ''),
                    'label': opt.get_text(strip=True),
                })
        
        # Required
        required = el.has_attr('required') or el.get('aria-required', '') == 'true'
        
        # Validation
        min_length = el.get('minlength')
        max_length = el.get('maxlength')
        pattern = el.get('pattern', '')
        
        # Generate CSS selectors
        candidates = {}
        if el_id:
            candidates[f"#{el_id}"] = 95
        if name:
            candidates[f"[name='{name}']"] = 82
        if el_id and name:
            candidates[f"#{el_id}"] = 95
        
        best_selector = list(candidates.keys())[0] if candidates else tag
        
        field = {
            'key': key,
            'label': label,
            'selector': best_selector,
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
        if pattern:
            field['pattern'] = pattern
        
        fields.append(field)
        field_index += 1

    # Detect form actions/buttons
    buttons = []
    for btn in soup.find_all(['button', 'input']):
        if btn.name == 'input':
            btn_type = btn.get('type', '').lower()
            if btn_type not in ('submit', 'button'):
                continue
            btn_text = btn.get('value', '') or ''
        else:
            btn_text = btn.get_text(strip=True) or btn.get('value', '') or ''
        
        if not btn_text:
            continue
        
        buttons.append({
            'key': btn_text.lower().replace(' ', '_'),
            'text': btn_text,
            'selector': f"[value='{btn.get('value', '')}']" if btn.get('value') else '',
            'type': btn.name,
        })

    return {
        'fields': fields,
        'actions': buttons,
        'url': source_url,
    }


def write_profile(data, channel, output_dir="profiles"):
    """Write profile YAML to file."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    
    pages = {}
    for page_name, page_data in data.items():
        elements = {}
        for f in page_data.get('fields', []):
            field_data = {k: v for k, v in f.items() if k != 'key'}
            elements[f['key']] = field_data
        
        page_entry = {
            'description': f"{page_name} form page",
            'url_pattern': page_data.get('url', ''),
            'elements': elements,
        }
        if page_data.get('actions'):
            page_entry['actions'] = page_data['actions']
        pages[page_name] = page_entry

    profile = {
        'version': '1.0',
        'portal': 'great_eastern',
        'quote_channel': channel,
        'captured_at': now,
        'pages': pages,
    }

    path = os.path.expanduser(f"~/{output_dir}/{channel.lower()}_quote.yaml")
    with open(path, 'w') as f:
        yaml.dump(profile, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"  ✓ Saved {len(pages)} pages, {sum(len(p.get('elements', {})) for p in pages.values())} fields to {path}")
    return path


async def main():
    print("=" * 60)
    print("C1 — Real Portal Discovery (HTTPX)")
    print(f"  Target: GEGLink IFE / EQ")
    print(f"  Time:   {datetime.utcnow().isoformat()}")
    print("=" * 60)

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        # 1. Get login page (init cookies)
        print("\n1. Initializing session...")
        resp = await client.get(LOGIN_URL)
        print(f"   Cookies: {len(client.cookies)}")

        # 2. POST login
        print("\n2. Logging in...")
        resp = await client.post(
            LOGIN_ACTION,
            data={"oac_username": USERNAME, "oac_intpwd": PASSWORD},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": BASE_URL,
                "Referer": LOGIN_URL,
            }
        )
        print(f"   Status: {resp.status_code}, URL: {resp.url}")

        # 3. Check if PDPA
        if "pdpa" in str(resp.url).lower():
            print("\n3. Accepting PDPA terms...")
            # PDPA is accepted by POST decl_eparid=DONE to home URL
            resp = await client.post(
                f"{BASE_URL}/oacportal/group/geglink/home",
                data={"decl_eparid": "DONE"},
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Content-Type": "application/x-www-form-urlencoded",
                }
            )
            print(f"   PDPA accept: Status={resp.status_code}, URL: {resp.url}")
            
            # Verify we're on dashboard
            if "pdpa" in str(resp.url).lower():
                print("   ❌ Still on PDPA page!")
                return False
            print("   ✓ PDPA accepted, on dashboard")
        
        # 4. Navigate to Get Quote page
        print(f"\n4. Fetching Get Quote page...")
        resp = await client.get(GET_QUOTE_URL)
        print(f"   Status: {resp.status_code}, URL: {resp.url}")
        
        # Check if still on login page
        if "login" in str(resp.url).lower():
            print("   ❌ Still on login page!")
            return False
        
        # 5. Parse Get Quote page - find IFE/EQ links
        print("\n5. Analyzing Get Quote page...")
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find iframe or links
        iframes = soup.find_all('iframe')
        print(f"   Iframes found: {len(iframes)}")
        for iframe in iframes:
            src = iframe.get('src', '')
            print(f"     - {src[:100]}")
        
        # Find all forms
        forms = soup.find_all('form')
        print(f"   Forms found: {len(forms)}")
        for form in forms:
            action = form.get('action', '')
            channel_input = form.find('input', {'name': 'channelType'})
            if channel_input:
                channel = channel_input.get('value', '')
                print(f"     - Channel: {channel}, Action: {action}")
        
        # 6. Launch IFE
        print(f"\n6. Launching IFE...")
        for form in soup.find_all('form'):
            action = form.get('action', '')
            channel_input = form.find('input', {'name': 'channelType'})
            if channel_input and channel_input.get('value') == 'IFE':
                # Get ALL inputs in this form
                form_data = {}
                for inp in form.find_all('input'):
                    name = inp.get('name', '')
                    value = inp.get('value', '')
                    if name:
                        form_data[name] = value
                
                # Submit the form
                print(f"   Form action: {action}")
                print(f"   Form data: {form_data}")
                
                if action.startswith('/'):
                    action_url = f"{BASE_URL}{action}"
                elif action.startswith('http'):
                    action_url = action
                else:
                    action_url = f"{BASE_URL}/{action}"
                
                resp = await client.post(action_url, data=form_data)
                print(f"   IFE launch: Status={resp.status_code}, URL: {resp.url}")
                
                # Parse IFE form
                print(f"\n7. Scanning IFE form fields...")
                result = parse_form_fields(resp.text, str(resp.url))
                print(f"   Found {len(result['fields'])} fields, {len(result['actions'])} actions")
                
                # Print first 15 fields
                for f in result['fields'][:20]:
                    req = "🔴" if f['required'] else "⚪"
                    print(f"     {req} {f['key'][:25]:25s} {f['field_type']:10s} label='{str(f.get('label', ''))[:30]}'")
                if len(result['fields']) > 20:
                    print(f"     ... and {len(result['fields']) - 20} more fields")
                
                write_profile({'quote_form': result}, 'IFE')
                break
        
        # 7. Launch EQ
        print(f"\n8. Launching EQ...")
        for form in soup.find_all('form'):
            action = form.get('action', '')
            channel_input = form.find('input', {'name': 'channelType'})
            if channel_input and channel_input.get('value') == 'EQ':
                form_data = {}
                for inp in form.find_all('input'):
                    name = inp.get('name', '')
                    value = inp.get('value', '')
                    if name:
                        form_data[name] = value
                
                if action.startswith('/'):
                    action_url = f"{BASE_URL}{action}"
                elif action.startswith('http'):
                    action_url = action
                else:
                    action_url = f"{BASE_URL}/{action}"
                
                resp = await client.post(action_url, data=form_data)
                print(f"   EQ launch: Status={resp.status_code}, URL: {resp.url}")
                
                print(f"\n9. Scanning EQ form fields...")
                result = parse_form_fields(resp.text, str(resp.url))
                print(f"   Found {len(result['fields'])} fields, {len(result['actions'])} actions")
                
                for f in result['fields'][:15]:
                    req = "🔴" if f['required'] else "⚪"
                    print(f"     {req} {f['key'][:25]:25s} {f['field_type']:10s} label='{str(f.get('label', ''))[:30]}'")
                
                write_profile({'quote_form': result}, 'EQ')
                break

    print(f"\n{'=' * 60}")
    print("C1 Complete!")
    print(f"{'=' * 60}")
    return True


if __name__ == "__main__":
    asyncio.run(main())
