"""InsureDesk — Policy Domain Model.

Core insurance policy: the central business object.
Every portal adapter, PDF extractor, and API returns this shape.
"""

from __future__ import annotations

from typing import Optional, List
from dataclasses import dataclass, field
from datetime import date
from enum import Enum, auto

from .base import BaseModel


class PolicyStatus(Enum):
    """Lifecycle status of a policy."""
    ACTIVE = "active"
    LAPSED = "lapsed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PENDING = "pending"
    UNDERWRITING = "underwriting"
    UNKNOWN = "unknown"


class ProductType(Enum):
    """Types of insurance products."""
    FIRE = "fire"
    MOTOR = "motor"
    HEALTH = "health"
    LIFE = "life"
    TRAVEL = "travel"
    HOME = "home"
    MARINE = "marine"
    ENGINEERING = "engineering"
    LIABILITY = "liability"
    PERSONAL_ACCIDENT = "personal_accident"
    UNKNOWN = "unknown"


@dataclass
class Insured(BaseModel):
    """The insured person or entity."""
    name: str = ""
    ic_number: str = ""          # NRIC / passport
    phone: str = ""
    email: str = ""
    address: str = ""


@dataclass
class Premium(BaseModel):
    """Premium details."""
    total: float = 0.0
    currency: str = "MYR"
    installment: str = ""         # yearly / half-yearly / quarterly
    due_date: Optional[date] = None
    paid: bool = False


@dataclass
class CoverageSection(BaseModel):
    """A single coverage section within a policy (e.g. Section I - Buildings)."""
    section: str = ""              # "I", "II", "A", "B"
    title: str = ""                # "Buildings", "Contents"
    sum_insured: float = 0.0
    premium: float = 0.0
    description: str = ""


@dataclass
class Coverage(BaseModel):
    """Full coverage breakdown."""
    total_sum_insured: float = 0.0
    sections: List[CoverageSection] = field(default_factory=list)
    excess: float = 0.0
    exclusions: List[str] = field(default_factory=list)


@dataclass
class PolicyDocument(BaseModel):
    """A document attached to or extracted from a policy."""
    doc_type: str = ""             # policy_schedule, endorsement, receipt
    file_name: str = ""
    url: str = ""
    pages: int = 0
    extracted_text: str = ""


@dataclass
class Policy(BaseModel):
    """Universal insurance policy model.

    The single source of truth for policy data.
    PortalAdapter.fetch_policy() → Policy
    PDFExtractor.extract() → Policy
    API.search_policies() → Policy[]
    """
    # ── Identification ──
    policy_number: str = ""
    insurer: str = ""               # "Great Eastern", "Allianz"
    product_type: ProductType = ProductType.UNKNOWN
    status: PolicyStatus = PolicyStatus.UNKNOWN

    # ── Parties ──
    insured: Optional[Insured] = None

    # ── Coverage ──
    coverage: Optional[Coverage] = None
    premium: Optional[Premium] = None

    # ── Dates ──
    inception_date: Optional[date] = None
    expiry_date: Optional[date] = None
    last_updated: Optional[date] = None

    # ── Documents ──
    documents: List[PolicyDocument] = field(default_factory=list)

    # ── Metadata ──
    source: str = ""                # "portal", "pdf", "api"
    source_url: str = ""
    raw_text: str = ""
