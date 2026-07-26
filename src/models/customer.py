"""InsureDesk — Customer Domain Model."""

from __future__ import annotations

from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum

from .base import BaseModel


class ContactType(Enum):
    """Type of contact information."""
    PHONE = "phone"
    EMAIL = "email"
    ADDRESS = "address"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"


@dataclass
class Contact(BaseModel):
    """A single contact point."""
    type: ContactType = ContactType.PHONE
    value: str = ""
    is_primary: bool = False
    notes: str = ""


@dataclass
class Identity(BaseModel):
    """Identity information."""
    full_name: str = ""
    ic_number: str = ""           # NRIC / passport
    date_of_birth: str = ""
    nationality: str = "Malaysian"
    occupation: str = ""


@dataclass
class Customer(BaseModel):
    """Insurance customer / policyholder.

    PortalAdapter.search_customer() → Customer
    """
    # ── Identity ──
    customer_id: str = ""
    identity: Optional[Identity] = None

    # ── Contact ──
    contacts: List[Contact] = field(default_factory=list)

    # ── Relationships ──
    policy_numbers: List[str] = field(default_factory=list)
    claim_ids: List[str] = field(default_factory=list)

    # ── Metadata ──
    notes: str = ""
    source: str = ""
