# External Agent SDK — UIP-AI Platform Contract

> Phase 4.3 (ChatGPT suggestion): "这实际上已经不是 InsureDesk feature，它是
> UIP-AI platform contract." Third-party developers follow this contract to
> register ANY remote agent without modifying UIP-AI core.

## Who this is for

Developers who want to connect an external agent (desktop, SaaS, local) to
UIP-AI as a **Capability Provider** — not a connector, not a Router change.

## The 5-step lifecycle

```
1. Write manifest.yaml      → what capabilities the agent provides
2. register                 → POST /api/v1/agent-providers/register-manifest
3. heartbeat (every 30s)    → POST /api/v1/agent-providers/{id}/heartbeat
4. poll commands (every 3s) → GET  /api/v1/agent-providers/{id}/commands
5. execute + report result  → POST /api/v1/agent-providers/{id}/executions/{execution_id}/result
```

## 1. Manifest

```yaml
name: crm_agent              # REQUIRED — stable agent_id
type: saas_agent             # desktop_agent | saas_agent | local_agent
version: 1.0.0
transport: http_pull         # Phase 4.2 MVP supports only http_pull
provides:                    # REQUIRED — ≥1 capability
  - crm.customer.lookup
  - crm.customer.sync
metadata:                    # optional free-form
  vendor: Acme CRM
```

Capability naming: `{domain}.{entity}.{action}` — e.g. `insurance.quote.calculate`.

## 2. Register

```
POST /api/v1/agent-providers/register-manifest
{
  "tenant_id": "tenant_abc",
  "manifest": { ... above ... }
}
→ { "agent_id": "crm_agent", "instance_id": "inst_crm_agent", "status": "online" }
```

Store `instance_id` — you need it for heartbeat/poll/result.

## 3. Heartbeat

```
POST /api/v1/agent-providers/{instance_id}/heartbeat   (every 30s)
→ { "status": "running" }
```

- Heartbeat TTL = 60s. If the agent misses 2 beats it becomes **offline**
  and the Resolver skips it.
- Heartbeat failure must NEVER crash the agent — retry, degrade to offline,
  keep trying.

## 4. Poll commands

```
GET /api/v1/agent-providers/{instance_id}/commands
→ { "commands": [
      { "execution_id": "exec_123",
        "capability": "crm.customer.lookup",
        "arguments": { "customer_id": "C-42" } }
  ] }
```

Polling marks commands DELIVERED. Poll every ~3s (http_pull is preferred
over server push for NAT/firewall/corporate-network environments).

## 5. Execute + report result

Execute locally, then:

```
POST /api/v1/agent-providers/{instance_id}/executions/{execution_id}/result

Success:
{ "status": "success", "result": { "name": "Alice" }, "execution_mode": "real" }

Failure:
{ "status": "failed", "error_code": "CRM_API_ERROR", "error": "..." }
```

**Never send raw exceptions.** Map to stable codes:
`PORTAL_AUTH_FAILED`, `PORTAL_SESSION_EXPIRED`, `PORTAL_TIMEOUT`,
`NOT_FOUND`, `VALIDATION_ERROR`, `EXECUTION_FAILED` (extensible).

## What you do NOT need to touch

- Router / ToolRuntime / ConnectorRuntime / Blueprint engine
- Permission engine (per-tenant capability grants via tenant_capabilities)
- UIP-AI core code

## Reference implementation

InsureDesk (`src/agent/` in the InsureDesk repo) is the first Agent
Protocol client:
`manifest.py` → `client.py` → `heartbeat.py` → `command_loop.py` →
`handlers.py` → `result_reporter.py`.

## Testing contract

The Phase 4.3 acceptance suite (`tests/test_agent_client_runtime.py`)
covers: register → heartbeat → poll → simulate execution → error mapping →
restart recovery. Run against a fake UIP-AI server; swap the endpoint for
a real UIP-AI deployment.
