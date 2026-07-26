"""InsureDesk — Allianz Malaysia ModelAdapter.

Allianz field naming convention (from portal YAML):
  - certificate_no / policy_number
  - insured_name
  - id_number
  - product
  - sum_insured
  - total_premium
  - inception / valid_from
  - expiry / valid_to
  - policy_status / status
"""

from typing import Dict, Any, List

from src.models.adapter_base import ModelAdapter
from src.models.policy import Policy, Insured, Premium, ProductType


class AllianzAdapter(ModelAdapter):
    """ModelAdapter for Allianz Malaysia Insurance portal."""

    PORTAL_NAME = "Allianz Malaysia"

    FIELD_MAP: Dict[str, str] = {
        "policy_number": "policy_number",
        "certificate_no": "policy_number",
        "certificate_number": "policy_number",
        "insured_name": "insured_name",
        "customer_name": "insured_name",
        "id_number": "insured_ic",
        "nric": "insured_ic",
        "product": "product_type",
        "product_type": "product_type",
        "sum_insured": "sum_insured",
        "premium": "premium",
        "total_premium": "premium",
        "inception": "inception_date",
        "valid_from": "inception_date",
        "start_date": "inception_date",
        "expiry": "expiry_date",
        "valid_to": "expiry_date",
        "valid_until": "expiry_date",
        "end_date": "expiry_date",
        "status": "status",
        "policy_status": "status",
    }

    REQUIRED_POLICY_FIELDS: List[str] = ["policy_number"]

    def extract_policy(self, data: Dict[str, Any]) -> Policy:
        """Allianz-specific: certificate_no is primary key."""
        p = super().extract_policy(data)

        # Allianz uses certificate_no
        if not p.policy_number:
            for key in ["certificate_no", "certificate_number"]:
                val = data.get(key, "")
                if val:
                    p.policy_number = str(val)
                    break

        # Allianz often has product name instead of enum; normalize
        product = self.mapper.get(data, "product_type", "")
        if product and p.product_type == ProductType.UNKNOWN:
            product_lower = product.lower()
            if "fire" in product_lower:
                p.product_type = ProductType.FIRE
            elif "motor" in product_lower or "car" in product_lower:
                p.product_type = ProductType.MOTOR

        return p
