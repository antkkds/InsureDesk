# InsureDesk — Product Specification

> **Insurance Agent's AI-powered Desktop Workspace.**
> Powered by [UIP-AI](https://github.com/antkk/UIP-AI).

---

## 1. Product Positioning

### What InsureDesk IS

- A **local desktop application** for insurance agents and brokers
- An **AI-powered workspace** that automates portal data entry, document management, and customer communication
- A **client of UIP-AI** — connects to UIP-AI for AI capabilities (assistant, memory, tool execution)

### What InsureDesk IS NOT

- ❌ NOT a replacement for insurance company portals
- ❌ NOT an ERP or core insurance system
- ❌ NOT a CRM (it has a lightweight customer workspace, not a full CRM)
- ❌ NOT part of UIP-AI's codebase (separate project, separate repo)
- ❌ NOT a SaaS platform (it's installed on the agent's laptop)

### Brand Hierarchy

```
UIP-AI (Platform)
    ↓ powers
InsureDesk (Product)
    ↓ contains
Marry (AI Assistant — user-named)
```

---

## 2. Target Users

| User | Description | Pain Point |
|------|-------------|------------|
| **Insurance Agent** | Sells policies to individuals | Manual data entry across multiple insurer portals |
| **Insurance Broker** | Handles corporate clients | Tracking renewals, claims, and policy changes |
| **Agency Manager** | Manages a team of agents | Visibility into team activities and client status |

Primary market: **Malaysia** (multi-lingual: English, Malay, Chinese)
Secondary market: Singapore, Indonesia, Thailand

---

## 3. Capabilities

> Organized by capability area — not chronological PI phases.
> Full detail in [Policy Intelligence](docs/products/insuredesk/policy-intelligence.md)

| Capability | Description |
|------------|-------------|
| **Document Intelligence** | PDF OCR, policy parsing, knowledge storage, semantic search |
| **Portfolio & Lifecycle** | Customer workspace, cross-company portfolio, lifecycle tracking |
| **Business Intelligence** | Health metrics, risk scoring, AI review reports |
| **Team Collaboration** | Agency management, work assignment, knowledge sharing |
| **Predictive Intelligence** | Family context, life events, predictive rules, AI planner |
| **Autonomous Operations** | Goal engine, proactive opportunities, daily reviews |
| **Integration** | External CRM, calendar, accounting connectors |
| **Portal Automation** | Browser engine, form interaction, insurer adapters |

---

## 4. Architecture (High-Level)

> Full architecture in [Architecture Overview](docs/architecture/overview.md)

```
Desktop Shell (PySide6)
    → Service Layer
        → Portal Adapter Layer
            → Browser Engine (Playwright / WebEngine)
                → Insurer Portals + UIP-AI
```

**Key principles:**
- UI never calls browser directly
- Each portal adapter is independent
- Local-first storage (SQLite + filesystem)
- UIP-AI is the ONLY brain (no local OCR/LLM)

---

## 5. Productization

> Full strategy in [Product Plan](PRODUCT_PLAN.md)

| Phase | Engine | Dependencies | Users |
|-------|--------|-------------|-------|
| Dev/Test | Playwright | pip install (dev machine) | Engineers |
| MVP | Qt WebEngine | PySide6 only | Pilot customers |
| Final | PyInstaller .exe | Windows 10/11 only | All customers |

**Customer machine needs:** Windows 10/11 only. No Python, no Playwright, no Chrome required.

---

## 6. Status

- **Generation 1 Development:** ✅ COMPLETE (PI-1 → PI-20, 207 tests)
- **Portal Validation:** 🔄 IN PROGRESS (Great Eastern live test)
- **Windows Packaging:** 📋 PLANNED
- **Pilot:** 📋 PLANNED

See [Roadmap](docs/products/insuredesk/roadmap.md) and [PILOT Checklist](docs/products/insuredesk/PILOT.md).
