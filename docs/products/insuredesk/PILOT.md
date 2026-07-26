# PILOT — Real User Testing Checklist

> Transition from "complete codebase" to "testable with real insurance agents."

## Status

- **Generation 1 development:** COMPLETE (PI-1 → PI-20)
- **Engineer validation:** Browser automation through Playwright on Great Eastern
- **Next:** Real agent testing on Windows laptops

---

## □ Browser Engine

- [ ] PlaywrightDriver opens Chromium window on WSL/Linux
- [ ] QtDriver starts embedded browser on Windows (PyInstaller)
- [ ] Engine auto-selection works (create_browser_engine)
- [ ] Headless mode functional for automated runs
- [ ] Multiple tabs handled (if portal opens new tab)
- [ ] Error recovery: browser crash → restart
- [ ] Screenshot capture for debugging

## □ Session Persistence

- [ ] Login once → cookies saved to disk
- [ ] Close app → reopen → session restored (no re-login)
- [ ] Expired session detected → re-login prompt
- [ ] Multiple insurer sessions coexist (GE + Allianz + AIA)
- [ ] Session survives network disconnection

## □ Portal Adapter: Great Eastern

- [ ] Navigate to i-Connect login page
- [ ] Fill username field
- [ ] Fill password field
- [ ] Click submit / login button
- [ ] Detect successful login (dashboard welcome message)
- [ ] Detect failed login (error message handling)
- [ ] Navigate to policy search
- [ ] Enter policy number and search
- [ ] Read policy details (number, status, premium, dates)
- [ ] Navigate to claims section
- [ ] Fill claim form
- [ ] Submit claim
- [ ] Navigate to document upload
- [ ] Upload a PDF document
- [ ] Trigger policy renewal
- [ ] Logout
- [ ] Timeout after 5 min inactivity
- [ ] Error handling: portal down → graceful message

## □ Portal Adapter: Allianz

- [ ] Login with name-based selectors
- [ ] Policy search by number
- [ ] Read policy details
- [ ] Logout

## □ Portal Adapter: AIA

- [ ] Login with name-based selectors
- [ ] Policy search
- [ ] Logout

## □ Desktop Application

- [ ] PySide6 main window opens
- [ ] Dashboard loads without error
- [ ] Customer list renders
- [ ] Create new customer
- [ ] Edit existing customer
- [ ] Add policy to customer
- [ ] Document upload UI works
- [ ] Portal connection dialog works
- [ ] Settings page loads
- [ ] Multi-language display (English / Malay / Chinese)

## □ UIP-AI Integration

- [ ] Bridge connection established
- [ ] Ping/health check returns OK
- [ ] Upload PDF → UIP-AI parses → structured data returned
- [ ] Assistant chat works
- [ ] Memory persists across sessions
- [ ] Tool calling executes correctly

## □ Installation (Windows)

- [ ] PyInstaller builds single .exe
- [ ] Clean install on Windows 10 (no Python installed)
- [ ] Clean install on Windows 11
- [ ] First launch: creates data directory
- [ ] No missing DLL errors
- [ ] Antivirus false positive check
- [ ] Uninstall removes all files

## □ Pilot Test Scenarios

### Scenario 1: New Agent Setup
1. Install InsureDesk → 5 min
2. Configure Great Eastern account → 2 min
3. Login to GE → 30 sec
4. Search first policy → 10 sec
5. Add customer → 1 min
6. Link policy to customer → 30 sec
7. Total: ~10 min

### Scenario 2: Daily Operations
1. Open InsureDesk → 5 sec
2. Check morning review → 10 sec
3. See 3 renewals due this week → 5 sec
4. Open renewal → 5 sec
5. Click "Renew" → portal auto-fills → agent confirms → 30 sec
6. Log call notes → 1 min
7. Total per action: ~2 min

### Scenario 3: Claim Handling
1. Customer calls about claim → 5 sec
2. Search customer → 5 sec
3. Open claims section → 5 sec
4. Fill claim form (auto-populated from policy) → 30 sec
5. Upload supporting document → 10 sec
6. Submit → 5 sec
7. Total: ~1 min

---

## Performance Targets

| Metric | Target |
|--------|--------|
| App cold start | < 5 sec |
| Portal login | < 30 sec |
| Policy search | < 10 sec |
| Claim submission | < 2 min |
| Memory usage (idle) | < 200 MB |
| Disk usage | < 200 MB |
| Internet (per operation) | < 1 MB |
