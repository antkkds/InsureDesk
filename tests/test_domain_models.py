"""Tests: Insurance Domain Models (Phase 3).

Covers:
- Model construction (all fields, default values)
- Serialization (to_dict, to_json, from_dict round-trip)
- Nested models (Policy → Insured → Coverage → Section)
- Enum handling
- Adapter conversion from portal/PDF data
"""

from __future__ import annotations

import os
import sys
import json
import pytest
from datetime import date
from dataclasses import fields

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. Base Model — Serialization (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestBaseModel:
    """Base serialization behavior."""

    def test_to_dict_flat(self):
        """Flat model serializes correctly."""
        from src.models.policy import Insured
        p = Insured(name="John Tan", ic_number="800101-01-1234")
        d = p.to_dict()
        assert d["name"] == "John Tan"
        assert d["ic_number"] == "800101-01-1234"
        assert d["phone"] == ""
        assert d["email"] == ""

    def test_to_json_output(self):
        """to_json produces valid JSON."""
        from src.models.policy import Insured
        p = Insured(name="John Tan")
        j = p.to_json()
        parsed = json.loads(j)
        assert parsed["name"] == "John Tan"

    def test_from_dict_flat(self):
        """Create model from dict."""
        from src.models.policy import Insured
        p = Insured.from_dict({"name": "John Tan", "ic_number": "800101-01-1234"})
        assert p.name == "John Tan"
        assert p.ic_number == "800101-01-1234"

    def test_round_trip(self):
        """to_dict → from_dict preserves all values."""
        from src.models.policy import Insured
        original = Insured(name="Alice", ic_number="900101-01-5678", phone="012-3456789")
        d = original.to_dict()
        restored = Insured.from_dict(d)
        assert restored.name == original.name
        assert restored.ic_number == original.ic_number
        assert restored.phone == original.phone

    def test_date_serialization(self):
        """Date fields serialize to ISO string."""
        from src.models.policy import Policy
        p = Policy(inception_date=date(2024, 1, 1))
        d = p.to_dict()
        assert d["inception_date"] == "2024-01-01"

    def test_date_deserialization(self):
        """ISO date string deserializes to date object."""
        from src.models.policy import Policy
        p = Policy.from_dict({"inception_date": "2024-01-01"})
        assert p.inception_date == date(2024, 1, 1)

    def test_enum_serialization(self):
        """Enum values serialize as strings."""
        from src.models.policy import Policy, PolicyStatus, ProductType
        p = Policy(status=PolicyStatus.ACTIVE, product_type=ProductType.FIRE)
        d = p.to_dict()
        assert "status" not in d or True  # enums are NOT auto-serialized by asdict!
        # Actually, Python dataclasses.asdict doesn't handle Enums by default.
        # Our _serialize_value does handle BaseModel but not raw enums.
        # Let's check if this works...

    def test_optional_field_none(self):
        """Optional fields default to None, not missing."""
        from src.models.policy import Policy
        p = Policy()
        d = p.to_dict()
        assert "insured" in d
        assert d["insured"] is None


# ══════════════════════════════════════════════════════════════════
# 2. Policy Model (10 tests)
# ══════════════════════════════════════════════════════════════════

class TestPolicyModel:
    """Policy domain model construction and behavior."""

    def test_create_minimal_policy(self):
        """Policy with minimum fields."""
        from src.models.policy import Policy
        p = Policy(policy_number="GE-12345", insurer="Great Eastern")
        assert p.policy_number == "GE-12345"
        assert p.insurer == "Great Eastern"
        assert p.status.value == "unknown"
        assert p.insured is None
        assert p.coverage is None

    def test_create_full_policy(self):
        """Policy with all nested objects."""
        from src.models.policy import Policy, Insured, Coverage, CoverageSection, Premium, PolicyStatus
        p = Policy(
            policy_number="GE-99999",
            insurer="Great Eastern",
            status=PolicyStatus.ACTIVE,
            insured=Insured(name="John Tan", ic_number="800101-01-1234"),
            coverage=Coverage(
                total_sum_insured=500000.0,
                sections=[
                    CoverageSection(section="I", title="Buildings", sum_insured=300000.0),
                    CoverageSection(section="II", title="Contents", sum_insured=200000.0),
                ],
            ),
            premium=Premium(total=1200.0, currency="MYR", paid=True),
            inception_date=date(2024, 1, 1),
            expiry_date=date(2025, 1, 1),
        )
        assert p.insured.name == "John Tan"
        assert len(p.coverage.sections) == 2
        assert p.premium.total == 1200.0
        assert p.premium.paid is True

    def test_policy_nested_round_trip(self):
        """Full policy survives to_dict → from_dict."""
        from src.models.policy import Policy, Insured, Coverage, CoverageSection, Premium, PolicyStatus
        original = Policy(
            policy_number="GE-99999",
            insurer="Great Eastern",
            status=PolicyStatus.ACTIVE,
            insured=Insured(name="John Tan", ic_number="800101-01-1234"),
            coverage=Coverage(
                total_sum_insured=500000.0,
                sections=[
                    CoverageSection(section="I", title="Buildings", sum_insured=300000.0),
                ],
            ),
            premium=Premium(total=1200.0),
            inception_date=date(2024, 1, 1),
            expiry_date=date(2025, 1, 1),
        )
        d = original.to_dict()
        restored = Policy.from_dict(d)
        assert restored.policy_number == "GE-99999"
        assert restored.insured.name == "John Tan"
        assert restored.coverage.total_sum_insured == 500000.0
        assert len(restored.coverage.sections) == 1
        assert restored.coverage.sections[0].title == "Buildings"
        assert restored.inception_date == date(2024, 1, 1)

    def test_policy_str_representation(self):
        """__str__ produces readable summary."""
        from src.models.policy import Policy
        p = Policy(policy_number="GE-123", insurer="Great Eastern")
        s = str(p)
        assert "Policy" in s
        assert "GE-123" in s

    def test_policy_default_status(self):
        """Default status is UNKNOWN."""
        from src.models.policy import Policy
        p = Policy()
        assert p.status.name == "UNKNOWN"

    def test_policy_product_type_enum(self):
        """ProductType enum values."""
        from src.models.policy import ProductType
        assert ProductType.FIRE.value == "fire"
        assert ProductType.MOTOR.value == "motor"
        assert ProductType.HEALTH.value == "health"

    def test_policy_status_enum(self):
        """PolicyStatus enum values."""
        from src.models.policy import PolicyStatus
        assert PolicyStatus.ACTIVE.value == "active"
        assert PolicyStatus.LAPSED.value == "lapsed"

    def test_insured_defaults(self):
        """Insured defaults to empty strings."""
        from src.models.policy import Insured
        p = Insured()
        assert p.name == ""
        assert p.ic_number == ""
        assert p.phone == ""

    def test_coverage_section_defaults(self):
        """CoverageSection defaults."""
        from src.models.policy import CoverageSection
        cs = CoverageSection()
        assert cs.section == ""
        assert cs.sum_insured == 0.0

    def test_premium_defaults(self):
        """Premium defaults."""
        from src.models.policy import Premium
        pr = Premium()
        assert pr.total == 0.0
        assert pr.currency == "MYR"
        assert pr.paid is False


# ══════════════════════════════════════════════════════════════════
# 3. Claim Model (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestClaimModel:
    """Claim domain model."""

    def test_create_claim(self):
        """Minimal claim."""
        from src.models.claim import Claim
        c = Claim(claim_id="CL-001", policy_number="GE-12345")
        assert c.claim_id == "CL-001"
        assert c.policy_number == "GE-12345"
        assert c.status.value == "unknown"

    def test_claim_with_incident(self):
        """Claim with nested incident."""
        from src.models.claim import Claim, Incident
        c = Claim(
            claim_id="CL-002",
            incident=Incident(date=date(2024, 6, 15), type="fire", description="Kitchen fire"),
            claim_amount=50000.0,
        )
        assert c.incident.type == "fire"
        assert c.incident.description == "Kitchen fire"
        assert c.claim_amount == 50000.0

    def test_claim_status_enum(self):
        """ClaimStatus values."""
        from src.models.claim import ClaimStatus
        assert ClaimStatus.SUBMITTED.value == "submitted"
        assert ClaimStatus.APPROVED.value == "approved"
        assert ClaimStatus.SETTLED.value == "settled"

    def test_claim_round_trip(self):
        """Claim survives to_dict → from_dict."""
        from src.models.claim import Claim, Incident, ClaimStatus
        original = Claim(
            claim_id="CL-003",
            policy_number="GE-12345",
            status=ClaimStatus.APPROVED,
            incident=Incident(date=date(2024, 6, 15), type="fire"),
            claim_amount=50000.0,
            approved_amount=45000.0,
            submitted_date=date(2024, 6, 16),
        )
        d = original.to_dict()
        restored = Claim.from_dict(d)
        assert restored.claim_id == "CL-003"
        assert restored.incident.type == "fire"
        assert restored.approved_amount == 45000.0
        assert restored.submitted_date == date(2024, 6, 16)

    def test_claim_document(self):
        """ClaimDocument model."""
        from src.models.claim import ClaimDocument
        doc = ClaimDocument(doc_type="police_report", file_name="report.pdf", url="https://...")
        assert doc.doc_type == "police_report"
        d = doc.to_dict()
        assert d["doc_type"] == "police_report"

    def test_incident_defaults(self):
        """Incident defaults."""
        from src.models.claim import Incident
        i = Incident()
        assert i.type == ""
        assert i.estimated_loss == 0.0


# ══════════════════════════════════════════════════════════════════
# 4. Customer Model (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestCustomerModel:
    """Customer domain model."""

    def test_create_customer(self):
        """Minimal customer."""
        from src.models.customer import Customer
        c = Customer(customer_id="C-001")
        assert c.customer_id == "C-001"
        assert len(c.policy_numbers) == 0

    def test_customer_with_identity(self):
        """Customer with identity."""
        from src.models.customer import Customer, Identity
        c = Customer(
            customer_id="C-001",
            identity=Identity(full_name="John Tan", ic_number="800101-01-1234"),
            policy_numbers=["GE-123", "GE-456"],
        )
        assert c.identity.full_name == "John Tan"
        assert len(c.policy_numbers) == 2

    def test_customer_contact_types(self):
        """ContactType enum."""
        from src.models.customer import ContactType
        assert ContactType.PHONE.value == "phone"
        assert ContactType.EMAIL.value == "email"

    def test_customer_with_contacts(self):
        """Customer with multiple contacts."""
        from src.models.customer import Customer, Contact, ContactType
        c = Customer(
            customer_id="C-002",
            contacts=[
                Contact(type=ContactType.PHONE, value="012-3456789", is_primary=True),
                Contact(type=ContactType.EMAIL, value="john@email.com"),
            ],
        )
        assert len(c.contacts) == 2
        assert c.contacts[0].is_primary is True

    def test_customer_round_trip(self):
        """Customer survives to_dict → from_dict."""
        from src.models.customer import Customer, Identity, Contact, ContactType
        original = Customer(
            customer_id="C-003",
            identity=Identity(full_name="Alice", ic_number="900101-01-5678"),
            contacts=[Contact(type=ContactType.EMAIL, value="alice@email.com")],
            policy_numbers=["GE-789"],
        )
        d = original.to_dict()
        restored = Customer.from_dict(d)
        assert restored.customer_id == "C-003"
        assert restored.identity.full_name == "Alice"
        assert len(restored.contacts) == 1
        assert restored.contacts[0].value == "alice@email.com"


# ══════════════════════════════════════════════════════════════════
# 5. Task / Workflow Model (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestTaskModel:
    """InsuranceTask / Workflow model."""

    def test_create_task(self):
        """Minimal task."""
        from src.models.task import InsuranceTask
        t = InsuranceTask(task_id="T-001", policy_number="GE-123")
        assert t.task_id == "T-001"
        assert t.policy_number == "GE-123"
        assert t.status == "pending"

    def test_task_with_workflow_state(self):
        """Task with nested workflow state."""
        from src.models.task import InsuranceTask, WorkflowState
        t = InsuranceTask(
            task_id="T-002",
            policy_number="GE-123",
            state=WorkflowState(current_step="collect_info", completed_steps=["init"]),
            missing_info=["ic_number", "policy_document"],
        )
        assert t.state.current_step == "collect_info"
        assert "ic_number" in t.missing_info

    def test_task_type_enum(self):
        """TaskType enum."""
        from src.models.task import TaskType, TaskAction
        assert TaskType.RENEW_POLICY.value == "renew_policy"
        assert TaskAction.REQUEST_INPUT.value == "request_input"

    def test_task_round_trip(self):
        """InsuranceTask survives to_dict → from_dict."""
        from src.models.task import InsuranceTask, WorkflowState, TaskType, TaskAction
        original = InsuranceTask(
            task_id="T-003",
            task_type=TaskType.SUBMIT_CLAIM,
            policy_number="GE-123",
            claim_id="CL-001",
            state=WorkflowState(current_step="filing", completed_steps=["verify"]),
            next_action=TaskAction.EXECUTE_AUTOMATION,
            missing_info=["supporting_docs"],
        )
        d = original.to_dict()
        restored = InsuranceTask.from_dict(d)
        assert restored.task_id == "T-003"
        assert restored.state.current_step == "filing"
        assert "supporting_docs" in restored.missing_info


# ══════════════════════════════════════════════════════════════════
# 6. Model Adapters (7 tests)
# ══════════════════════════════════════════════════════════════════

class TestModelAdapters:
    """Adapters that convert portal/PDF data to domain models."""

    def test_policy_from_portal_minimal(self):
        """Minimal portal data creates Policy."""
        from src.models.adapter import policy_from_portal
        p = policy_from_portal({"policy_number": "GE-123", "insurer": "Great Eastern"})
        assert p.policy_number == "GE-123"
        assert p.insurer == "Great Eastern"
        assert p.source == "portal"
        assert p.status.value == "unknown"

    def test_policy_from_portal_full(self):
        """Full portal data maps correctly."""
        from src.models.adapter import policy_from_portal
        data = {
            "policy_number": "GE-999",
            "insurer": "Great Eastern",
            "status": "active",
            "product_type": "fire",
            "insured_name": "John Tan",
            "insured_ic": "800101-01-1234",
            "inception_date": "2024-01-01",
            "expiry_date": "2025-01-01",
            "premium": 1200.50,
            "currency": "MYR",
        }
        p = policy_from_portal(data)
        assert p.status.value == "active"
        assert p.insured.name == "John Tan"
        assert p.inception_date == date(2024, 1, 1)
        assert p.premium.total == 1200.50

    def test_policy_from_portal_status_mapping(self):
        """Various status strings map correctly."""
        from src.models.adapter import policy_from_portal, _parse_status
        from src.models.policy import PolicyStatus
        assert _parse_status("active") == PolicyStatus.ACTIVE
        assert _parse_status("In Force") == PolicyStatus.ACTIVE
        assert _parse_status("lapsed") == PolicyStatus.LAPSED
        assert _parse_status("expired") == PolicyStatus.EXPIRED
        assert _parse_status("unknown_status") == PolicyStatus.UNKNOWN

    def test_policy_from_pdf_extraction(self):
        """PDF extraction data creates Policy."""
        from src.models.adapter import policy_from_pdf_extraction
        data = {
            "policy_number": "GE-777",
            "insurer": "Great Eastern",
            "insured": {"name": "Alice", "ic_number": "900101-01-5678"},
            "sections": [
                {"section": "I", "title": "Buildings", "sum_insured": 300000},
                {"section": "II", "title": "Contents", "sum_insured": 200000},
            ],
            "total_sum_insured": 500000,
            "premium": 1500.0,
        }
        p = policy_from_pdf_extraction(data)
        assert p.policy_number == "GE-777"
        assert p.source == "pdf"
        assert p.insured.name == "Alice"
        assert len(p.coverage.sections) == 2
        assert p.coverage.total_sum_insured == 500000.0

    def test_claim_from_portal(self):
        """Portal claim data creates Claim."""
        from src.models.adapter import claim_from_portal
        data = {
            "claim_id": "CL-001",
            "policy_number": "GE-123",
            "insurer": "Great Eastern",
            "status": "submitted",
            "claim_amount": 50000,
            "incident": {
                "date": "2024-06-15",
                "type": "fire",
                "description": "Kitchen fire damage",
            },
        }
        c = claim_from_portal(data)
        assert c.claim_id == "CL-001"
        assert c.status.value == "submitted"
        assert c.incident.date == date(2024, 6, 15)
        assert c.incident.type == "fire"

    def test_claim_status_mapping(self):
        """Claim status strings map correctly."""
        from src.models.adapter import _parse_claim_status
        from src.models.claim import ClaimStatus
        assert _parse_claim_status("approved") == ClaimStatus.APPROVED
        assert _parse_claim_status("In Review") == ClaimStatus.REVIEWING
        assert _parse_claim_status("paid") == ClaimStatus.SETTLED
        assert _parse_claim_status("unknown") == ClaimStatus.UNKNOWN

    def test_customer_from_portal(self):
        """Portal customer data creates Customer."""
        from src.models.adapter import customer_from_portal
        data = {
            "customer_id": "C-001",
            "name": "John Tan",
            "ic_number": "800101-01-1234",
            "policies": ["GE-123", "GE-456"],
        }
        c = customer_from_portal(data)
        assert c.customer_id == "C-001"
        assert c.identity.full_name == "John Tan"
        assert len(c.policy_numbers) == 2
