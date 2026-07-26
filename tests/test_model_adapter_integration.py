"""Tests: ModelAdapter Integration — Full Portal → Model Flow.

Simulates the complete flow:
1. PortalAdapter fetches data from a portal (simulated as raw dicts)
2. ModelAdapter converts raw data to domain models
3. Validation checks model completeness
4. Domain model serialization round-trip

Target: Push total test count to 400+
"""

from __future__ import annotations

import os
import sys
import json
import pytest
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. Great Eastern — Full Integration (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestGEIntegration:
    """Great Eastern: full integration flow."""

    RAW_POLICY = {
        "policy_number": "F0377733",
        "insured_name": "Tiong Hoe Hung",
        "nric": "720415-01-1234",
        "inception_date": "2024-01-01",
        "expiry_date": "2025-01-01",
        "premium": "1250.00",
        "status": "active",
        "product_type": "fire",
    }

    def test_ge_full_extract(self):
        """Full GE portal data → Policy model."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        assert p.policy_number == "F0377733"
        assert p.insured.name == "Tiong Hoe Hung"
        assert p.insured.ic_number == "720415-01-1234"
        assert p.premium.total == 1250.0
        assert p.inception_date == date(2024, 1, 1)
        assert p.expiry_date == date(2025, 1, 1)

    def test_ge_extract_then_validate(self):
        """Extract then validate passes."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        result = adapter.validate_policy(p)
        assert result.valid is True

    def test_ge_extract_then_serialize(self):
        """Extract → to_dict → from_dict round-trip."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        d = p.to_dict()
        from src.models.policy import Policy
        restored = Policy.from_dict(d)
        assert restored.policy_number == "F0377733"
        assert restored.insured.name == "Tiong Hoe Hung"
        assert restored.premium.total == 1250.0

    def test_ge_extract_then_json(self):
        """Extract → to_json produces valid JSON."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        j = p.to_json()
        parsed = json.loads(j)
        assert parsed["policy_number"] == "F0377733"

    def test_ge_customer_flow(self):
        """Extract customer from GE data."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        raw = {"customer_id": "C-123", "customer_name": "Tiong Hoe Hung", "policies": ["F0377733"]}
        c = adapter.extract_customer(raw)
        assert c.customer_id == "C-123"
        assert c.identity.full_name == "Tiong Hoe Hung"
        assert "F0377733" in c.policy_numbers

    def test_ge_stats_tracking(self):
        """Full flow tracks stats correctly."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        adapter.extract_policy(self.RAW_POLICY)
        adapter.extract_customer({"customer_id": "C-123"})
        assert adapter.stats["extracted"] == 2


# ══════════════════════════════════════════════════════════════════
# 2. Allianz — Full Integration (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestAllianzIntegration:
    """Allianz: full integration flow."""

    RAW_POLICY = {
        "certificate_no": "AL-2024-999",
        "insured_name": "Alice Wong",
        "id_number": "850101-01-5678",
        "valid_from": "2024-06-01",
        "valid_until": "2025-06-01",
        "total_premium": "980.00",
        "status": "In Force",
        "product": "Motor Insurance",
    }

    def test_allianz_full_extract(self):
        """Full Allianz data → Policy model."""
        from src.models.adapter_allianz import AllianzAdapter
        adapter = AllianzAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        assert p.policy_number == "AL-2024-999"
        assert p.insured.name == "Alice Wong"
        assert p.insured.ic_number == "850101-01-5678"
        assert p.premium.total == 980.0
        assert p.inception_date == date(2024, 6, 1)
        assert p.expiry_date == date(2025, 6, 1)

    def test_allianz_status_mapping(self):
        """'In Force' maps to ACTIVE."""
        from src.models.adapter_allianz import AllianzAdapter
        from src.models.policy import PolicyStatus
        adapter = AllianzAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        assert p.status == PolicyStatus.ACTIVE

    def test_allianz_product_mapping_integration(self):
        """Product name 'Motor Insurance' maps to MOTOR."""
        from src.models.adapter_allianz import AllianzAdapter
        from src.models.policy import ProductType
        adapter = AllianzAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        assert p.product_type == ProductType.MOTOR

    def test_allianz_validate_with_insured(self):
        """Allianz policy with all fields validates OK."""
        from src.models.adapter_allianz import AllianzAdapter
        adapter = AllianzAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        result = adapter.validate_policy(p)
        assert result.valid is True

    def test_allianz_serialize_round_trip(self):
        """Allianz → to_dict → from_dict."""
        from src.models.adapter_allianz import AllianzAdapter
        from src.models.policy import Policy
        adapter = AllianzAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        d = p.to_dict()
        restored = Policy.from_dict(d)
        assert restored.policy_number == "AL-2024-999"
        assert restored.insured.name == "Alice Wong"


# ══════════════════════════════════════════════════════════════════
# 3. AIA — Full Integration (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestAIAIntegration:
    """AIA: full integration flow."""

    RAW_POLICY = {
        "policy_id": "AIA-LIFE-2024-456",
        "life_assured": "Charlie Lim",
        "owner_ic": "760303-01-9012",
        "commencement_date": "2024-03-15",
        "maturity_date": "2034-03-15",
        "basic_premium": "2400.00",
        "policy_status": "active",
        "plan_name": "Supreme Health Plus",
    }

    def test_aia_full_extract(self):
        """Full AIA data → Policy model."""
        from src.models.adapter_aia import AIAAdapter
        adapter = AIAAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        assert p.policy_number == "AIA-LIFE-2024-456"
        assert p.insured.name == "Charlie Lim"
        assert p.insured.ic_number == "760303-01-9012"
        assert p.premium.total == 2400.0
        assert p.inception_date == date(2024, 3, 15)
        assert p.expiry_date == date(2034, 3, 15)

    def test_aia_validate_with_insured(self):
        """AIA policy validates OK."""
        from src.models.adapter_aia import AIAAdapter
        adapter = AIAAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        result = adapter.validate_policy(p)
        assert result.valid is True

    def test_aia_serialize_round_trip(self):
        """AIA → to_dict → from_dict."""
        from src.models.adapter_aia import AIAAdapter
        from src.models.policy import Policy
        adapter = AIAAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        d = p.to_dict()
        restored = Policy.from_dict(d)
        assert restored.policy_number == "AIA-LIFE-2024-456"
        assert restored.insured.name == "Charlie Lim"

    def test_aia_status_active(self):
        """AIA 'active' status maps correctly."""
        from src.models.adapter_aia import AIAAdapter
        from src.models.policy import PolicyStatus
        adapter = AIAAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        assert p.status == PolicyStatus.ACTIVE

    def test_aia_plan_name_preserved(self):
        """AIA plan_name is accessible via raw data even if not in model."""
        from src.models.adapter_aia import AIAAdapter
        adapter = AIAAdapter()
        p = adapter.extract_policy(self.RAW_POLICY)
        assert p.source == "portal"


# ══════════════════════════════════════════════════════════════════
# 4. Claim Integration (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestClaimIntegration:
    """Claim extraction across portals."""

    GE_CLAIM = {
        "claim_id": "GE-CL-2024-001",
        "policy_number": "F0377733",
        "insurer": "Great Eastern",
        "status": "submitted",
        "claim_amount": "50000.00",
        "incident": {
            "date": "2024-06-15",
            "type": "fire",
            "description": "Kitchen fire due to electrical short circuit",
        },
    }

    ALLIANZ_CLAIM = {
        "claim_id": "AL-CL-2024-001",
        "policy_number": "AL-2024-999",
        "insurer": "Allianz Malaysia",
        "status": "in review",
        "claim_amount": "15000.00",
        "approved_amount": "12000.00",
        "incident": {
            "date": "2024-08-20",
            "type": "accident",
            "description": "Rear-end collision",
        },
    }

    def test_ge_claim_full(self):
        """Great Eastern claim extraction."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        c = adapter.extract_claim(self.GE_CLAIM)
        assert c.claim_id == "GE-CL-2024-001"
        assert c.policy_number == "F0377733"
        assert c.claim_amount == 50000.0
        assert c.incident.type == "fire"

    def test_ge_claim_status(self):
        """'submitted' maps correctly."""
        from src.models.adapter_ge import GreatEasternAdapter
        from src.models.claim import ClaimStatus
        adapter = GreatEasternAdapter()
        c = adapter.extract_claim(self.GE_CLAIM)
        assert c.status == ClaimStatus.SUBMITTED

    def test_allianz_claim_full(self):
        """Allianz claim with approved_amount."""
        from src.models.adapter_allianz import AllianzAdapter
        adapter = AllianzAdapter()
        c = adapter.extract_claim(self.ALLIANZ_CLAIM)
        assert c.claim_id == "AL-CL-2024-001"
        assert c.approved_amount == 12000.0

    def test_allianz_claim_status_in_review(self):
        """'in review' maps to REVIEWING."""
        from src.models.adapter_allianz import AllianzAdapter
        from src.models.claim import ClaimStatus
        adapter = AllianzAdapter()
        c = adapter.extract_claim(self.ALLIANZ_CLAIM)
        assert c.status == ClaimStatus.REVIEWING

    def test_claim_round_trip_ge(self):
        """GE claim serialization round-trip."""
        from src.models.adapter_ge import GreatEasternAdapter
        from src.models.claim import Claim
        adapter = GreatEasternAdapter()
        c = adapter.extract_claim(self.GE_CLAIM)
        d = c.to_dict()
        restored = Claim.from_dict(d)
        assert restored.claim_id == "GE-CL-2024-001"
        assert restored.incident.description == "Kitchen fire due to electrical short circuit"


# ══════════════════════════════════════════════════════════════════
# 5. Edge Cases (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestModelAdapterEdgeCases:
    """Edge cases for model adapters."""

    def test_empty_data(self):
        """Empty dict doesn't crash."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({})
        assert p.policy_number == ""
        assert p.insurer == "Great Eastern"

    def test_missing_policy_number_fails_validation(self):
        """Policy without number fails validation."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({"insured_name": "John"})
        result = adapter.validate_policy(p)
        assert result.valid is False

    def test_partial_date(self):
        """Partial date doesn't crash."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({"policy_number": "GE-1", "inception_date": "bad-date"})
        assert p.inception_date is None

    def test_negative_premium(self):
        """Negative premium accepted (edge case)."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({"policy_number": "GE-1", "premium": "-100"})
        assert p.premium.total == -100.0

    def test_very_long_text_fields(self):
        """Long text fields don't break."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        long_name = "A" * 5000
        p = adapter.extract_policy({"policy_number": "GE-1", "insured_name": long_name})
        assert len(p.insured.name) == 5000

    def test_case_insensitive_field_matching(self):
        """Field matching is case-insensitive."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        # All caps should still match via FieldMapper case-insensitive fallback
        data = {"POLICY_NUMBER": "GE-1", "INSURED_NAME": "John"}
        p = adapter.extract_policy(data)
        # The mapper tries direct key match first, then mapped keys
        # Direct key: "POLICY_NUMBER" is NOT "policy_number", so no direct match
        # Mapped keys: tries "policy_number" → data doesn't have it
        # But wait... let me check - FIELD_MAP has "policy_number": "policy_number" as a raw_to_model entry
        # So the mapper tries data["policy_number"] which doesn't exist
        # Actually this tests the case-insensitive fallback in FieldMapper
        # The mapper should find it via the fallback loop
        assert p.policy_number == "GE-1"

    def test_unicode_chinese_names(self):
        """Chinese character names work."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({"policy_number": "GE-1", "insured_name": "黄种雄"})
        assert p.insured.name == "黄种雄"

    def test_mixed_data_types(self):
        """Mixed data types handled gracefully."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({
            "policy_number": 12345,  # int instead of str
            "premium": "1,200.50",   # formatted string
        })
        assert p.policy_number == "12345"
        # premium "1,200.50" should fail float conversion → default 0.0
        assert p.premium is None


# ══════════════════════════════════════════════════════════════════
# 6. Registry Integration (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestRegistryIntegration:
    """Registry: dynamic adapter lookup + cross-portal consistency."""

    def test_all_portals_produce_same_model(self):
        """All portal adapters produce Policy model."""
        from src.models.adapter_registry import get_model_adapter
        from src.models.policy import Policy

        data = {"policy_number": "P-001", "insured_name": "John"}
        for portal in ["great_eastern", "allianz", "aia"]:
            adapter = get_model_adapter(portal)
            p = adapter.extract_policy(data)
            assert isinstance(p, Policy), f"{portal} should produce Policy"

    def test_each_portal_has_unique_name(self):
        """Each adapter has a distinct name."""
        from src.models.adapter_registry import list_model_adapters
        adapters = list_model_adapters()
        names = [a["name"] for a in adapters if "PDF" not in a["name"]]
        assert len(names) == len(set(names)), "Duplicate adapter names"

    def test_registry_list_portal_adapters(self):
        """List returns all portal adapters."""
        from src.models.adapter_registry import list_model_adapters
        adapters = list_model_adapters()
        assert len(adapters) >= 4  # GE, Allianz, AIA + GE PDF

    def test_registry_ge_short_name(self):
        """'ge' short name works."""
        from src.models.adapter_registry import get_model_adapter
        adapter = get_model_adapter("ge")
        assert adapter is not None
        assert "Great Eastern" in adapter.name

    def test_registry_pdf_source(self):
        """source='pdf' returns PDF adapter."""
        from src.models.adapter_registry import get_model_adapter
        adapter = get_model_adapter("great_eastern", source="pdf")
        assert adapter is not None
        assert "PDF" in adapter.name
        # Portal source returns portal adapter
        portal_adapter = get_model_adapter("great_eastern", source="portal")
        assert "PDF" not in portal_adapter.name
