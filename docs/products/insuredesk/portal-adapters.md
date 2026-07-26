# Portal Adapters

> Per-insurer adapter contracts defining login → operation → logout lifecycle.

## Adapter Architecture

```
PortalAdapter (ABC)
    ├── GreatEasternAdapter → portals/great_eastern.yaml
    ├── AllianzAdapter      → portals/allianz.yaml
    └── AIAAdapter          → portals/aia.yaml
```

Each adapter:
- Auto-loads its YAML mapping by name
- Uses FormEngine for all browser interactions
- Uses SessionManager for persistent login
- Is fully swappable between Playwright (dev) and WebEngine (prod)

## Standard Contract

Every adapter implements:

| Method | Description | Selector Group |
|--------|-------------|----------------|
| `connect()` | Start browser engine | — |
| `disconnect()` | Save session, stop engine | — |
| `login(credentials)` | Auth + session restore | `login.*` |
| `logout()` | Sign out | `dashboard.logout_link` |
| `search_policy(no)` | Find policy | `policy_search.*` |
| `get_policy_details()` | Read current policy | `policy_details.*` |
| `submit_claim(data)` | File a claim | `claims.*` |
| `renew_policy()` | Trigger renewal | `renewal.*` |
| `upload_document(path, type)` | Upload document | `documents.*` |
| `check_health()` | Portal status | — |

## YAML Selector Groups

### Login (`login.*`)
```
username, password, submit, login_button, remember_me
```

### Dashboard (`dashboard.*`)
```
welcome_message, logout_link, user_profile
```

### Policy Search (`policy_search.*`)
```
nav_link, search_input, search_button, search_results, policy_row
```

### Policy Details (`policy_details.*`)
```
policy_number, status, premium, start_date, end_date, coverage_section, download_button
```

### Claims (`claims.*`)
```
nav_link, new_claim_button, policy_no_field, incident_date, claim_type, description, upload_evidence, submit_button, claim_status
```

### Documents (`documents.*`)
```
nav_link, upload_button, file_input, document_type, submit_upload
```

### Renewal (`renewal.*`)
```
nav_link, renew_button, confirm_renewal, payment_method, complete_renewal
```

### Customer (`customer.*`)
```
nav_link, search_input, search_result
```

## Great Eastern

| Property | Value |
|----------|-------|
| **Portal** | Great Eastern i-Connect |
| **URL** | https://iconnect.greateasternlife.com |
| **Adapter** | `GreatEasternAdapter` |
| **File** | `portals/great_eastern.yaml` |
| **Selectors** | ID-based (`#username`, `#password`) |

## Allianz

| Property | Value |
|----------|-------|
| **Portal** | Allianz Life e-Service |
| **URL** | https://life-eservice.allianz.com.my |
| **Adapter** | `AllianzAdapter` |
| **File** | `portals/allianz.yaml` |
| **Selectors** | Name-based (`input[name='userid']`) |

## AIA

| Property | Value |
|----------|-------|
| **Portal** | AIA e-Care |
| **URL** | https://ecare.aia.com.my |
| **Adapter** | `AIAAdapter` |
| **File** | `portals/aia.yaml` |
| **Selectors** | Name-based (`input[name='username']`) |

## Adding a New Portal

1. Create YAML: `portals/<name>.yaml`
2. Define selectors for each group
3. Create adapter class in `src/portals/base.py`
4. Register in `_ADAPTER_MAP`
5. Write tests
6. Run `python test_portal_live.py <name>` to verify
