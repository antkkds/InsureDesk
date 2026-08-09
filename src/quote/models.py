"""InsureDesk — Quote Engine Domain Models.

Data models for insurance quotations across all carriers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Dict, Any, List
from enum import Enum, auto


class QuoteStatus(Enum):
    DRAFT = "draft"
    CALCULATED = "calculated"
    SAVED = "saved"
    SUBMITTED = "submitted"
    EXPIRED = "expired"
    ERROR = "error"


class RiskClass(Enum):
    """Common risk/occupation classifications."""
    FIRE = "fire"
    ENGINEERING = "engineering"
    MOTOR = "motor"
    MARINE = "marine"
    PERSONAL_ACCIDENT = "personal_accident"
    MEDICAL = "medical"
    TRAVEL = "travel"
    LIABILITY = "liability"
    UNKNOWN = "unknown"


@dataclass
class QuoteItem:
    """A single item/asset being quoted."""
    description: str = ""
    sum_insured: float = 0.0
    risk_class: str = ""
    location: str = ""
    occupation: str = ""
    industry: str = ""


@dataclass
class QuoteRequest:
    """A complete quotation request."""
    # Portal info
    portal: str = ""
    adapter: str = ""
    channel_type: str = ""  # IFE or EQ

    # Policy holder
    proposer_name: str = ""
    proposer_ic: str = ""
    proposer_email: str = ""
    proposer_phone: str = ""

    # Coverage
    cover_type: str = ""
    risk_class: str = ""
    items: List[QuoteItem] = field(default_factory=list)

    # Period
    inception_date: Optional[date] = None
    expiry_date: Optional[date] = None
    policy_term_years: int = 1

    # Additional data (portal-specific)
    additional_data: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    session_id: str = ""


@dataclass
class QuoteResult:
    """Result from a quote calculation."""
    status: QuoteStatus = QuoteStatus.DRAFT
    quote_number: str = ""
    gross_premium: float = 0.0
    net_premium: float = 0.0
    tax_amount: float = 0.0
    stamp_duty: float = 0.0
    total_premium: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)
    message: str = ""
    errors: List[str] = field(default_factory=list)
    raw_response: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return self.status == QuoteStatus.CALCULATED and self.total_premium > 0


@dataclass
class QuoteDraft:
    """A saved quote draft reference."""
    draft_id: str = ""
    quote_number: str = ""
    channel_type: str = ""
    portal: str = ""
    status: QuoteStatus = QuoteStatus.DRAFT
    total_premium: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expiry_date: Optional[date] = None
    data: Dict[str, Any] = field(default_factory=dict)
