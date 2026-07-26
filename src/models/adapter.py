"""InsureDesk — Model Adapter.

Converts between domain models and external representations:
- Portal data (dict from YAML mapping)
- PDF extracted text
- API JSON responses

Each adapter is a function that takes raw data and returns a domain model.
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from datetime import date
import re

from .policy import Policy, PolicyStatus, ProductType, Insured, Coverage, CoverageSection, Premium
from .claim import Claim, ClaimStatus, Incident
from .customer import Customer, Identity, Contact, ContactType


# ══════════════════════════════════════════════════════════════════
# Policy Adapters
# ══════════════════════════════════════════════════════════════════

def policy_from_portal(portal_data: Dict[str, Any]) -> Policy:
    """Convert portal API response to Policy model."""
    p = Policy(
        policy_number=portal_data.get("policy_number", ""),
        insurer=portal_data.get("insurer", ""),
        source="portal",
        source_url=portal_data.get("url", ""),
        status=_parse_status(portal_data.get("status", "")),
        product_type=_parse_product(portal_data.get("product_type", "")),
    )

    # Insured
    if "insured_name" in portal_data:
        p.insured = Insured(
            name=portal_data.get("insured_name", ""),
            ic_number=portal_data.get("insured_ic", ""),
        )

    # Dates
    for field, key in [("inception_date", "inception_date"),
                       ("expiry_date", "expiry_date"),
                       ("last_updated", "last_updated")]:
        val = portal_data.get(key, "")
        if val:
            try:
                setattr(p, field, date.fromisoformat(val))
            except (ValueError, TypeError):
                pass

    # Premium
    premium_val = portal_data.get("premium", 0)
    if premium_val:
        p.premium = Premium(
            total=float(premium_val),
            currency=portal_data.get("currency", "MYR"),
        )

    return p


def policy_from_pdf_extraction(extracted: Dict[str, Any]) -> Policy:
    """Convert PDF extraction result to Policy model.

    extracted is the normalized output from Document Intelligence SDK.
    """
    p = Policy(
        policy_number=extracted.get("policy_number", ""),
        insurer=extracted.get("insurer", ""),
        source="pdf",
        raw_text=extracted.get("raw_text", ""),
    )

    # The PDF extraction gives structured fields
    if "insured" in extracted:
        ins = extracted["insured"]
        p.insured = Insured(
            name=ins.get("name", ""),
            ic_number=ins.get("ic_number", "") or ins.get("nric", ""),
            address=ins.get("address", ""),
        )

    # Coverage from extracted sections
    sections_raw = extracted.get("sections", []) or extracted.get("coverages", [])
    if sections_raw:
        sections = []
        for s in sections_raw:
            if isinstance(s, dict):
                sections.append(CoverageSection(
                    section=s.get("section", s.get("id", "")),
                    title=s.get("title", s.get("name", "")),
                    sum_insured=float(s.get("sum_insured", 0) or 0),
                    premium=float(s.get("premium", 0) or 0),
                    description=s.get("description", s.get("text", "")),
                ))
        p.coverage = Coverage(
            total_sum_insured=float(extracted.get("total_sum_insured", 0) or 0),
            sections=sections,
        )

    # Premium
    premium_val = extracted.get("premium", 0)
    if premium_val:
        p.premium = Premium(total=float(premium_val))

    # Dates
    for field_name, key in [("inception_date", "inception_date"),
                            ("expiry_date", "expiry_date")]:
        val = extracted.get(key, "")
        if val:
            try:
                setattr(p, field_name, date.fromisoformat(val))
            except (ValueError, TypeError):
                pass

    return p


# ══════════════════════════════════════════════════════════════════
# Claim Adapters
# ══════════════════════════════════════════════════════════════════

def claim_from_portal(portal_data: Dict[str, Any]) -> Claim:
    """Convert portal claim response to Claim model."""
    c = Claim(
        claim_id=portal_data.get("claim_id", "") or portal_data.get("reference", ""),
        policy_number=portal_data.get("policy_number", ""),
        insurer=portal_data.get("insurer", ""),
        status=_parse_claim_status(portal_data.get("status", "")),
        claim_amount=float(portal_data.get("claim_amount", 0) or 0),
        approved_amount=float(portal_data.get("approved_amount", 0) or 0),
        source="portal",
    )

    # Incident
    inc_data = portal_data.get("incident", {})
    if isinstance(inc_data, dict):
        c.incident = Incident(
            date=_try_parse_date(inc_data.get("date", "")),
            type=inc_data.get("type", ""),
            description=inc_data.get("description", ""),
            estimated_loss=float(inc_data.get("estimated_loss", 0) or 0),
        )

    return c


# ══════════════════════════════════════════════════════════════════
# Customer Adapters
# ══════════════════════════════════════════════════════════════════

def customer_from_portal(portal_data: Dict[str, Any]) -> Customer:
    """Convert portal customer response to Customer model."""
    return Customer(
        customer_id=portal_data.get("customer_id", "") or portal_data.get("id", ""),
        identity=Identity(
            full_name=portal_data.get("name", ""),
            ic_number=portal_data.get("ic_number", "") or portal_data.get("nric", ""),
            nationality=portal_data.get("nationality", "Malaysian"),
        ),
        policy_numbers=portal_data.get("policies", []) or portal_data.get("policy_numbers", []),
        source="portal",
    )


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def _parse_status(s: str) -> PolicyStatus:
    s = s.strip().lower()
    mapping = {
        "active": PolicyStatus.ACTIVE,
        "in force": PolicyStatus.ACTIVE,
        "lapsed": PolicyStatus.LAPSED,
        "cancelled": PolicyStatus.CANCELLED,
        "expired": PolicyStatus.EXPIRED,
        "pending": PolicyStatus.PENDING,
    }
    return mapping.get(s, PolicyStatus.UNKNOWN)


def _parse_product(s: str) -> ProductType:
    s = s.strip().lower().replace(" ", "_")
    for pt in ProductType:
        if pt.value == s:
            return pt
    # Fuzzy match
    if "fire" in s or "home" in s:
        return ProductType.FIRE
    if "motor" in s or "car" in s or "auto" in s:
        return ProductType.MOTOR
    if "health" in s or "medical" in s:
        return ProductType.HEALTH
    return ProductType.UNKNOWN


def _parse_claim_status(s: str) -> ClaimStatus:
    s = s.strip().lower()
    mapping = {
        "draft": ClaimStatus.DRAFT,
        "submitted": ClaimStatus.SUBMITTED,
        "in review": ClaimStatus.REVIEWING,
        "reviewing": ClaimStatus.REVIEWING,
        "approved": ClaimStatus.APPROVED,
        "rejected": ClaimStatus.REJECTED,
        "settled": ClaimStatus.SETTLED,
        "paid": ClaimStatus.SETTLED,
        "withdrawn": ClaimStatus.WITHDRAWN,
    }
    return mapping.get(s, ClaimStatus.UNKNOWN)


def _try_parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        pass
    # Try dd/mm/yyyy
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None
