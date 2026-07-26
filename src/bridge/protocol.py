"""InsureDesk — Bridge Protocol for UIP-AI communication.

Architecture:

    InsureDesk Desktop              UIP-AI Platform (server)
    ────────────────                ─────────────────────
    BridgeClient                      UIP-AI API
         │                                │
         │  POST /v1/chat                  │
│  │  POST /v1/chat                  │
│  ├───────────────────────────────▶ │
│  │  { response, actions }          │
│  │◀─────────────────────────────── │
│  │                                 │
│  │  POST /v1/tools/execute          │
│  │  { tool, params }               │
│  ├───────────────────────────────▶ │
│  │  { result }                     │
│  │◀─────────────────────────────── │
│  │                                 │
│  │  POST /v1/policy/parse           │
│  │  (multipart: PDF file)          │
│  ├───────────────────────────────▶ │
│  │  { structured policy JSON }     │
│  │◀─────────────────────────────── │
│
└──── ──── ──── ──── ──── ──── ──"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field, asdict

import requests


DEFAULT_UIP_AI_URL = "http://localhost:8000"
API_VERSION = "v1"


def _now():
    return datetime.now(timezone.utc).isoformat()


# ── Protocol Types ───────────────────────────────────────────────

@dataclass
class BridgeMessage:
    """A message sent from InsureDesk to UIP-AI."""
    text: str
    customer_id: Optional[str] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BridgeResponse:
    """Response from UIP-AI after processing a message."""
    text: str
    actions: list = field(default_factory=list)
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    id: str = ""
    timestamp: str = field(default_factory=_now)

    @classmethod
    def from_dict(cls, d: dict) -> "BridgeResponse":
        return cls(
            text=d.get("text", ""),
            actions=d.get("actions", []),
            conversation_id=d.get("conversation_id"),
            session_id=d.get("session_id"),
            metadata=d.get("metadata", {}),
            id=d.get("id", ""),
            timestamp=d.get("timestamp", _now()),
        )


@dataclass
class ToolCall:
    """A tool execution request to UIP-AI."""
    tool: str
    params: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    result: dict = field(default_factory=dict)
    error: str = ""
    id: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "ToolResult":
        return cls(
            success=d.get("success", False),
            result=d.get("result", {}),
            error=d.get("error", ""),
            id=d.get("id", ""),
        )


# ── Client ───────────────────────────────────────────────────────

class BridgeClient:
    """Client for communicating with UIP-AI platform."""

    def __init__(self, base_url: str = DEFAULT_UIP_AI_URL, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session_id = None
        self.connected = False

    # ── Connection ──

    def connect(self, token: str) -> bool:
        """Connect to UIP-AI platform with an API token."""
        self.token = token
        try:
            resp = requests.get(
                f"{self.base_url}/v1/health",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10,
            )
            if resp.status_code == 200:
                self.connected = True
                return True
        except requests.RequestException:
            pass
        self.connected = False
        return False

    def disconnect(self):
        """Disconnect from UIP-AI."""
        self.connected = False
        self.token = ""
        self.session_id = None

    def ping(self) -> bool:
        """Check if connection is alive."""
        if not self.connected or not self.token:
            return False
        try:
            resp = requests.get(
                f"{self.base_url}/v1/health",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5,
            )
            return resp.status_code == 200
        except requests.RequestException:
            self.connected = False
            return False

    # ── Messaging ──

    def send_message(self, message: BridgeMessage) -> Optional[BridgeResponse]:
        """Send a message to the AI assistant and get response."""
        if not self.connected:
            return None

        payload = {
            "text": message.text,
            "customer_id": message.customer_id,
            "session_id": self.session_id,
        }

        try:
            resp = requests.post(
                f"{self.base_url}/v1/chat",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                response = BridgeResponse.from_dict(data)
                self.session_id = response.session_id or self.session_id
                return response
        except requests.RequestException:
            pass
        return None

    # ── Tool Execution ──

    def execute_tool(self, tool_call: ToolCall) -> Optional[ToolResult]:
        """Execute a tool via UIP-AI."""
        if not self.connected:
            return None

        try:
            resp = requests.post(
                f"{self.base_url}/v1/tools/execute",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json=tool_call.to_dict(),
                timeout=60,
            )
            if resp.status_code == 200:
                return ToolResult.from_dict(resp.json())
        except requests.RequestException:
            pass
        return None

    # ── Policy Intelligence ────────────────────────────────────────

    def upload_policy(self, file_path: str, customer_id: str, language: str = "en") -> Optional[dict]:
        """Upload a policy PDF/image to UIP-AI for OCR + LLM parsing.

        UIP-AI handles OCR extraction and LLM-based structured parsing.
        InsureDesk only stores the structured JSON result locally.

        Args:
            file_path: Absolute path to the PDF or image file.
            customer_id: Customer ID to associate the parsed policy with.
            language: Document language code (en/ms/zh).

        Returns:
            dict with keys: company, policy_number, policy_type, status,
            premium, start_date, end_date, coverages, exclusions, summary
            or None if the upload/parse failed.
        """
        if not self.connected:
            return None

        file_path = str(file_path)
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
                data = {"customer_id": customer_id, "language": language}
                resp = requests.post(
                    f"{self.base_url}/v1/policy/parse",
                    headers={"Authorization": f"Bearer {self.token}"},
                    files=files,
                    data=data,
                    timeout=120,
                )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── Portfolio Intelligence (PI-6) ──────────────────────────────

    def build_portfolio(
        self,
        customer_id: str,
        customer_name: str,
        policies: list,
    ) -> Optional[dict]:
        """Build a customer portfolio from parsed policies.

        Args:
            customer_id: Customer identifier.
            customer_name: Customer display name.
            policies: List of dicts with parse_result + metadata.

        Returns:
            CustomerPortfolio dict with policies grouped by type.
        """
        if not self.connected:
            return None

        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/portfolio/build",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "policies_json": _json.dumps(policies),
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def query_portfolio(
        self,
        customer_id: str,
        customer_name: str,
        policies: list,
        question: str,
    ) -> Optional[str]:
        """Query the customer's insurance portfolio.

        Args:
            customer_id: Customer identifier.
            customer_name: Customer display name.
            policies: List of dicts with parse_result + metadata.
            question: Natural language question.

        Returns:
            Answer string or None.
        """
        if not self.connected:
            return None

        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/portfolio/query",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "policies_json": _json.dumps(policies),
                    "question": question,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("answer", "")
            return None
        except requests.RequestException:
            return None

    def analyze_gaps(
        self,
        customer_id: str,
        customer_name: str,
        policies: list,
        customer_age: int = 0,
    ) -> Optional[list]:
        """Analyze coverage gaps in a customer's portfolio.

        Args:
            customer_id: Customer identifier.
            customer_name: Customer display name.
            policies: List of dicts with parse_result + metadata.
            customer_age: Customer age for gap analysis context.

        Returns:
            List of gap dicts or None.
        """
        if not self.connected:
            return None

        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/portfolio/gaps",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "policies_json": _json.dumps(policies),
                    "customer_age": customer_age,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("gaps", [])
            return None
        except requests.RequestException:
            return None

    # ── PI-8: Lifecycle Methods ───────────────────────────────────

    def build_lifecycle(
        self,
        policy_id: str,
        customer_id: str,
        company: str = "",
        product_name: str = "",
        effective_date: str = "",
        expiry_date: str = "",
        premium: float = 0.0,
        auto_renew: bool = False,
        grace_period_days: int = 30,
    ) -> Optional[dict]:
        """Create a PolicyLifecycle for a newly parsed policy."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/lifecycle/build",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "policy_id": policy_id,
                    "customer_id": customer_id,
                    "company": company,
                    "product_name": product_name,
                    "effective_date": effective_date,
                    "expiry_date": expiry_date,
                    "premium": premium,
                    "auto_renew": auto_renew,
                    "grace_period_days": grace_period_days,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def scan_lifecycles(self, today: str = "") -> Optional[dict]:
        """Scan all policy lifecycles for tasks needing attention.

        This is the primary endpoint for the morning dashboard.
        """
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/lifecycle/scan",
                headers={"Authorization": f"Bearer {self.token}"},
                data={"today": today},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_dashboard(self, today: str = "") -> Optional[dict]:
        """Build the full InsureDesk dashboard summary."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/lifecycle/dashboard",
                headers={"Authorization": f"Bearer {self.token}"},
                data={"today": today},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def renew_policy(
        self,
        policy_id: str,
        new_expiry_date: str = "",
        new_premium: float = 0.0,
    ) -> Optional[dict]:
        """Mark a policy as renewed."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/lifecycle/renew",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "policy_id": policy_id,
                    "new_expiry_date": new_expiry_date,
                    "new_premium": new_premium,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_customer_lifecycles(self, customer_id: str) -> Optional[dict]:
        """Get all lifecycle records for a customer."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/policy/lifecycle/customer/{customer_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── PI-9: Premium Intelligence ───────────────────────────────

    def record_premium(
        self,
        customer_id: str,
        policy_id: str,
        premium_amount: float,
        effective_date: str = "",
        currency: str = "RM",
        payment_frequency: str = "yearly",
        reason: str = "new_policy",
        notes: str = "",
    ) -> Optional[dict]:
        """Record a premium entry for a policy."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/premium/record",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "customer_id": customer_id,
                    "policy_id": policy_id,
                    "premium_amount": premium_amount,
                    "effective_date": effective_date,
                    "currency": currency,
                    "payment_frequency": payment_frequency,
                    "reason": reason,
                    "notes": notes,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_premium_history(
        self,
        policy_id: str,
        product_name: str = "",
        company: str = "",
    ) -> Optional[dict]:
        """Get premium history for a policy."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/policy/premium/history/{policy_id}",
                params={"product_name": product_name, "company": company},
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def analyze_premium_trend(
        self,
        policy_id: str,
        product_name: str = "",
    ) -> Optional[dict]:
        """Analyze premium trend for a policy."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/premium/trend",
                headers={"Authorization": f"Bearer {self.token}"},
                data={"policy_id": policy_id, "product_name": product_name},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_premium_customer_summary(
        self,
        customer_id: str,
        customer_name: str = "",
        portfolio: Optional[list] = None,
    ) -> Optional[dict]:
        """Get aggregated premium summary for a customer."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/premium/customer-summary",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "portfolio_json": _json.dumps(portfolio or []),
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── PI-9: Claim Intelligence ─────────────────────────────────

    def record_claim(
        self,
        customer_id: str,
        policy_id: str,
        claim_date: str = "",
        claim_type: str = "",
        claimed_amount: float = 0.0,
        approved_amount: float = 0.0,
        status: str = "submitted",
        description: str = "",
    ) -> Optional[dict]:
        """Record a new insurance claim."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/claim/record",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "customer_id": customer_id,
                    "policy_id": policy_id,
                    "claim_date": claim_date,
                    "claim_type": claim_type,
                    "claimed_amount": claimed_amount,
                    "approved_amount": approved_amount,
                    "status": status,
                    "description": description,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_claim_history(self, customer_id: str) -> Optional[dict]:
        """Get claim history for a customer."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/policy/claim/history/{customer_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_claim_summary(self, customer_id: str) -> Optional[dict]:
        """Get summarized claim analytics for a customer."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/claim/summary",
                headers={"Authorization": f"Bearer {self.token}"},
                data={"customer_id": customer_id},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def query_claims(
        self,
        customer_id: str,
        question: str,
        customer_name: str = "",
    ) -> Optional[dict]:
        """Ask a question about a customer's claims."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/claim/query",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "question": question,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── PI-10: Market Intelligence ───────────────────────────────

    def record_market_announcement(
        self,
        company: str,
        title: str,
        summary: str = "",
        category: str = "general",
        date: str = "",
        detail: str = "",
        effective_date: str = "",
        severity: str = "medium",
        source: str = "",
        tags: str = "",
    ) -> Optional[dict]:
        """Record a market announcement from an insurance company."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/market/announcement",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "company": company,
                    "title": title,
                    "summary": summary,
                    "category": category,
                    "date": date,
                    "detail": detail,
                    "effective_date": effective_date,
                    "severity": severity,
                    "source": source,
                    "tags": tags,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_market_dashboard(self) -> Optional[dict]:
        """Get market intelligence dashboard data."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/policy/market/dashboard",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_company_announcements(
        self,
        company: str,
        limit: int = 20,
    ) -> Optional[dict]:
        """Get announcements for a specific insurance company."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/policy/market/company/{company}",
                params={"limit": limit},
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def query_market(
        self,
        question: str,
        company_filter: str = "",
    ) -> Optional[dict]:
        """Ask a question about market intelligence."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/market/query",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "question": question,
                    "company_filter": company_filter,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── PI-11: Workflow Intelligence ────────────────────────────

    def build_work_queue(
        self,
        lifecycle: Optional[list] = None,
        market: Optional[list] = None,
        claims: Optional[list] = None,
        premium: Optional[list] = None,
        policy_changes: Optional[list] = None,
        portfolio_gaps: Optional[list] = None,
    ) -> Optional[dict]:
        """Build work queue from all intelligence sources."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/workflow/build",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "lifecycle_json": _json.dumps(lifecycle or []),
                    "market_json": _json.dumps(market or []),
                    "claims_json": _json.dumps(claims or []),
                    "premium_json": _json.dumps(premium or []),
                    "policy_changes_json": _json.dumps(policy_changes or []),
                    "portfolio_gaps_json": _json.dumps(portfolio_gaps or []),
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_today_work(self) -> Optional[dict]:
        """Get today's work queue."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/policy/workflow/today",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def complete_work_item(self, item_id: str) -> Optional[dict]:
        """Mark a work item as completed."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/workflow/complete",
                headers={"Authorization": f"Bearer {self.token}"},
                data={"item_id": item_id},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def add_work_item(
        self,
        customer_id: str,
        title: str,
        description: str = "",
        recommended_action: str = "",
        due_date: str = "",
        priority: str = "medium",
        customer_name: str = "",
    ) -> Optional[dict]:
        """Add a manual work item."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/workflow/add",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "customer_id": customer_id,
                    "title": title,
                    "description": description,
                    "recommended_action": recommended_action,
                    "due_date": due_date,
                    "priority": priority,
                    "customer_name": customer_name,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── PI-12: Data Synchronization ────────────────────────────

    def register_sync_source(
        self,
        name: str,
        source_type: str,
        config: Optional[dict] = None,
    ) -> Optional[dict]:
        """Register a new data source."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/sync/source/register",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "name": name,
                    "source_type": source_type,
                    "config_json": _json.dumps(config or {}),
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def run_sync(self, source_id: str, items: Optional[list] = None) -> Optional[dict]:
        """Execute a synchronization job."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/sync/run",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "source_id": source_id,
                    "items_json": _json.dumps(items or []),
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_sync_job(self, job_id: str) -> Optional[dict]:
        """Get sync job status."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/policy/sync/job/{job_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def list_sync_sources(self) -> Optional[dict]:
        """List all sync sources."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/policy/sync/sources",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── PI-13: Communication Intelligence ──────────────────────

    def create_comm_plan(self, work_item: dict, customer_name: str = "") -> Optional[dict]:
        """Create a communication plan from a work item."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/communication/plan",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "work_item_json": _json.dumps(work_item),
                    "customer_name": customer_name,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def generate_comm_draft(
        self,
        plan_id: str,
        step_id: str,
        customer_context: Optional[dict] = None,
        language: str = "en",
    ) -> Optional[dict]:
        """Generate a message draft."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/communication/draft",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "plan_id": plan_id,
                    "step_id": step_id,
                    "customer_json": _json.dumps(customer_context or {}),
                    "language": language,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def approve_comm_draft(self, draft_id: str) -> Optional[dict]:
        """Approve a message draft."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/communication/approve",
                headers={"Authorization": f"Bearer {self.token}"},
                data={"draft_id": draft_id},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def send_communication(self, draft_id: str) -> Optional[dict]:
        """Record a sent communication."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/communication/send",
                headers={"Authorization": f"Bearer {self.token}"},
                data={"draft_id": draft_id},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_comm_history(self, customer_id: str) -> Optional[dict]:
        """Get communication history for a customer."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/policy/communication/history/{customer_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── PI-14: Automation & Approval ───────────────────────────

    def create_automation_rule(
        self, name: str, trigger: str, action_type: str,
        conditions: Optional[dict] = None,
        execution_policy: str = "automatic",
    ) -> Optional[dict]:
        """Create an automation rule."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/automation/rules",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "name": name,
                    "trigger": trigger,
                    "conditions_json": _json.dumps(conditions or {}),
                    "action_type": action_type,
                    "execution_policy": execution_policy,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def evaluate_automation(self, trigger: str,
                            event_data: Optional[dict] = None) -> Optional[dict]:
        """Evaluate automation rules for a trigger."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/automation/evaluate",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "trigger": trigger,
                    "event_data_json": _json.dumps(event_data or {}),
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def request_approval(self, rule_id: str, action_type: str,
                         action_summary: str) -> Optional[dict]:
        """Request approval for an action."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/approval/request",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "rule_id": rule_id,
                    "action_type": action_type,
                    "action_summary": action_summary,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def approve_action(self, request_id: str, notes: str = "") -> Optional[dict]:
        """Approve a pending action."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/policy/approval/approve",
                headers={"Authorization": f"Bearer {self.token}"},
                data={"request_id": request_id, "notes": notes},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def list_pending_approvals(self) -> Optional[dict]:
        """List pending approvals."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/policy/approval/pending",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def execute_automation(self, rule_id: str, action_type: str,
                           action_params: Optional[dict] = None) -> Optional[dict]:
        """Execute an automation action."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/automation/execute",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "rule_id": rule_id,
                    "action_type": action_type,
                    "action_params_json": _json.dumps(action_params or {}),
                },
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── PI-15: Business Intelligence ───────────────────────────

    def get_business_dashboard(
        self,
        customers: Optional[list] = None,
        policies: Optional[list] = None,
        lifecycles: Optional[list] = None,
        premiums: Optional[list] = None,
        portfolios: Optional[list] = None,
        previous_data: Optional[dict] = None,
    ) -> Optional[dict]:
        """Build business health dashboard."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/business/dashboard",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "customers_json": _json.dumps(customers or []),
                    "policies_json": _json.dumps(policies or []),
                    "lifecycles_json": _json.dumps(lifecycles or []),
                    "premiums_json": _json.dumps(premiums or []),
                    "portfolios_json": _json.dumps(portfolios or []),
                    "previous_json": _json.dumps(previous_data or {}),
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def analyze_business_risks(
        self,
        customers: Optional[list] = None,
        policies: Optional[list] = None,
        lifecycles: Optional[list] = None,
        premiums: Optional[list] = None,
        portfolios: Optional[list] = None,
    ) -> Optional[dict]:
        """Analyze customer risks and opportunities."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/business/risk-analysis",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "customers_json": _json.dumps(customers or []),
                    "policies_json": _json.dumps(policies or []),
                    "lifecycles_json": _json.dumps(lifecycles or []),
                    "premiums_json": _json.dumps(premiums or []),
                    "portfolios_json": _json.dumps(portfolios or []),
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_business_review(
        self,
        customers: Optional[list] = None,
        policies: Optional[list] = None,
        lifecycles: Optional[list] = None,
        premiums: Optional[list] = None,
        portfolios: Optional[list] = None,
        language: str = "en",
    ) -> Optional[dict]:
        """Generate AI business review."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/policy/business/review",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "customers_json": _json.dumps(customers or []),
                    "policies_json": _json.dumps(policies or []),
                    "lifecycles_json": _json.dumps(lifecycles or []),
                    "premiums_json": _json.dumps(premiums or []),
                    "portfolios_json": _json.dumps(portfolios or []),
                    "language": language,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── PI-16: Agency Collaboration ───────────────────────────

    def query_agent_tasks(
        self,
        member_id: str,
        team_id: str,
        question: str = "What should I do today?",
    ) -> Optional[dict]:
        """Ask AI what an agent should focus on today."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/agency/agent/plan",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "member_id": member_id,
                    "team_id": team_id,
                    "question": question,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def query_team_performance(
        self,
        team_id: str,
        question: str = "How is my team?",
    ) -> Optional[dict]:
        """Ask AI about team performance."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/agency/team/performance",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "team_id": team_id,
                    "question": question,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── PI-17: Enterprise Integration ─────────────────────────

    def list_integrations(self) -> Optional[list]:
        """List available integration connectors from UIP-AI."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/integrations",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("integrations", [])
            return None
        except requests.RequestException:
            return None

    def connect_integration(
        self, provider: str, config: dict = None,
    ) -> Optional[dict]:
        """Connect to an external system via UIP-AI."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/integrations/connect",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "provider": provider,
                    "config_json": json.dumps(config or {}),
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def sync_integration(self, integration_id: str) -> Optional[dict]:
        """Trigger a sync for an integration."""
        if not self.connected:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/v1/integrations/{integration_id}/sync",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    # ── PI-18: Predictive Intelligence ────────────────────────

    def get_daily_plan(self) -> Optional[dict]:
        """Get AI-generated daily plan from UIP-AI."""
        if not self.connected:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/planner/today",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def predict_renewal_risk(self, customer_data: dict) -> Optional[dict]:
        """Predict renewal risk for a customer."""
        if not self.connected:
            return None
        try:
            import json as _json
            resp = requests.post(
                f"{self.base_url}/v1/predict/renewal-risk",
                headers={"Authorization": f"Bearer {self.token}"},
                data={"customer_json": _json.dumps(customer_data)},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None
