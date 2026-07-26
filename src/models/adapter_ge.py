"""InsureDesk — Great Eastern ModelAdapter.

Maps Great Eastern Insurance portal data → domain models.

GE field naming convention (from portal YAML + PDF extraction):
  - policy_no / policy_number
  - insured_name / customer_name
  - insured_ic / nric
  - premium_amount
  - inception / inception_date
  - expiry / expiry_date
  - cover_note_no
"""

from typing import Dict, Any, List

from src.models.adapter_base import ModelAdapter
from src.models.policy import Policy, Insured, Premium
from src.models.claim import Claim, ClaimStatus


class GreatEasternAdapter(ModelAdapter):
    """ModelAdapter for Great Eastern Insurance portal."""

    PORTAL_NAME = "Great Eastern"

    FIELD_MAP: Dict[str, str] = {
        "policy_number": "policy_number",
        "policy_no": "policy_number",
        "cover_note": "policy_number",
        "insured_name": "insured_name",
        "insured_ic": "insured_ic",
        "nric": "insured_ic",
        "premium": "premium",
        "premium_amount": "premium",
        "inception": "inception_date",
        "inception_date": "inception_date",
        "expiry": "expiry_date",
        "expiry_date": "expiry_date",
        "status": "status",
        "customer_name": "insured_name",
        "customer_ic": "insured_ic",
        "policy_status": "status",
    }

    REQUIRED_POLICY_FIELDS: List[str] = ["policy_number"]

    def extract_policy(self, data: Dict[str, Any]) -> Policy:
        """GE-specific: policy_no is primary key, support cover_note format."""
        p = super().extract_policy(data)

        # GE uses 'policy_no' more often than 'policy_number'
        if not p.policy_number:
            p.policy_number = str(self.mapper.get(data, "policy_no", ""))

        # GE cover note format
        if not p.policy_number:
            p.policy_number = str(data.get("cover_note_no", ""))

        return p


class GreatEasternPDFAdapter(ModelAdapter):
    """ModelAdapter for Great Eastern PDF extraction.

    Handles the output of Document Intelligence SDK.
    Different field naming from the portal version.
    """

    PORTAL_NAME = "Great Eastern (PDF)"

    FIELD_MAP: Dict[str, str] = {
        "policy_number": "policy_number",
        "policy_no": "policy_number",
        "insurer": "insurer",
        "insured": "insured_name",
        "insured_name": "insured_name",
        "nric": "insured_ic",
        "sum_insured": "sum_insured",
        "premium": "premium",
        "inception_date": "inception_date",
        "expiry_date": "expiry_date",
    }

    REQUIRED_POLICY_FIELDS: List[str] = ["policy_number"]

    def extract_policy(self, data: Dict[str, Any]) -> Policy:
        """PDF extraction: insured is a nested object, not flat string."""
        p = Policy(
            policy_number=str(self.mapper.get(data, "policy_number", "")
                              or data.get("policy_no", "")),
            insurer="Great Eastern",
            source="pdf",
            raw_text=data.get("raw_text", ""),
        )

        # Insured might be a dict
        insured_data = data.get("insured", {})
        if isinstance(insured_data, dict):
            p.insured = Insured(
                name=str(insured_data.get("name", "")),
                ic_number=str(insured_data.get("ic_number", insured_data.get("nric", ""))),
                address=str(insured_data.get("address", "")),
            )
        elif isinstance(insured_data, str):
            p.insured = Insured(name=insured_data)

        # Premium
        premium_val = data.get("premium", 0) or data.get("total_premium", 0)
        if premium_val:
            p.premium = Premium(total=float(premium_val))

        # Dates
        for key, attr in [("inception_date", "inception_date"), ("expiry_date", "expiry_date")]:
            val = data.get(key, "")
            if val:
                try:
                    from datetime import date
                    setattr(p, attr, date.fromisoformat(val) if isinstance(val, str) else val)
                except (ValueError, TypeError):
                    pass

        self._stats["extracted"] += 1
        return p
