# Policy Intelligence

> All PI-1~20 work organized by capability area, not chronological phase number.

## Capability Map

```
Policy Intelligence
├── Document Intelligence    — OCR, parsing, knowledge store
├── Portfolio & Lifecycle    — Customer policies, lifecycle events
├── Business Intelligence    — Health metrics, risk scoring, AI review
├── Team Collaboration       — Agency management, assignments
├── Predictive Intelligence  — Family context, life events, predictions
├── Autonomous Operations    — Goal engine, proactive reviews, improvement
├── Integration              — External connectors, CRM, calendar
└── Portal Automation        — Browser engines, adapters, session management
```

---

## Document Intelligence

**Files:** `src/documents/`, `src/knowledge/`

### OCR & Parsing
- PDF/scanned document text extraction via UIP-AI Bridge
- Structured policy data (coverage, premium, exclusions, terms)
- PolicyParseRecord in SQLite

### Knowledge Store
- `KnowledgeLibrary` — multi-type entries (POLICY_DOCUMENT, CLAIM_GUIDE, PRODUCT_INFO, REGULATION, TIP)
- Semantic retrieval across all documents
- Cross-search: `search_knowledge(query, type_filter, customer_id)`

### Explainable Reasoning
- When answering policy questions, cite source documents
- Confidence scoring per answer
- Reference trail back to original policy text

**Tests:** `tests/test_knowledge.py` — 28 tests

---

## Portfolio & Lifecycle

**Files:** `src/customers/`, `src/bridge/`

### Customer Workspace
- Profile: name, phone, IC (Malaysia), email, language preference
- Linked policies across multiple insurers
- Notes and communication history

### Policy Portfolio
- Aggregate view: active/lapsed/claim policies per customer
- Cross-company portfolio (GE + Allianz + AIA)
- Bridge Portfolio: consolidated view via UIP-AI

### Policy Lifecycle
- Status tracking: active → renewal_due → lapsed → reinstated
- Configurable lifecycle stages per insurer
- Version tracking for policy changes

### Customer Financial Profile
- Premium history and payment patterns
- Coverage gap analysis
- Financial health indicators

**Tests:** `tests/test_bridge_portfolio.py` — 25 tests

---

## Business Intelligence

**Files:** `src/integrations/business_health.py`

### Business Health Engine
7 metrics + trend analysis:
- Renewal Rate (percentage, trend)
- Claims Ratio
- Customer Lifetime Value
- Policy Growth Rate
- Overdue Task Count
- Customer Engagement Score
- Revenue Per Customer

### Risk & Opportunity Engine
- Auto-detect at-risk renewals (30, 14, 7 days out)
- Coverage gap identification
- Upsell opportunity scoring

### AI Business Review
- Multi-language reports (English, Malay, Chinese)
- Daily/weekly/monthly summaries
- Generated via UIP-AI Bridge

**Tests:** `tests/test_integrations.py` — 35 tests

---

## Team Collaboration

**Files:** `src/teams/`

### Team Model
- Teams with multiple agents
- Manager/Agent dual role
- Team dashboard with performance metrics

### Work Assignment
- `AssignmentService` — create, assign, complete tasks
- Auto-select least-loaded agent
- Workload balancing

### Knowledge Sharing
- Create, search, update, delete team knowledge entries
- Cross-team search permissions

**Tests:** `tests/test_team_collaboration.py` — 40 tests

---

## Predictive Intelligence

**Files:** `src/predictive/`, `src/family/`

### Family Context
- `FamilyMember` — spouse, children, parents, siblings
- `Household` — aggregate family view
- `LifeEvent` — marriage, birth, education, retirement, death

### Customer Health Score
- Individual + family context weighted score
- Policy adequacy ratio (coverage vs needs)
- Engagement recency factor

### Predictive Rules Engine
- Rule-based opportunity detection:
  - Child turns 18 → education policy opportunity
  - Marriage → joint policy opportunity
  - New baby → medical/education policy
  - Approaching retirement → annuity opportunity
  - Policy expiry in 30 days → renewal reminder

### AI Daily Planner
- Prioritized task list from rules engine
- Customer-specific action items
- Agent daily briefing

**Tests:** `tests/test_predictive.py` — 32 tests

---

## Autonomous Operations

**Files:** `src/autonomous/`

### Goal Engine
- Business targets per metric (renewal rate, etc.)
- Current value + target + status (on_track / critical / behind)
- Auto-recompute on changes

### Proactive Opportunity Engine
- Scan for renewal risks, coverage gaps, life events
- Auto-create action items
- Requires approval for high-impact actions
- List pending for agent review

### Autonomous Review Cycle
- Daily morning brief with goal status
- Urgent item highlighting
- Personalized suggestions
- On-demand generation

### Continuous Improvement
- Track action outcomes (success/fail)
- Calculate success rate per action type
- Auto-summarize improvement trends

### Home Dashboard
- Autonomous Review card on main dashboard
- Quick-glance goal status
- Pending actions count

**Tests:** `tests/test_autonomous.py` — 22 tests

---

## Integration

**Files:** `src/integrations/`

### External CRM Connector
- CSV import/export connector
- Google Sheets connector (via API)
- Generic connector framework for future CRMs

### Calendar Integration
- Sync with external calendars
- Event creation from policy dates
- Renewal reminder scheduling

### Accounting Integration
- Premium reconciliation
- Commission tracking
- Payment status monitoring

**Tests:** Part of `tests/test_integrations.py`

---

## Portal Automation

**Files:** `src/browser/`, `src/portal/`, `src/portals/`

### BrowserEngine Abstraction
- `BrowserEngine` ABC — 30+ methods
- `PlaywrightDriver` — dev/testing (requires Playwright)
- `QtDriver` — production (Qt WebEngine, no extra deps)
- `create_browser_engine()` factory — auto-select

### Portal Mapping
- YAML-based selector configs per insurer
- Field groups: login, dashboard, policy_search, claims, documents, renewal, customer
- When insurer changes UI: update YAML only

### FormEngine
- Shared form interaction: fill, click, select, upload, wait
- Human-like delays for bot detection avoidance
- Works with any BrowserEngine backend

### Session Management
- Cookie persistence to disk
- Login detection (dashboard vs login page)
- Automatic session restore on reconnect

### Portal Inspector
- Dev tool to capture selectors from live pages
- Generate YAML config automatically
- Useful for initial adapter development

**Tests:** `tests/test_portal.py` — 25 tests

---

## Test Summary

| Area | Tests |
|------|-------|
| Portal Infrastructure | 25 |
| Autonomous Operations | 22 |
| Team Collaboration | 40 |
| Predictive + Family | 32 |
| Knowledge & Reasoning | 28 |
| Integrations | 35 |
| Bridge/Portfolio | 25 |
| **Total** | **207** |
