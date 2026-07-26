# InsureDesk

> **Insurance Agent's AI-powered Desktop Workspace.**
> Powered by [UIP-AI](https://github.com/antkk/UIP-AI).

## Overview

InsureDesk is a local desktop application for insurance agents and brokers in Malaysia. It automates portal data entry, document management, and customer communication across multiple insurer portals (Great Eastern, Allianz, AIA).

### Brand Hierarchy

```
UIP-AI (Platform)
    ↓ powers
InsureDesk (Product)
    ↓ contains
Marry (AI Assistant — user-named)
```

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | Dual-engine design, data flow, tech stack |
| [Browser Automation](browser-automation.md) | BrowserEngine abstraction, FormEngine, Session, Mapping |
| [Portal Adapters](portal-adapters.md) | Per-insurer adapter contracts (GE, Allianz, AIA) |
| [Policy Intelligence](policy-intelligence.md) | PI-1~20 organized by capability |
| [Roadmap](roadmap.md) | Completed phases + next steps |
| [PILOT](PILOT.md) | Real user testing checklist |
| [Product Plan](../../../PRODUCT_PLAN.md) | Productization strategy |
| [Test Notes](../../../test_notes.md) | Live testing guide |

## Quick Start

```bash
cd ~/InsureDesk
source venv/bin/activate
python test_portal_live.py          # Offline checks
python test_portal_live.py great_eastern  # Live browser test
```

## Target Users

- **Insurance Agent** — Sells policies, needs multi-portal automation
- **Insurance Broker** — Corporate clients, renewal/claims tracking
- **Agency Manager** — Team visibility and activity monitoring

Primary market: **Malaysia** (English, Malay, Chinese)
