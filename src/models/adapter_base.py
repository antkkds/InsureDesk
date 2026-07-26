"""InsureDesk — ModelAdapter: Portal data → Domain Models.

A ModelAdapter sits between PortalAdapter and DomainModel.
It converts portal-specific raw data into unified Policy/Claim/Customer models.

Flow:
  PortalAdapter.fetch_policy() → raw dict
    → ModelAdapter.extract_policy(raw) → Policy (validated)

Each portal has its own ModelAdapter implementation.
The base class handles validation and shared logic.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List, Type
from dataclasses import dataclass, field
from datetime import date
from abc import ABC, abstractmethod
import re

from src.models.policy import Policy, PolicyStatus, ProductType, Insured, Premium
from src.models.claim import Claim, ClaimStatus, Incident
from src.models.customer import Customer, Identity, Contact, ContactType
from src.models.task import InsuranceTask, WorkflowState, TaskType, TaskAction


# ══════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════

@dataclass
class ValidationError:
    """A single validation issue."""
    field: str
    message: str
    severity: str = "error"  # error, warning, info

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.field}: {self.message}"


@dataclass
class ValidationResult:
    """Result of model validation."""
    valid: bool = True
    errors: List[ValidationError] = field(default_factory=list)

    def add(self, field: str, message: str, severity: str = "error"):
        self.errors.append(ValidationError(field, message, severity))
        if severity == "error":
            self.valid = False

    def summary(self) -> str:
        if self.valid:
            return "✓ Valid"
        lines = [f"✗ {len(self.errors)} validation issue(s):"]
        for e in self.errors[:10]:
            lines.append(f"  {e}")
        if len(self.errors) > 10:
            lines.append(f"  ... and {len(self.errors) - 10} more")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# Field Mapping Helpers
# ══════════════════════════════════════════════════════════════════

class FieldMapper:
    """Map portal-specific field names to domain model fields.

    Each portal adapter defines a mapping dict like:
    {"raw_field_name": "model_field_name", ...}

    Multiple raw fields can map to the same model field.
    The mapper tries raw keys in order until it finds a value.
    """

    def __init__(self, field_map: Dict[str, str]):
        # model_field → [raw_field1, raw_field2, ...]  (ordered, tries first match)
        self._model_to_raw: Dict[str, List[str]] = {}
        for raw_key, model_field in field_map.items():
            if model_field not in self._model_to_raw:
                self._model_to_raw[model_field] = []
            self._model_to_raw[model_field].append(raw_key)

    def get(self, data: Dict[str, Any], model_field: str, default: Any = "") -> Any:
        """Get a value from raw data by model field name.

        Tries raw keys in order; the model_field itself is always tried first.
        """
        # Always try the model_field name as a direct key first
        if model_field in data:
            return data[model_field]

        # Then try mapped raw keys
        raw_keys = self._model_to_raw.get(model_field, [])
        for key in raw_keys:
            if key in data:
                return data[key]
            if key.lower() in {k.lower() for k in data}:
                # Case-insensitive fallback
                for k, v in data.items():
                    if k.lower() == key.lower():
                        return v

        return default

    def map_all(self, data: Dict[str, Any], model_fields: List[str]) -> Dict[str, Any]:
        """Extract multiple model fields from raw data."""
        return {f: self.get(data, f) for f in model_fields}

    def get_date(self, data: Dict[str, Any], model_field: str) -> Optional[date]:
        """Get a date value from raw data."""
        val = self.get(data, model_field, "")
        if not val:
            return None
        try:
            return date.fromisoformat(val)
        except (ValueError, TypeError):
            pass
        # dd/mm/yyyy
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(val))
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return None

    def get_float(self, data: Dict[str, Any], model_field: str, default: float = 0.0) -> float:
        """Get a float value from raw data."""
        val = self.get(data, model_field, default)
        try:
            return float(val)
        except (ValueError, TypeError):
            return default


# ══════════════════════════════════════════════════════════════════
# Base ModelAdapter
# ══════════════════════════════════════════════════════════════════

class ModelAdapter(ABC):
    """Base adapter: portal data → domain model.

    Each portal gets a concrete subclass that implements:
    - extract_policy(raw_data) → Policy
    - extract_claim(raw_data) → Claim
    - extract_customer(raw_data) → Customer

    Subclasses define:
    - FIELD_MAP: raw field name → model field name mapping
    - REQUIRED_POLICY_FIELDS: list of required Policy fields
    - REQUIRED_CLAIM_FIELDS: list of required Claim fields
    """

    # Subclasses override these
    PORTAL_NAME: str = "unknown"
    VERSION: str = "1.0.0"
    """Adapter implementation version. Bump when extraction logic changes."""
    PORTAL_VERSION: str = "1.0.0"
    """Version of the portal/source this adapter targets."""
    SCHEMA_VERSION: str = "1.0.0"
    """Version of the output schema (Policy/Claim field contract)."""
    FIELD_MAP: Dict[str, str] = {}
    REQUIRED_POLICY_FIELDS: List[str] = ["policy_number"]
    REQUIRED_CLAIM_FIELDS: List[str] = ["claim_id", "policy_number"]

    def __init__(self):
        self.mapper = FieldMapper(self.FIELD_MAP)
        self._stats: Dict[str, int] = {"extracted": 0, "validated": 0, "errors": 0}

    @property
    def name(self) -> str:
        return self.PORTAL_NAME

    # ── Extract methods (override in subclasses) ──

    def extract_policy(self, data: Dict[str, Any]) -> Policy:
        """Extract a Policy model from raw portal data.

        Override in subclasses for portal-specific logic.
        The base implementation uses FIELD_MAP for generic mapping.
        """
        p = Policy(
            policy_number=str(self.mapper.get(data, "policy_number", "")),
            insurer=self.PORTAL_NAME,
            source="portal",
            status=self._parse_policy_status(self.mapper.get(data, "status", "")),
            insured=Insured(
                name=str(self.mapper.get(data, "insured_name", "")),
                ic_number=str(self.mapper.get(data, "insured_ic", "")),
            ),
            inception_date=self.mapper.get_date(data, "inception_date"),
            expiry_date=self.mapper.get_date(data, "expiry_date"),
        )

        # Premium
        premium_val = self.mapper.get_float(data, "premium")
        if premium_val:
            p.premium = Premium(total=premium_val)

        self._stats["extracted"] += 1
        return p

    def extract_claim(self, data: Dict[str, Any]) -> Claim:
        """Extract a Claim model from raw portal data."""
        c = Claim(
            claim_id=str(self.mapper.get(data, "claim_id", "")),
            policy_number=str(self.mapper.get(data, "policy_number", "")),
            insurer=self.PORTAL_NAME,
            status=self._parse_claim_status(self.mapper.get(data, "status", "")),
            claim_amount=self.mapper.get_float(data, "claim_amount"),
            approved_amount=self.mapper.get_float(data, "approved_amount"),
        )

        # Incident
        inc = data.get("incident", {})
        if inc:
            c.incident = Incident(
                date=self.mapper.get_date(inc, "incident_date") or self._try_parse(inc.get("date", "")),
                type=str(inc.get("type", "")),
                description=str(inc.get("description", "")),
            )

        self._stats["extracted"] += 1
        return c

    def extract_customer(self, data: Dict[str, Any]) -> Customer:
        """Extract a Customer model from raw portal data."""
        c = Customer(
            customer_id=str(self.mapper.get(data, "customer_id", "")),
            identity=Identity(
                full_name=str(self.mapper.get(data, "customer_name", "")),
                ic_number=str(self.mapper.get(data, "customer_ic", "")),
            ),
        )
        # Policy references
        policies = data.get("policies", data.get("policy_numbers", []))
        if isinstance(policies, list):
            c.policy_numbers = policies

        self._stats["extracted"] += 1
        return c

    # ── Validation ──

    def validate_policy(self, policy: Policy) -> ValidationResult:
        """Validate a policy model has required fields."""
        result = ValidationResult()
        self._stats["validated"] += 1

        for field_name in self.REQUIRED_POLICY_FIELDS:
            val = getattr(policy, field_name, "")
            if not val:
                result.add(field_name, "Missing required field")

        if not policy.insured or not policy.insured.name:
            result.add("insured.name", "Missing insured name", "warning")

        if policy.inception_date and policy.expiry_date:
            if policy.inception_date > policy.expiry_date:
                result.add("expiry_date", "Expiry before inception", "error")

        return result

    def validate_claim(self, claim: Claim) -> ValidationResult:
        """Validate a claim model."""
        result = ValidationResult()
        self._stats["validated"] += 1

        for field_name in self.REQUIRED_CLAIM_FIELDS:
            val = getattr(claim, field_name, "")
            if not val:
                result.add(field_name, "Missing required field")

        return result

    # ── Stats ──

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    def reset_stats(self):
        self._stats = {"extracted": 0, "validated": 0, "errors": 0}

    # ── Helpers ──

    def _parse_policy_status(self, s: str) -> PolicyStatus:
        mapping = {
            "active": PolicyStatus.ACTIVE, "in force": PolicyStatus.ACTIVE,
            "lapsed": PolicyStatus.LAPSED, "cancelled": PolicyStatus.CANCELLED,
            "expired": PolicyStatus.EXPIRED, "pending": PolicyStatus.PENDING,
        }
        return mapping.get(s.strip().lower(), PolicyStatus.UNKNOWN)

    def _parse_claim_status(self, s: str) -> ClaimStatus:
        mapping = {
            "submitted": ClaimStatus.SUBMITTED, "in review": ClaimStatus.REVIEWING,
            "reviewing": ClaimStatus.REVIEWING, "approved": ClaimStatus.APPROVED,
            "rejected": ClaimStatus.REJECTED, "settled": ClaimStatus.SETTLED,
            "paid": ClaimStatus.SETTLED, "withdrawn": ClaimStatus.WITHDRAWN,
        }
        return mapping.get(s.strip().lower(), ClaimStatus.UNKNOWN)

    @staticmethod
    def _try_parse(s: str) -> Optional[date]:
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except (ValueError, TypeError):
            pass
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(s))
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return None
