"""InsureDesk — Claim Domain Model."""

from __future__ import annotations

from typing import Optional, List
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .base import BaseModel


class ClaimStatus(Enum):
    """Lifecycle status of a claim."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    SETTLED = "settled"
    WITHDRAWN = "withdrawn"
    UNKNOWN = "unknown"


@dataclass
class Incident(BaseModel):
    """Details of the insured incident."""
    date: Optional[date] = None
    type: str = ""                   # fire, theft, flood, accident
    description: str = ""
    location: str = ""
    estimated_loss: float = 0.0


@dataclass
class ClaimDocument(BaseModel):
    """A document attached to a claim."""
    doc_type: str = ""               # police_report, photo, receipt, assessment
    file_name: str = ""
    url: str = ""
    uploaded_at: Optional[date] = None


@dataclass
class Claim(BaseModel):
    """Insurance claim model.

    PortalAdapter.submit_claim() → Claim
    PortalAdapter.get_claim_status() → Claim
    """
    # ── Identification ──
    claim_id: str = ""
    policy_number: str = ""
    insurer: str = ""

    # ── Incident ──
    incident: Optional[Incident] = None

    # ── Status ──
    status: ClaimStatus = ClaimStatus.UNKNOWN
    claim_amount: float = 0.0
    approved_amount: float = 0.0

    # ── Dates ──
    submitted_date: Optional[date] = None
    decision_date: Optional[date] = None

    # ── Documents ──
    documents: List[ClaimDocument] = field(default_factory=list)

    # ── Metadata ──
    notes: str = ""
    source: str = ""
