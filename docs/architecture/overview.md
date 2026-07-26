# Architecture

> Platform-level design: UIP-AI runtime, Bridge Protocol, Desktop shell.

## Layer Diagram

```
┌──────────────────────────────────────────────────┐
│              Desktop Shell (PySide6)              │
│  Dashboard │ Customers │ Documents │ ...          │
└───────────────────────┬──────────────────────────┘
                        │ calls
┌───────────────────────▼──────────────────────────┐
│                 Service Layer                      │
│  CustomerService │ DocumentService │ Bridge       │
└───────────────────────┬──────────────────────────┘
                        │ calls
┌───────────────────────▼──────────────────────────┐
│              Portal Adapter Layer                  │
│  BaseAdapter │ GreatEastern │ Allianz │ AIA       │
└───────────────────────┬──────────────────────────┘
                        │ uses
┌───────────────────────▼──────────────────────────┐
│              Browser Engine                        │
│  PlaywrightDriver / QtDriver / FormEngine  │
└───────────────────────┬──────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────┐
│              External Systems                      │
│  Insurer Portals │ UIP-AI │ Local Filesystem      │
└──────────────────────────────────────────────────┘
```

## Key Principles

1. **UI never calls browser directly** — always through Service → Adapter → Engine
2. **Each Portal Adapter is independent** — no shared state between insurers
3. **Local-first storage** — SQLite for data, filesystem for documents
4. **UIP-AI is the ONLY brain** — no local OCR, no local LLM. InsureDesk uploads PDFs → UIP-AI processes → returns structured JSON

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Desktop UI | PySide6 (Qt for Python) |
| Browser Automation | PlaywrightDriver (dev) / QtDriver (prod) |
| Local Database | SQLite via SQLAlchemy |
| Document Storage | Local filesystem (~/InsureDesk/documents/) |
| AI Backend | UIP-AI via Bridge Protocol |
| Portal Config | YAML mapping per insurer |

## Desktop Shell

`src/desktop/` — PySide6 main window

- Navigation top bar: Dashboard, Customers, Documents, Companies, Assistant, Settings
- Sidebar alternative for reduced top-level tabs
- Qt stylesheet for professional appearance

## Service Layer

`src/customers/`, `src/documents/`, `src/bridge/` — Business logic services

- CustomerService: CRUD + search + policy linking
- DocumentService: upload, preview, tag, search
- BridgeService: UIP-AI connection management
- All services use SQLAlchemy for persistence

## Portal Adapter Layer

`src/portals/base.py` — Abstract adapter + concrete implementations

- Base class defines: login, logout, search_policy, get_policy_details, submit_claim, renew_policy, upload_document
- Each adapter auto-loads its YAML mapping
- FormEngine for all browser interactions
- SessionManager for cookie persistence

## Browser Engine

`src/browser/` — Abstract + two implementations

- BrowserEngine ABC: 30+ methods for browser control
- PlaywrightDriver: development/testing (requires Playwright install)
- QtDriver: production (Qt WebEngine, ships with PySide6)
- Factory function auto-selects based on availability

## Data Flow

```
Agent Action → PySide6 UI → Service Layer → PortalAdapter
    → FormEngine → BrowserEngine → HTTP(S) → Insurer Portal
    ← HTML/JSON ←
    ↓ Parse
    SQLite ← structured data
    ↓
UI updates
```

## Bridge Protocol

InsureDesk ↔ UIP-AI communication:

- Upload: PDF document → HTTP POST → UIP-AI OCR + LLM → structured JSON
- Execute: Action request → HTTP POST → UIP-AI tool execution → result
- Query: Natural language → HTTP POST → Assistant response

## Session Architecture

```
InsureDesk Session
├── Browser Sessions (per portal)
│   ├── Great Eastern → cookies → ~/InsureDesk/sessions/great_eastern.json
│   ├── Allianz      → cookies → ~/InsureDesk/sessions/allianz.json
│   └── AIA          → cookies → ~/InsureDesk/sessions/aia.json
├── Portal Sessions (per adapter)
│   ├── Login state
│   └── Activity timeout
└── UIP-AI Session
    ├── Auth token
    └── Connection state
```

## Testing Strategy

| Level | Tool | Scope |
|-------|------|-------|
| Unit | pytest | Models, services, mapping, session |
| Integration | pytest + Playwright | Portal adapter flows |
| E2E | pytest + real browser | Full login → search → claim |
| Manual | PySide6 window | UI on real Windows machine |

Current: **207 tests** covering all capability areas.
