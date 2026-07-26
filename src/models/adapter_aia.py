"""InsureDesk — AIA Malaysia ModelAdapter.

AIA field naming convention (from portal YAML):
  - policy_number / policy_id
  - life_assured / insured_name
  - plan_name / product_type
  - basic_premium / premium
  - sum_assured / sum_insured
  - commencement_date / inception_date
  - maturity_date / expiry_date
  - policy_status
  - owner_name / customer_name
  - owner_ic / nric
"""

from typing import Dict, Any

from src.models.adapter_base import ModelAdapter
from src.models.policy import Policy, Insured


class AIAAdapter(ModelAdapter):
    """ModelAdapter for AIA Malaysia Insurance portal."""

    PORTAL_NAME = "AIA Malaysia"

    FIELD_MAP: Dict[str, str] = {
        "policy_number": "policy_number",
        "policy_id": "policy_number",
        "insured_name": "insured_name",
        "life_assured": "insured_name",
        "owner_name": "insured_name",
        "customer_name": "insured_name",
        "insured_ic": "insured_ic",
        "owner_ic": "insured_ic",
        "nric": "insured_ic",
        "plan_name": "product_type",
        "plan_type": "product_type",
        "product_type": "product_type",
        "premium": "premium",
        "basic_premium": "premium",
        "total_premium": "premium",
        "sum_assured": "sum_insured",
        "sum_insured": "sum_insured",
        "commencement_date": "inception_date",
        "inception_date": "inception_date",
        "start_date": "inception_date",
        "maturity_date": "expiry_date",
        "expiry_date": "expiry_date",
        "valid_until": "expiry_date",
        "status": "status",
        "policy_status": "status",
    }

    def extract_policy(self, data: dict) -> Policy:
        """AIA-specific: life_assured is the insured, owner might differ."""
        p = super().extract_policy(data)

        # AIA often has life_assured as a separate name
        if not p.insured or not p.insured.name:
            life_assured = data.get("life_assured", "")
            if life_assured:
                p.insured = Insured(name=str(life_assured))

        # AIA uses policy_id more often
        if not p.policy_number:
            val = data.get("policy_id", "")
            if val:
                p.policy_number = str(val)

        return p
