# Browser Automation

> Dual-engine architecture: Playwright (dev) + QtWebEngine (production).

## Architecture

```
PortalAdapter
    ↓ uses
FormEngine (shared interaction layer)
    ↓ delegates to
BrowserEngine (abstract interface)
    ├── PlaywrightDriver (dev) — visible Chromium, CDP
    └── QtDriver (prod) — embedded Qt WebEngine
```

All browser interactions go through FormEngine → BrowserEngine. Adapters never call browser APIs directly.

## Engine Comparison

| | PlaywrightDriver | QtDriver |
|---|---|---|
| **Purpose** | Development / testing | Customer production |
| **Dependencies** | playwright + chromium (~300MB) | PySide6.QtWebEngine (bundled) |
| **Browser** | External Chrome window | Embedded in InsureDesk window |
| **Customer install** | ❌ Too complex | ✅ Single .exe, nothing extra |
| **Selectors** | Standard CSS | Standard CSS (JS injection) |

## BrowserEngine Interface

`src/browser/engine.py` — Abstract base class defining all browser operations:

- `start()` / `stop()` — Lifecycle
- `navigate(url)` — Page navigation with timeout
- `click(selector)`, `fill(selector, value)` — Element interaction
- `select_option(selector, value)` — Dropdowns
- `get_text(selector)`, `get_attribute(selector, attr)` — Read page
- `is_visible(selector)`, `wait_for_selector(selector)` — Wait for elements
- `get_cookies()` / `set_cookies(cookies)` — Session persistence
- `evaluate(script)` — JavaScript execution
- `screenshot()` — Page capture

## FormEngine

`src/portal/form_engine.py` — Shared form interaction layer.

- `fill_text(selector, value)` — Human-like typing
- `click(selector)` — Click with human delays
- `select_option(selector, value)` — Dropdown selection
- `check(selector, checked)` — Checkbox toggle
- `upload_file(selector, path)` — File upload
- `wait_for_selector(selector)` — Element wait

All methods work with either BrowserEngine backend. No adapter code changes needed when switching engines.

## Portal Mapping (YAML)

`portals/<adapter>.yaml` — Per-insurer selector configuration.

```yaml
portal:
  name: "Great Eastern"
  short_name: "GE"
  base_url: "https://iconnect.greateasternlife.com"
  login_url: "https://iconnect.greateasternlife.com/login"
  adapter: "great_eastern"

selectors:
  login:
    username: "#username"
    password: "#password"
    submit: "button[type='submit']"
  dashboard:
    welcome_message: ".welcome-message"
    logout_link: "a:has-text('Logout')"
  policy_search:
    nav_link: "a:has-text('Policy')"
    search_input: "input[name='policyNo']"
  claims:
    nav_link: "a:has-text('Claims')"
    submit_button: "button:has-text('Submit')"
```

When an insurer changes their UI, update the YAML only — no code changes.

## Session Manager

`src/portal/session.py` — Cookie persistence with login detection.

- `save_cookies(adapter, cookies)` — Persist to disk
- `load_cookies(adapter)` — Restore session
- `check_validity(adapter)` — Detect login page vs dashboard
- `list_sessions()` — All saved sessions

## Factory: Engine Selection

`src/browser/__init__.py` — Auto-selects best engine:

```python
from src.browser import create_browser_engine

# Auto: WebEngine (prod) → Playwright (dev)
engine = create_browser_engine()

# Specific
engine = create_browser_engine(prefer="playwright")
engine = create_browser_engine(prefer="webengine")
```

## Limitations (WebEngine vs Playwright)

| Feature | Playwright | WebEngine | Production Solution |
|---------|-----------|-----------|-------------------|
| fill | ✅ page.type() | ✅ JS injection | OK |
| click | ✅ page.click() | ✅ JS click() | OK |
| select | ✅ page.select_option() | ✅ JS value set | OK |
| upload | ✅ set_input_files() | ❌ Security limit | Native file dialog |
| checkbox | ✅ is_checked() | ✅ JS checked | OK |
| screenshot | ✅ page.screenshot() | ✅ widget.grab() | OK |
| cookies | ✅ context.cookies() | ✅ document.cookie | OK (httpOnly limited) |
| iframes | ✅ frame() | ❌ | Needs special handling |
