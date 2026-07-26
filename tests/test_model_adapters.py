"""Tests: ModelAdapter Layer (Phase 4).

Covers:
- Base ModelAdapter field mapping + validation
- Great Eastern adapter (portal + PDF)
- Allianz adapter
- AIA adapter
- Integration: PortalAdapter → ModelAdapter flow
- Target: 80+ new tests (321 → 400+)
"""

from __future__ import annotations

import os
import sys
import pytest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. Base ModelAdapter — Field Mapping (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestFieldMapper:
    """FieldMapper utility."""

    def test_basic_mapping(self):
        """FieldMapper maps raw → model fields."""
        from src.models.adapter_base import FieldMapper
        m = FieldMapper({"policy_no": "policy_number"})
        assert m.get({"policy_no": "GE-123"}, "policy_number") == "GE-123"

    def test_default_value(self):
        """Missing keys return default."""
        from src.models.adapter_base import FieldMapper
        m = FieldMapper({"policy_no": "policy_number"})
        assert m.get({}, "policy_number", "N/A") == "N/A"

    def test_direct_key_fallback(self):
        """Direct key access when no mapping defined."""
        from src.models.adapter_base import FieldMapper
        m = FieldMapper({})
        assert m.get({"policy_number": "GE-123"}, "policy_number") == "GE-123"

    def test_get_date_iso(self):
        """ISO date string parsed."""
        from src.models.adapter_base import FieldMapper
        m = FieldMapper({"from": "inception_date"})
        d = m.get_date({"from": "2024-01-01"}, "inception_date")
        assert d == date(2024, 1, 1)

    def test_get_date_dd_mm_yyyy(self):
        """dd/mm/yyyy date string parsed."""
        from src.models.adapter_base import FieldMapper
        m = FieldMapper({"start": "inception_date"})
        d = m.get_date({"start": "01/01/2024"}, "inception_date")
        assert d == date(2024, 1, 1)

    def test_get_date_empty(self):
        """Empty date returns None."""
        from src.models.adapter_base import FieldMapper
        m = FieldMapper({})
        assert m.get_date({}, "inception_date") is None
        assert m.get_date({"inception_date": ""}, "inception_date") is None

    def test_get_float(self):
        """String float converted."""
        from src.models.adapter_base import FieldMapper
        m = FieldMapper({"premium": "premium"})
        assert m.get_float({"premium": "1200.50"}, "premium") == 1200.50

    def test_get_float_missing(self):
        """Missing float returns default."""
        from src.models.adapter_base import FieldMapper
        m = FieldMapper({})
        assert m.get_float({}, "premium") == 0.0


# ══════════════════════════════════════════════════════════════════
# 2. Validation (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestValidation:
    """ValidationResult and validation logic."""

    def test_validation_passes(self):
        """Empty policy with required fields passes."""
        from src.models.adapter_base import ModelAdapter
        from src.models.policy import Policy

        class TestValAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {}
            REQUIRED_POLICY_FIELDS = ["policy_number"]

        adapter = TestValAdapter()
        p = Policy(policy_number="GE-123")
        result = adapter.validate_policy(p)
        assert result.valid is True

    def test_validation_fails_missing(self):
        """Missing required field fails."""
        from src.models.adapter_base import ModelAdapter
        from src.models.policy import Policy

        class TestValAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {}
            REQUIRED_POLICY_FIELDS = ["policy_number"]

        adapter = TestValAdapter()
        p = Policy(policy_number="")
        result = adapter.validate_policy(p)
        assert result.valid is False
        assert any("policy_number" in e.field for e in result.errors)

    def test_validation_date_order(self):
        """Expiry before inception is an error."""
        from src.models.adapter_base import ModelAdapter
        from src.models.policy import Policy

        class TestValAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {}
            REQUIRED_POLICY_FIELDS = ["policy_number"]

        adapter = TestValAdapter()
        p = Policy(policy_number="GE-123", inception_date=date(2025, 1, 1), expiry_date=date(2024, 1, 1))
        result = adapter.validate_policy(p)
        assert result.valid is False

    def test_validation_result_summary_valid(self):
        """Valid result summary."""
        from src.models.adapter_base import ValidationResult
        r = ValidationResult(valid=True)
        assert "Valid" in r.summary()

    def test_validation_result_summary_errors(self):
        """Error result summary."""
        from src.models.adapter_base import ValidationResult
        r = ValidationResult(valid=False)
        r.add("policy_number", "Missing")
        s = r.summary()
        assert "ERROR" in s or "Error" in s or "error" in s or "✗" in s


# ══════════════════════════════════════════════════════════════════
# 3. Base ModelAdapter — extract_policy (10 tests)
# ══════════════════════════════════════════════════════════════════

class TestBaseModelAdapter:
    """Base ModelAdapter generic behavior."""

    def test_base_extract_policy(self):
        """Base extract_policy with FIELD_MAP."""
        from src.models.adapter_base import ModelAdapter
        class TestAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {"policy_no": "policy_number"}
        adapter = TestAdapter()
        p = adapter.extract_policy({"policy_no": "T-001"})
        assert p.policy_number == "T-001"
        assert p.insurer == "Test"
        assert p.source == "portal"

    def test_base_extract_policy_full(self):
        """Full data mapped correctly."""
        from src.models.adapter_base import ModelAdapter
        class TestAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {
                "policy_no": "policy_number",
                "name": "insured_name",
                "ic": "insured_ic",
                "start": "inception_date",
                "end": "expiry_date",
                "prem": "premium",
            }
        adapter = TestAdapter()
        data = {
            "policy_no": "T-001",
            "name": "John Tan",
            "ic": "800101-01-1234",
            "start": "2024-01-01",
            "end": "2025-01-01",
            "prem": "1500.00",
        }
        p = adapter.extract_policy(data)
        assert p.policy_number == "T-001"
        assert p.insured.name == "John Tan"
        assert p.insured.ic_number == "800101-01-1234"
        assert p.inception_date == date(2024, 1, 1)
        assert p.expiry_date == date(2025, 1, 1)
        assert p.premium.total == 1500.0

    def test_base_extract_policy_minimal(self):
        """Minimal data doesn't crash."""
        from src.models.adapter_base import ModelAdapter
        class TestAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {}
        adapter = TestAdapter()
        p = adapter.extract_policy({"policy_number": "T-001"})
        assert p.policy_number == "T-001"

    def test_base_extract_claim(self):
        """Base extract_claim works."""
        from src.models.adapter_base import ModelAdapter
        class TestAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {}
        adapter = TestAdapter()
        c = adapter.extract_claim({"claim_id": "CL-001", "policy_number": "T-001"})
        assert c.claim_id == "CL-001"
        assert c.policy_number == "T-001"

    def test_base_extract_claim_with_incident(self):
        """Claim with incident data."""
        from src.models.adapter_base import ModelAdapter
        class TestAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {}
        adapter = TestAdapter()
        c = adapter.extract_claim({
            "claim_id": "CL-002",
            "policy_number": "T-001",
            "claim_amount": "50000",
            "incident": {"type": "fire", "description": "Kitchen fire", "date": "2024-06-15"},
        })
        assert c.claim_amount == 50000.0
        assert c.incident.type == "fire"
        assert c.incident.date == date(2024, 6, 15)

    def test_base_extract_customer(self):
        """Base extract_customer works."""
        from src.models.adapter_base import ModelAdapter
        class TestAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {}
        adapter = TestAdapter()
        c = adapter.extract_customer({
            "customer_id": "C-001",
            "customer_name": "John Tan",
            "policies": ["T-001", "T-002"],
        })
        assert c.customer_id == "C-001"
        assert c.identity.full_name == "John Tan"
        assert len(c.policy_numbers) == 2

    def test_base_status_parsing(self):
        """Status parsing from adapter."""
        from src.models.adapter_base import ModelAdapter
        class TestAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {"pol_status": "status"}
        adapter = TestAdapter()
        p = adapter.extract_policy({"policy_number": "T-001", "pol_status": "active"})
        from src.models.policy import PolicyStatus
        assert p.status == PolicyStatus.ACTIVE

    def test_base_extract_policy_no_premium(self):
        """Zero premium doesn't create Premium object."""
        from src.models.adapter_base import ModelAdapter
        class TestAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {}
        adapter = TestAdapter()
        p = adapter.extract_policy({"policy_number": "T-001", "premium": "0"})
        assert p.premium is None

    def test_stats_tracking(self):
        """Adapter tracks extraction stats."""
        from src.models.adapter_base import ModelAdapter
        class TestAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {}
        adapter = TestAdapter()
        assert adapter.stats["extracted"] == 0
        adapter.extract_policy({"policy_number": "T-001"})
        assert adapter.stats["extracted"] == 1
        adapter.extract_claim({"claim_id": "CL-001", "policy_number": "T-001"})
        assert adapter.stats["extracted"] == 2

    def test_reset_stats(self):
        """Stats can be reset."""
        from src.models.adapter_base import ModelAdapter
        class TestAdapter(ModelAdapter):
            PORTAL_NAME = "Test"
            FIELD_MAP = {}
        adapter = TestAdapter()
        adapter.extract_policy({"policy_number": "T-001"})
        assert adapter.stats["extracted"] == 1
        adapter.reset_stats()
        assert adapter.stats["extracted"] == 0


# ══════════════════════════════════════════════════════════════════
# 4. Great Eastern Adapter (12 tests)
# ══════════════════════════════════════════════════════════════════

class TestGreatEasternAdapter:
    """Great Eastern portal model adapter."""

    def test_ge_policy_basic(self):
        """GE basic policy extraction."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({"policy_number": "GE-12345"})
        assert p.policy_number == "GE-12345"
        assert p.insurer == "Great Eastern"
        assert adapter.name == "Great Eastern"

    def test_ge_policy_with_policy_no(self):
        """GE uses policy_no as alternate key."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({"policy_no": "GE-999"})
        assert p.policy_number == "GE-999"

    def test_ge_policy_with_cover_note(self):
        """GE cover note format."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({"cover_note_no": "CN-001"})
        assert p.policy_number == "CN-001"

    def test_ge_policy_with_insured(self):
        """GE policy with insured info."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({
            "policy_number": "GE-123",
            "insured_name": "Tiong Hoe Hung",
            "nric": "800101-01-1234",
        })
        assert p.insured.name == "Tiong Hoe Hung"
        assert p.insured.ic_number == "800101-01-1234"

    def test_ge_policy_with_dates_and_premium(self):
        """GE policy with dates and premium."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({
            "policy_number": "GE-123",
            "inception_date": "2024-01-01",
            "expiry_date": "2025-01-01",
            "premium": "1200.50",
        })
        assert p.inception_date == date(2024, 1, 1)
        assert p.expiry_date == date(2025, 1, 1)
        assert p.premium.total == 1200.50

    def test_ge_policy_status_active(self):
        """Status 'active' maps to ACTIVE."""
        from src.models.adapter_ge import GreatEasternAdapter
        from src.models.policy import PolicyStatus
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({"policy_number": "GE-123", "status": "active"})
        assert p.status == PolicyStatus.ACTIVE

    def test_ge_policy_status_in_force(self):
        """Status 'in force' maps to ACTIVE."""
        from src.models.adapter_ge import GreatEasternAdapter
        from src.models.policy import PolicyStatus
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({"policy_number": "GE-123", "policy_status": "In Force"})
        assert p.status == PolicyStatus.ACTIVE

    def test_ge_policy_status_lapsed(self):
        """Status 'lapsed' maps to LAPSED."""
        from src.models.adapter_ge import GreatEasternAdapter
        from src.models.policy import PolicyStatus
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({"policy_number": "GE-123", "status": "lapsed"})
        assert p.status == PolicyStatus.LAPSED

    def test_ge_validation_passes(self):
        """GE policy with required fields passes validation."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({"policy_number": "GE-123"})
        result = adapter.validate_policy(p)
        assert result.valid is True

    def test_ge_validation_fails(self):
        """GE policy without policy_number fails validation."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({})
        result = adapter.validate_policy(p)
        assert result.valid is False

    def test_ge_customer_name_as_insured(self):
        """GE uses customer_name as fallback."""
        from src.models.adapter_ge import GreatEasternAdapter
        adapter = GreatEasternAdapter()
        p = adapter.extract_policy({
            "policy_number": "GE-123",
            "customer_name": "Alice",
        })
        assert p.insured.name == "Alice"


class TestGreatEasternPDFAdapter:
    """Great Eastern PDF extraction adapter."""

    def test_ge_pdf_basic(self):
        """GE PDF extraction creates Policy."""
        from src.models.adapter_ge import GreatEasternPDFAdapter
        adapter = GreatEasternPDFAdapter()
        p = adapter.extract_policy({
            "policy_number": "GE-777",
            "insurer": "Great Eastern",
        })
        assert p.policy_number == "GE-777"
        assert p.insurer == "Great Eastern"
        assert p.source == "pdf"

    def test_ge_pdf_with_insured_dict(self):
        """PDF extraction: insured is a nested dict."""
        from src.models.adapter_ge import GreatEasternPDFAdapter
        adapter = GreatEasternPDFAdapter()
        p = adapter.extract_policy({
            "policy_number": "GE-888",
            "insured": {"name": "John Tan", "ic_number": "800101-01-1234"},
        })
        assert p.insured.name == "John Tan"
        assert p.insured.ic_number == "800101-01-1234"

    def test_ge_pdf_with_sections(self):
        """PDF extraction preserves sections in raw_text."""
        from src.models.adapter_ge import GreatEasternPDFAdapter
        adapter = GreatEasternPDFAdapter()
        p = adapter.extract_policy({
            "policy_number": "GE-999",
            "premium": "1500",
            "inception_date": "2024-06-01",
            "expiry_date": "2025-06-01",
            "raw_text": "Policy schedule...",
        })
        assert p.premium.total == 1500.0
        assert p.inception_date == date(2024, 6, 1)
        assert p.raw_text == "Policy schedule..."


# ══════════════════════════════════════════════════════════════════
# 5. Allianz Adapter (7 tests)
# ══════════════════════════════════════════════════════════════════

class TestAllianzAdapter:
    """Allianz portal model adapter."""

    def test_allianz_basic(self):
        """Allianz basic extraction."""
        from src.models.adapter_allianz import AllianzAdapter
        adapter = AllianzAdapter()
        p = adapter.extract_policy({"policy_number": "AL-12345"})
        assert p.policy_number == "AL-12345"
        assert p.insurer == "Allianz Malaysia"

    def test_allianz_certificate_no(self):
        """Allianz uses certificate_no as primary key."""
        from src.models.adapter_allianz import AllianzAdapter
        adapter = AllianzAdapter()
        p = adapter.extract_policy({"certificate_no": "AL-999"})
        assert p.policy_number == "AL-999"

    def test_allianz_certificate_number(self):
        """Allianz certificate_number alternate."""
        from src.models.adapter_allianz import AllianzAdapter
        adapter = AllianzAdapter()
        p = adapter.extract_policy({"certificate_number": "AL-888"})
        assert p.policy_number == "AL-888"

    def test_allianz_with_insured(self):
        """Allianz with insured info."""
        from src.models.adapter_allianz import AllianzAdapter
        adapter = AllianzAdapter()
        p = adapter.extract_policy({
            "certificate_no": "AL-123",
            "insured_name": "Bob",
            "id_number": "900101-01-5678",
        })
        assert p.insured.name == "Bob"
        assert p.insured.ic_number == "900101-01-5678"

    def test_allianz_product_mapping_fire(self):
        """Allianz product name maps to Fire."""
        from src.models.adapter_allianz import AllianzAdapter
        from src.models.policy import ProductType
        adapter = AllianzAdapter()
        p = adapter.extract_policy({"certificate_no": "AL-123", "product": "Fire Insurance"})
        assert p.product_type == ProductType.FIRE

    def test_allianz_product_mapping_motor(self):
        """Allianz motor product."""
        from src.models.adapter_allianz import AllianzAdapter
        from src.models.policy import ProductType
        adapter = AllianzAdapter()
        p = adapter.extract_policy({"certificate_no": "AL-123", "product_type": "Motor"})
        assert p.product_type == ProductType.MOTOR

    def test_allianz_multiple_date_formats(self):
        """Allianz date formats."""
        from src.models.adapter_allianz import AllianzAdapter
        adapter = AllianzAdapter()
        p = adapter.extract_policy({
            "certificate_no": "AL-123",
            "valid_from": "2024-01-01",
            "valid_until": "2025-01-01",
        })
        assert p.inception_date == date(2024, 1, 1)
        assert p.expiry_date == date(2025, 1, 1)


# ══════════════════════════════════════════════════════════════════
# 6. AIA Adapter (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestAIAAdapter:
    """AIA portal model adapter."""

    def test_aia_basic(self):
        """AIA basic extraction."""
        from src.models.adapter_aia import AIAAdapter
        adapter = AIAAdapter()
        p = adapter.extract_policy({"policy_number": "AIA-12345"})
        assert p.policy_number == "AIA-12345"
        assert p.insurer == "AIA Malaysia"

    def test_aia_policy_id(self):
        """AIA uses policy_id as alternate key."""
        from src.models.adapter_aia import AIAAdapter
        adapter = AIAAdapter()
        p = adapter.extract_policy({"policy_id": "AIA-999"})
        assert p.policy_number == "AIA-999"

    def test_aia_life_assured(self):
        """AIA life_assured maps to insured."""
        from src.models.adapter_aia import AIAAdapter
        adapter = AIAAdapter()
        p = adapter.extract_policy({
            "policy_number": "AIA-123",
            "life_assured": "Charlie",
        })
        assert p.insured.name == "Charlie"

    def test_aia_owner_ic(self):
        """AIA owner_ic maps to insured_ic."""
        from src.models.adapter_aia import AIAAdapter
        adapter = AIAAdapter()
        p = adapter.extract_policy({
            "policy_number": "AIA-123",
            "owner_ic": "700101-01-1111",
        })
        assert p.insured.ic_number == "700101-01-1111"

    def test_aia_plan_name(self):
        """AIA plan name maps to product_type but stays as string."""
        from src.models.adapter_aia import AIAAdapter
        adapter = AIAAdapter()
        p = adapter.extract_policy({
            "policy_number": "AIA-123",
            "plan_name": "Supreme Health",
        })
        # Product type stays as enum UNKNOWN since plan_name isn't in ProductType enum
        from src.models.policy import ProductType
        assert p.product_type == ProductType.UNKNOWN

    def test_aia_dates(self):
        """AIA date formats."""
        from src.models.adapter_aia import AIAAdapter
        adapter = AIAAdapter()
        p = adapter.extract_policy({
            "policy_number": "AIA-123",
            "commencement_date": "2024-03-01",
            "maturity_date": "2034-03-01",
        })
        assert p.inception_date == date(2024, 3, 1)
        assert p.expiry_date == date(2034, 3, 1)


# ══════════════════════════════════════════════════════════════════
# 7. Registry (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestModelAdapterRegistry:
    """ModelAdapter registry."""

    def test_get_ge_adapter(self):
        """Get Great Eastern adapter by name."""
        from src.models.adapter_registry import get_model_adapter
        adapter = get_model_adapter("great_eastern")
        assert adapter is not None
        assert adapter.name == "Great Eastern"

    def test_get_allianz_adapter(self):
        """Get Allianz adapter."""
        from src.models.adapter_registry import get_model_adapter
        adapter = get_model_adapter("allianz")
        assert adapter is not None
        assert "Allianz" in adapter.name

    def test_get_aia_adapter(self):
        """Get AIA adapter."""
        from src.models.adapter_registry import get_model_adapter
        adapter = get_model_adapter("aia")
        assert adapter is not None
        assert "AIA" in adapter.name

    def test_get_unknown_adapter(self):
        """Unknown adapter returns None."""
        from src.models.adapter_registry import get_model_adapter
        adapter = get_model_adapter("nonexistent")
        assert adapter is None

    def test_get_pdf_adapter(self):
        """Get PDF adapter."""
        from src.models.adapter_registry import get_model_adapter
        adapter = get_model_adapter("great_eastern", source="pdf")
        assert adapter is not None
        assert "PDF" in adapter.name

    def test_list_adapters(self):
        """List all adapters returns unique entries."""
        from src.models.adapter_registry import list_model_adapters
        adapters = list_model_adapters()
        assert len(adapters) >= 4  # GE, Allianz, AIA, GE PDF
        names = [a["name"] for a in adapters]
        assert "Great Eastern" in names
        assert "Allianz Malaysia" in names
