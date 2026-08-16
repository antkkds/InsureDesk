"""PA-8.2 — IdentityRequirements (per-product identity field requirements).

ChatGPT (2026-08-16): shared IdentityData ≠ every product needs the same
identity fields. PA needs id_number + dob + gender; Motor needs id_number +
full_name. The requirements are PROFILE-DRIVEN — each product declares
``identity_requirements`` in its binding YAML, so identity assumptions never
leak across products.

    IdentityData
        │
        ▼
    IdentityRequirements     ← declared in the product's binding YAML
        │
   ┌────┴─────┐
  PA         Motor

PA profile (pa_easi_protector.yaml):
    identity_requirements:
      required: [id_number, dob, gender]

Motor profile (motor_private_car.yaml):
    identity_requirements:
      required: [id_number, full_name]
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.identity.errors import IdentityRequirementError, MissingIdentityFieldError
from src.identity.models import IdentityData


def _resolve_profile(profile_path: str) -> str:
    """Resolve a relative profile path against the repo root.

    Tests may chdir; the binding profiles are declared repo-relative
    ("src/portal/forms/*.yaml") — resolve them against the project root so
    CWD changes never break loading.
    """
    if Path(profile_path).is_absolute():
        return profile_path
    root = Path(__file__).resolve().parent.parent.parent
    candidate = root / profile_path
    if candidate.exists():
        return str(candidate)
    return profile_path


class IdentityRequirements:
    """Which identity fields a product REQUIRES for a valid quote request."""

    def __init__(self, product: str, required: List[str]) -> None:
        self.product = product
        self.required = list(required)

    # ── Construction ───────────────────────────────────────────────────────

    @classmethod
    def from_binding(cls, binding) -> "IdentityRequirements":
        """Load from a ProductBinding (Capability → Binding → Profile).

        Capabilities never reference YAML paths directly — the binding owns
        the profile (ChatGPT PA-8.2: Capability → Binding → Profile, not
        the reverse).
        """
        return cls.from_profile(binding.profile, product=binding.product)

    @classmethod
    def from_profile(cls, profile_path: str, product: Optional[str] = None) -> "IdentityRequirements":
        """Load requirements from a binding YAML's ``identity_requirements``."""
        import yaml

        profile_path = _resolve_profile(profile_path)
        with open(profile_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        req = (data.get("identity_requirements") or {})
        required = [str(f) for f in (req.get("required") or [])]
        return cls(
            product=product or str(data.get("product_id") or "unknown"),
            required=required,
        )

    @classmethod
    def none(cls, product: str) -> "IdentityRequirements":
        return cls(product=product, required=[])

    # ── Behavior ───────────────────────────────────────────────────────────

    def missing_fields(self, identity: IdentityData) -> List[str]:
        """Fields in ``required`` that the identity does not carry."""
        present = {
            "id_type": bool(identity.id_type),
            "id_number": bool(identity.id_number.strip()),
            "full_name": bool(identity.full_name.strip()),
            "dob": identity.dob is not None,
            "gender": bool(identity.gender.strip()),
            "nationality": bool((identity.nationality or "").strip()),
        }
        return [f for f in self.required if not present.get(f, False)]

    def check(self, identity: IdentityData) -> None:
        """Raise IdentityRequirementError when requirements are unmet."""
        missing = self.missing_fields(identity)
        if missing:
            raise IdentityRequirementError(missing)

    def check_optional(self, identity: IdentityData) -> List[str]:
        """Non-raising variant: returns missing fields (empty = satisfied)."""
        return self.missing_fields(identity)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product": self.product,
            "required": list(self.required),
        }


class ContactRequirements:
    """POL-1: customer contact/address fields a product REQUIRES.

    Same profile-driven pattern as IdentityRequirements but for the
    applicant's contact block (mobile/email/address1/state). These are
    NEVER defaulted from test fixtures — a missing contact field fails
    validation so the operator asks the customer instead of fabricating.
    """

    def __init__(self, product: str, required: List[str]) -> None:
        self.product = product
        self.required = list(required)

    @classmethod
    def from_binding(cls, binding) -> "ContactRequirements":
        return cls.from_profile(binding.profile, product=binding.product)

    @classmethod
    def from_profile(cls, profile_path: str, product: Optional[str] = None) -> "ContactRequirements":
        import yaml

        profile_path = _resolve_profile(profile_path)
        with open(profile_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        req = (data.get("contact_requirements") or {})
        required = [str(f) for f in (req.get("required") or [])]
        return cls(
            product=product or str(data.get("product_id") or "unknown"),
            required=required,
        )

    @classmethod
    def none(cls, product: str) -> "ContactRequirements":
        return cls(product=product, required=[])

    def missing_fields(self, applicant: Dict[str, Any]) -> List[str]:
        return [f for f in self.required if not str(applicant.get(f, "")).strip()]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product": self.product,
            "required": list(self.required),
        }


# ── Defaults (source of truth: binding YAMLs; these mirror them) ──────────

PA_PROFILE = "src/portal/forms/pa_easi_protector.yaml"
MOTOR_PROFILE = "src/portal/forms/motor_private_car.yaml"

@lru_cache(maxsize=8)
def pa_requirements() -> IdentityRequirements:
    return IdentityRequirements.from_profile(PA_PROFILE, product="pa")


@lru_cache(maxsize=8)
def motor_requirements() -> IdentityRequirements:
    return IdentityRequirements.from_profile(MOTOR_PROFILE, product="motor")
