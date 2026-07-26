"""InsureDesk — Insurance Domain Models.

Pure dataclasses with serialization support.
Cross-cutting: used by Portal adapters, PDF extractors, API clients.
Every model is a simple dataclass — no ORM, no business logic.
"""

from .policy import Policy, Coverage, CoverageSection, Insured, Premium, PolicyDocument, PolicyStatus, ProductType
from .claim import Claim, Incident, ClaimDocument, ClaimStatus
from .customer import Customer, Contact, Identity, ContactType
from .task import InsuranceTask, WorkflowState, TaskAction, TaskType
from .base import BaseModel

__all__ = [
    # Base
    "BaseModel",
    # Policy
    "Policy", "Coverage", "CoverageSection", "Insured", "Premium",
    "PolicyDocument", "PolicyStatus", "ProductType",
    # Claim
    "Claim", "Incident", "ClaimDocument", "ClaimStatus",
    # Customer
    "Customer", "Contact", "Identity", "ContactType",
    # Task
    "InsuranceTask", "WorkflowState", "TaskAction", "TaskType",
]
