"""Tests: Runtime Integration Layer (Phase 5).

Covers:
- Error Types (8 tests)
- Capabilities (5 tests)
- Adapter Registry — dynamic registration (12 tests)
- Adapter Selector — auto-detection + scoring (12 tests)
- Runtime Executor — E2E extraction workflow (18 tests)
- Batch Operations (5 tests)
- Cross-insurer switching (5 tests)
Target: ~65 new tests (411 → 475+)
"""

from __future__ import annotations

import os
import sys
import pytest
from datetime import date
from typing import Dict, Any, List, Set

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. Error Types (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestRuntimeErrors:
    """Normalized error types."""

    def test_extraction_error_basic(self):
        """ExtractionError with code and message."""
        from src.runtime.errors import ExtractionError
        e = ExtractionError("test_code", "Something went wrong")
        assert e.code == "test_code"
        assert "Something" in str(e)

    def test_extraction_error_context(self):
        """ExtractionError with context dict."""
        from src.runtime.errors import ExtractionError
        e = ExtractionError("ctx_test", "With context", {"key": "value"})
        assert e.context["key"] == "value"

    def test_extraction_error_to_dict(self):
        """to_dict() returns structured dict."""
        from src.runtime.errors import ExtractionError
        e = ExtractionError("code", "msg", {"k": "v"})
        d = e.to_dict()
        assert d["code"] == "code"
        assert d["context"]["k"] == "v"

    def test_adapter_not_found(self):
        """AdapterNotFoundError with available list."""
        from src.runtime.errors import AdapterNotFoundError
        e = AdapterNotFoundError(portal_hint="unknown",
                                 available=[{"name": "test"}])
        assert "adapter" in str(e).lower()
        assert "unknown" in str(e)
        assert e.context["portal_hint"] == "unknown"
        assert len(e.context["available_adapters"]) == 1

    def test_validation_failed(self):
        """ValidationFailedError with error list."""
        from src.runtime.errors import ValidationFailedError
        import types
        err = types.SimpleNamespace(field="policy_number", severity="error")
        e = ValidationFailedError("policy", [err])
        assert "validation" in str(e).lower()

    def test_missing_data_error(self):
        """MissingDataError for sparse data."""
        from src.runtime.errors import MissingDataError
        e = MissingDataError(["name", "age"])
        assert "sparse" in str(e).lower() or "top-level" in str(e).lower()

    def test_adapter_execution_error(self):
        """AdapterExecutionError wraps adapter failures."""
        from src.runtime.errors import AdapterExecutionError
        e = AdapterExecutionError("TestAdapter", "division by zero")
        assert "TestAdapter" in str(e)
        assert e.context["original_error"] == "division by zero"

    def test_capability_not_supported(self):
        """CapabilityNotSupportedError."""
        from src.runtime.errors import CapabilityNotSupportedError
        e = CapabilityNotSupportedError("GE", "submit_claim")
        assert "submit_claim" in str(e)


# ══════════════════════════════════════════════════════════════════
# 2. Capabilities (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestCapabilities:
    """Adapter capability declarations."""

    def test_capability_enum_values(self):
        """Capability enum has expected values."""
        from src.runtime.capabilities import AdapterCapability
        assert AdapterCapability.FETCH_POLICY.value == "fetch_policy"
        assert AdapterCapability.SUBMIT_CLAIM.value == "submit_claim"

    def test_get_ge_capabilities(self):
        """Great Eastern has core + search + login."""
        from src.runtime.capabilities import get_adapter_capabilities
        caps = get_adapter_capabilities("great_eastern")
        cap_names = {c.value for c in caps}
        assert "fetch_policy" in cap_names
        assert "search_policies" in cap_names
        assert "login" in cap_names

    def test_get_pdf_capabilities(self):
        """PDF adapter has only fetch_policy."""
        from src.runtime.capabilities import get_adapter_capabilities
        caps = get_adapter_capabilities("great_eastern_pdf")
        cap_names = {c.value for c in caps}
        assert "fetch_policy" in cap_names
        assert "login" not in cap_names

    def test_supports_capability(self):
        """supports_capability checks correctly."""
        from src.runtime.capabilities import supports_capability, AdapterCapability
        assert supports_capability("great_eastern", AdapterCapability.FETCH_POLICY)
        assert not supports_capability("great_eastern_pdf", AdapterCapability.LOGIN)

    def test_register_capabilities(self):
        """Runtime registration of new capabilities."""
        from src.runtime.capabilities import (
            register_adapter_capabilities,
            get_adapter_capabilities,
            AdapterCapability,
        )
        register_adapter_capabilities("custom_test", {AdapterCapability.FETCH_POLICY})
        caps = get_adapter_capabilities("custom_test")
        assert len(caps) == 1
        assert AdapterCapability.FETCH_POLICY in caps


# ══════════════════════════════════════════════════════════════════
# 3. Adapter Registry — Dynamic Registration (12 tests)
# ══════════════════════════════════════════════════════════════════

class TestAdapterRegistry:
    """Dynamic AdapterRegistry."""

    def test_registry_get_builtin(self):
        """Get Great Eastern adapter by canonical key."""
        from src.runtime.registry import AdapterRegistry
        reg = AdapterRegistry()
        ge = reg.get("great_eastern")
        assert ge is not None
        assert ge.name == "Great Eastern"

    def test_registry_get_by_alias(self):
        """Get by alias 'ge' resolves to Great Eastern."""
        from src.runtime.registry import AdapterRegistry
        reg = AdapterRegistry()
        ge = reg.get("ge")
        assert ge is not None
        assert ge.name == "Great Eastern"

    def test_registry_get_allianz(self):
        """Get Allianz adapter."""
        from src.runtime.registry import AdapterRegistry
        reg = AdapterRegistry()
        al = reg.get("allianz")
        assert al is not None
        assert "Allianz" in al.name

    def test_registry_get_aia(self):
        """Get AIA adapter."""
        from src.runtime.registry import AdapterRegistry
        reg = AdapterRegistry()
        aia = reg.get("aia")
        assert aia is not None
        assert "AIA" in aia.name

    def test_registry_get_unknown(self):
        """Unknown key returns None."""
        from src.runtime.registry import AdapterRegistry
        reg = AdapterRegistry()
        assert reg.get("nonexistent_portal") is None

    def test_registry_list(self):
        """List adapters returns metadata."""
        from src.runtime.registry import AdapterRegistry
        reg = AdapterRegistry()
        adapters = reg.list()
        names = [a["name"] for a in adapters]
        assert "Great Eastern" in names
        assert "Allianz Malaysia" in names
        assert "AIA Malaysia" in names

    def test_registry_register_new(self):
        """Register a custom adapter at runtime."""
        from src.runtime.registry import AdapterRegistry
        from src.models.adapter_base import ModelAdapter

        class TestCustomAdapter(ModelAdapter):
            PORTAL_NAME = "Custom Portal"
            FIELD_MAP = {"custom_id": "policy_number"}

        reg = AdapterRegistry()
        inst = reg.register("custom", TestCustomAdapter)
        assert inst is not None
        assert inst.name == "Custom Portal"

        # Verify it's in the list
        names = [a["name"] for a in reg.list()]
        assert "Custom Portal" in names

    def test_registry_unregister(self):
        """Unregister removes adapter."""
        from src.runtime.registry import AdapterRegistry
        from src.models.adapter_base import ModelAdapter

        class TempAdapter(ModelAdapter):
            PORTAL_NAME = "Temp"
            FIELD_MAP = {}

        reg = AdapterRegistry()
        reg.register("temp", TempAdapter)
        assert reg.has_adapter("temp")
        reg.unregister("temp")
        assert not reg.has_adapter("temp")

    def test_registry_has_adapter(self):
        """has_adapter returns correct boolean."""
        from src.runtime.registry import AdapterRegistry
        reg = AdapterRegistry()
        assert reg.has_adapter("great_eastern")
        assert not reg.has_adapter("fake_portal")

    def test_registry_find_by_capability(self):
        """Find adapters by capability."""
        from src.runtime.registry import AdapterRegistry
        from src.runtime.capabilities import AdapterCapability
        reg = AdapterRegistry()
        claim_adapters = reg.find_by_capability(AdapterCapability.SUBMIT_CLAIM)
        # Currently no adapters declare submit_claim
        assert len(claim_adapters) == 0

        search_adapters = reg.find_by_capability(AdapterCapability.FETCH_POLICY)
        assert len(search_adapters) >= 3  # GE, Allianz, AIA

    def test_registry_stats(self):
        """Stats returns aggregate information."""
        from src.runtime.registry import AdapterRegistry
        reg = AdapterRegistry()
        ge = reg.get("great_eastern")
        ge.extract_policy({"policy_number": "TEST-001"})

        s = reg.stats()
        assert s["total"]["extracted"] >= 1
        assert s["adapter_count"] >= 3


# ══════════════════════════════════════════════════════════════════
# 4. Adapter Selector — Auto-detection (12 tests)
# ══════════════════════════════════════════════════════════════════

class TestAdapterSelector:
    """Auto-detect portal type from raw data."""

    def test_detect_ge_by_fields(self):
        """GE data has policy_no + insured_name → detected as GE."""
        from src.runtime.selector import detect_portal_from_data
        data = {"policy_no": "GE-123", "insured_name": "John", "premium": "1200"}
        detected = detect_portal_from_data(data)
        assert detected == "great_eastern"

    def test_detect_allianz_by_certificate(self):
        """Allianz data has certificate_no → detected as Allianz."""
        from src.runtime.selector import detect_portal_from_data
        data = {"certificate_no": "AL-999", "insured_name": "Bob"}
        detected = detect_portal_from_data(data)
        assert detected == "allianz"

    def test_detect_aia_by_life_assured(self):
        """AIA data has life_assured → detected as AIA."""
        from src.runtime.selector import detect_portal_from_data
        data = {"policy_id": "AIA-001", "life_assured": "Charlie"}
        detected = detect_portal_from_data(data)
        assert detected == "aia"

    def test_detect_empty_data(self):
        """Empty data returns None."""
        from src.runtime.selector import detect_portal_from_data
        assert detect_portal_from_data({}) is None
        assert detect_portal_from_data(None) is None

    def test_select_by_hint(self):
        """Portal hint overrides auto-detection."""
        from src.runtime.registry import AdapterRegistry
        from src.runtime.selector import select_adapter
        reg = AdapterRegistry()
        data = {"certificate_no": "AL-999"}  # Looks like Allianz
        detection = select_adapter(data, portal_hint="aia", registry=reg)
        assert detection.adapter == "aia"
        adapter = detection.get_adapter(reg)
        assert adapter is not None
        assert adapter.name == "AIA Malaysia"  # Override works

    def test_select_ge_policy_data(self):
        """GE policy data selects GE adapter."""
        from src.runtime.registry import AdapterRegistry
        from src.runtime.selector import select_adapter
        reg = AdapterRegistry()
        data = {"policy_no": "GE-123", "insured_name": "Tiong"}
        detection = select_adapter(data, registry=reg)
        assert detection.adapter is not None
        assert "great_eastern" in detection.adapter

    def test_select_allianz_data(self):
        """Allianz data selects Allianz adapter."""
        from src.runtime.registry import AdapterRegistry
        from src.runtime.selector import select_adapter
        reg = AdapterRegistry()
        data = {"certificate_no": "AL-001", "total_premium": "1500"}
        detection = select_adapter(data, registry=reg)
        assert detection.adapter is not None
        assert "allianz" in detection.adapter

    def test_select_aia_data(self):
        """AIA data selects AIA adapter."""
        from src.runtime.registry import AdapterRegistry
        from src.runtime.selector import select_adapter
        reg = AdapterRegistry()
        data = {"policy_id": "AIA-001", "life_assured": "Charlie", "basic_premium": "2000"}
        detection = select_adapter(data, registry=reg)
        assert detection.adapter is not None
        assert "aia" in detection.adapter

    def test_select_sparse_data_raises(self):
        """Very sparse data raises MissingDataError."""
        from src.runtime.registry import AdapterRegistry
        from src.runtime.selector import select_adapter
        from src.runtime.errors import MissingDataError
        reg = AdapterRegistry()
        with pytest.raises(MissingDataError):
            select_adapter({"name": "John"}, registry=reg)

    def test_select_empty_data_raises(self):
        """Empty data raises MissingDataError."""
        from src.runtime.registry import AdapterRegistry
        from src.runtime.selector import select_adapter
        from src.runtime.errors import MissingDataError
        reg = AdapterRegistry()
        with pytest.raises(MissingDataError):
            select_adapter({}, registry=reg)

    def test_score_adapter_matches(self):
        """Score adapter function returns positive for matching keys."""
        from src.runtime.selector import score_adapter
        from src.models.adapter_ge import GreatEasternAdapter
        score, matched, has_sig = score_adapter(GreatEasternAdapter,
                              {"policy_no", "insured_name", "premium"})
        assert score > 0
        assert len(matched) > 0

    def test_score_adapter_no_match(self):
        """Score adapter returns 0 for irrelevant keys."""
        from src.runtime.selector import score_adapter
        from src.models.adapter_ge import GreatEasternAdapter
        score, matched, has_sig = score_adapter(GreatEasternAdapter,
                              {"temperature", "humidity", "pressure"})
        assert score == 0
        assert len(matched) == 0


# ══════════════════════════════════════════════════════════════════
# 5. Runtime Executor — E2E Workflow (18 tests)
# ══════════════════════════════════════════════════════════════════

class TestRuntimeExecutor:
    """RuntimeExecutor: end-to-end extraction workflow."""

    def test_executor_extract_ge_policy(self):
        """Extract GE policy from raw data."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy({
            "policy_number": "GE-12345",
            "insured_name": "Tiong Hoe Hung",
            "premium": "1250.00",
        })
        assert result.success
        assert result.model.policy_number == "GE-12345"
        assert result.model.insured.name == "Tiong Hoe Hung"
        assert "Great Eastern" in result.adapter_name

    def test_executor_extract_allianz_policy(self):
        """Extract Allianz policy from raw data (auto-detect)."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy({
            "certificate_no": "AL-999",
            "insured_name": "Bob",
            "total_premium": "1500.00",
            "valid_from": "2024-01-01",
            "valid_until": "2025-01-01",
        })
        assert result.success
        assert result.model.policy_number == "AL-999"
        assert "Allianz" in result.adapter_name

    def test_executor_extract_aia_policy_with_hint(self):
        """Extract AIA policy with explicit portal hint."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy({
            "policy_id": "AIA-001",
            "life_assured": "Charlie",
            "basic_premium": "2000",
        }, portal_hint="aia")
        assert result.success
        assert result.model.policy_number == "AIA-001"
        assert result.model.insured.name == "Charlie"

    def test_executor_extract_claim(self):
        """Extract claim from raw data."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_claim({
            "claim_id": "CL-001",
            "policy_number": "GE-123",
            "claim_amount": "50000",
            "incident": {"type": "fire", "date": "2024-06-15"},
        }, portal_hint="great_eastern")
        assert result.success
        assert result.model.claim_id == "CL-001"
        assert result.model.claim_amount == 50000.0

    def test_executor_extract_customer(self):
        """Extract customer from raw data."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_customer({
            "customer_id": "C-001",
            "customer_name": "John Tan",
            "policies": ["GE-123", "GE-456"],
        }, portal_hint="great_eastern")
        assert result.success
        assert result.model.customer_id == "C-001"
        assert result.model.identity.full_name == "John Tan"

    def test_executor_validation_passes(self):
        """Validation passes for complete data."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy({
            "policy_number": "GE-VALID",
        })
        assert result.success

    def test_executor_validation_fails(self):
        """Validation returns failure for missing required fields."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy({
            "something": "else",
        }, portal_hint="great_eastern")
        # Should fail validation because policy_number is missing
        assert not result.success
        assert "validation" in result.error.lower() or "missing" in result.error.lower()

    def test_executor_unknown_portal_hint(self):
        """Unknown portal hint falls through to auto-detection which fails for sparse data."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        # Use sparse data that no adapter can recognize, with an invalid hint
        result = executor.extract_policy({
            "unrecognizable_key": "foo",
        }, portal_hint="nonexistent_portal")
        assert not result.success

    def test_executor_empty_data(self):
        """Empty data returns MissingDataError."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy({})
        assert not result.success
        assert "missing" in result.error.lower()

    def test_executor_ge_full_integration(self):
        """Full GE integration: extract → validate → round-trip."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        data = {
            "policy_number": "F0377733",
            "insured_name": "Tiong Hoe Hung",
            "nric": "720415-01-1234",
            "inception_date": "2024-01-01",
            "expiry_date": "2025-01-01",
            "premium": "1250.00",
            "status": "active",
        }
        result = executor.extract_policy(data)
        assert result.success
        p = result.model
        assert p.policy_number == "F0377733"
        assert p.insured.name == "Tiong Hoe Hung"
        assert p.insured.ic_number == "720415-01-1234"
        assert p.premium.total == 1250.0
        assert p.inception_date == date(2024, 1, 1)
        assert p.expiry_date == date(2025, 1, 1)
        from src.models.policy import PolicyStatus
        assert p.status == PolicyStatus.ACTIVE

        # Round-trip via to_dict/from_dict
        d = p.to_dict()
        from src.models.policy import Policy
        restored = Policy.from_dict(d)
        assert restored.policy_number == "F0377733"
        assert restored.insured.name == "Tiong Hoe Hung"

    def test_executor_allianz_full_integration(self):
        """Full Allianz integration: auto-detect → extract → validate."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        data = {
            "certificate_no": "AL-2024-001",
            "insured_name": "Tan Mei Ling",
            "id_number": "850101-01-5678",
            "product": "Fire Insurance",
            "total_premium": "1800.50",
            "valid_from": "2024-03-01",
            "valid_until": "2025-03-01",
            "status": "active",
        }
        result = executor.extract_policy(data)
        assert result.success
        p = result.model
        assert p.policy_number == "AL-2024-001"
        assert p.insured.name == "Tan Mei Ling"
        assert p.premium.total == 1800.50
        from src.models.policy import ProductType
        assert p.product_type == ProductType.FIRE

    def test_executor_aia_full_integration(self):
        """Full AIA integration: auto-detect → extract → validate."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        data = {
            "policy_id": "AIA-LIFE-2024-001",
            "life_assured": "Kumar Raju",
            "owner_ic": "750101-01-9999",
            "plan_name": "AIA Secure Life",
            "basic_premium": "2400.00",
            "commencement_date": "2024-06-01",
            "maturity_date": "2054-06-01",
            "status": "active",
        }
        result = executor.extract_policy(data)
        assert result.success
        p = result.model
        assert p.policy_number == "AIA-LIFE-2024-001"
        assert p.insured.name == "Kumar Raju"
        assert p.insured.ic_number == "750101-01-9999"
        assert p.premium.total == 2400.0
        assert p.inception_date == date(2024, 6, 1)

    def test_executor_result_metadata(self):
        """ExtractResult contains adapter metadata."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy({
            "policy_no": "GE-777",
        })
        assert result.success
        assert result.adapter_name == "Great Eastern"
        assert result.adapter_key  # Non-empty
        assert result.raw_data["policy_no"] == "GE-777"

    def test_executor_skip_validation(self):
        """validate=False skips validation even for incomplete data."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy({
            "name": "John",
        }, portal_hint="great_eastern", validate=False)
        # Without validation, extraction still produces a model
        assert result.success  # Extraction succeeded even if model is sparse
        assert result.model is not None

    def test_executor_supports_check(self):
        """supports() checks adapter capabilities."""
        from src.runtime import RuntimeExecutor
        from src.runtime.capabilities import AdapterCapability
        executor = RuntimeExecutor()
        assert executor.supports("great_eastern", AdapterCapability.FETCH_POLICY)
        assert not executor.supports("great_eastern_pdf", AdapterCapability.LOGIN)

    def test_executor_find_by_capability(self):
        """find_by_capability returns matching adapters."""
        from src.runtime import RuntimeExecutor
        from src.runtime.capabilities import AdapterCapability
        executor = RuntimeExecutor()
        results = executor.find_by_capability(AdapterCapability.FETCH_POLICY)
        assert len(results) >= 3

    def test_executor_stats(self):
        """Stats returns aggregate counts."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        executor.extract_policy({"policy_number": "GE-STATS-1"})
        executor.extract_claim({"claim_id": "CL-STATS-1", "policy_number": "GE-STATS-1"})
        s = executor.stats()
        assert s["total"]["extracted"] >= 2

    def test_executor_before_hook(self):
        """before_extract hook is called."""
        from src.runtime import RuntimeExecutor
        called = []

        def hook(raw_data, method, hint):
            called.append((method, hint))

        executor = RuntimeExecutor()
        executor.before_extract(hook)
        executor.extract_policy({"policy_number": "GE-HOOK"}, portal_hint="great_eastern")
        assert len(called) == 1
        assert called[0][0] == "extract_policy"

    def test_executor_after_hook(self):
        """after_extract hook is called."""
        from src.runtime import RuntimeExecutor
        called = []

        def hook(result):
            called.append(result.success)

        executor = RuntimeExecutor()
        executor.after_extract(hook)
        executor.extract_policy({"policy_number": "GE-HOOK2"}, portal_hint="great_eastern")
        assert len(called) == 1
        assert called[0] is True


# ══════════════════════════════════════════════════════════════════
# 6. Batch Operations (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestBatchOperations:
    """RuntimeExecutor batch extraction."""

    def test_batch_all_succeed(self):
        """Batch with all valid items succeeds entirely."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        items = [
            {"policy_number": "GE-001", "insured_name": "Alice"},
            {"policy_number": "GE-002", "insured_name": "Bob"},
            {"policy_number": "GE-003", "insured_name": "Charlie"},
        ]
        batch = executor.batch_extract(items, portal_hint="great_eastern")
        assert batch.total == 3
        assert batch.succeeded == 3
        assert batch.failed == 0

    def test_batch_with_failures(self):
        """Batch continues after individual failures."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        items = [
            {"policy_number": "GE-001"},
            {},  # Empty — will fail
            {"policy_number": "GE-003"},
        ]
        batch = executor.batch_extract(items, portal_hint="great_eastern")
        assert batch.total == 3
        assert batch.succeeded >= 2  # 1st and 3rd succeed
        assert batch.failed >= 1     # 2nd fails

    def test_batch_results_order(self):
        """Batch results preserve input order."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        items = [
            {"policy_number": "GE-001"},
            {"policy_number": "GE-002"},
        ]
        batch = executor.batch_extract(items, portal_hint="great_eastern")
        assert len(batch.results) == 2
        assert batch.results[0].model.policy_number == "GE-001"
        assert batch.results[1].model.policy_number == "GE-002"

    def test_batch_summary(self):
        """Batch summary string."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        items = [{"policy_number": "GE-001"}]
        batch = executor.batch_extract(items, portal_hint="great_eastern")
        assert "1 items" in batch.summary or "1 item" in batch.summary
        assert "succeeded" in batch.summary

    def test_batch_extract_type_claim(self):
        """Batch extract claims."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        items = [
            {"claim_id": "CL-001", "policy_number": "GE-001"},
            {"claim_id": "CL-002", "policy_number": "GE-002"},
        ]
        batch = executor.batch_extract(items, portal_hint="great_eastern",
                                       extract_type="claim")
        assert batch.total == 2
        assert batch.succeeded == 2
        assert batch.results[0].model.claim_id == "CL-001"


# ══════════════════════════════════════════════════════════════════
# 8. DetectionResult Specific Tests (10 tests)
# ══════════════════════════════════════════════════════════════════

class TestDetectionResult:
    """DetectionResult dataclass behavior."""

    def test_detection_result_defaults(self):
        """Default DetectionResult has None adapter."""
        from src.runtime.selector import DetectionResult
        dr = DetectionResult()
        assert dr.adapter is None
        assert dr.confidence == 0.0
        assert dr.detection_method == "none"

    def test_detection_result_explicit(self):
        """Explicit hint sets confidence 1.0."""
        from src.runtime.selector import DetectionResult
        dr = DetectionResult(
            adapter="great_eastern",
            confidence=1.0,
            detection_method="explicit",
            reason="User specified",
        )
        assert dr.adapter == "great_eastern"
        assert dr.confidence == 1.0
        assert dr.is_certain()

    def test_detection_result_get_adapter(self):
        """get_adapter returns adapter from registry."""
        from src.runtime.selector import DetectionResult
        from src.runtime.registry import AdapterRegistry
        reg = AdapterRegistry()
        dr = DetectionResult(adapter="great_eastern", confidence=1.0)
        ge = dr.get_adapter(reg)
        assert ge is not None
        assert ge.name == "Great Eastern"

    def test_detection_result_get_adapter_none(self):
        """get_adapter returns None when no adapter selected."""
        from src.runtime.selector import DetectionResult
        from src.runtime.registry import AdapterRegistry
        dr = DetectionResult()
        assert dr.get_adapter(AdapterRegistry()) is None

    def test_detection_result_alternatives(self):
        """DetectionResult can hold alternatives."""
        from src.runtime.selector import DetectionResult, DetectionCandidate
        dr = DetectionResult(
            adapter="allianz",
            confidence=0.96,
            alternatives=[
                DetectionCandidate(adapter="great_eastern", confidence=0.18),
                DetectionCandidate(adapter="aia", confidence=0.05),
            ],
            detection_method="field_match",
            matched_fields=["certificate_no"],
            reason="Found certificate_no",
        )
        assert len(dr.alternatives) == 2
        assert dr.alternatives[0].adapter == "great_eastern"
        assert dr.alternatives[0].confidence == 0.18

    def test_detection_result_not_certain(self):
        """Low confidence returns not certain."""
        from src.runtime.selector import DetectionResult
        dr = DetectionResult(adapter="ge", confidence=0.3)
        assert not dr.is_certain()

    def test_detection_result_certain_with_threshold(self):
        """Custom threshold for certainty check."""
        from src.runtime.selector import DetectionResult
        dr = DetectionResult(adapter="ge", confidence=0.75)
        assert dr.is_certain(threshold=0.7)
        assert not dr.is_certain(threshold=0.8)

    def test_compute_confidence_zero(self):
        """Zero score returns zero confidence."""
        from src.runtime.selector import compute_confidence
        assert compute_confidence(0, 10, False) == 0.0
        assert compute_confidence(0, 0, False) == 0.0

    def test_compute_confidence_full(self):
        """Max score with signature boost caps at 1.0."""
        from src.runtime.selector import compute_confidence
        conf = compute_confidence(10, 10, True)
        assert conf == 1.0

    def test_compute_confidence_partial(self):
        """Partial match gives intermediate confidence."""
        from src.runtime.selector import compute_confidence
        conf = compute_confidence(3, 10, False)
        assert 0.2 < conf < 0.4  # 3/10 = 0.3


# ══════════════════════════════════════════════════════════════════
# 9. Adapter Contract Tests (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestAdapterContracts:
    """Every adapter must pass these contract tests."""

    def _all_adapters(self):
        """Helper: get all registered adapter instances."""
        from src.runtime.registry import AdapterRegistry
        reg = AdapterRegistry()
        return [(entry["name"], reg.get(entry["key"])) for entry in reg.list()]

    def test_all_adapters_have_name(self):
        """Every adapter has a non-empty PORTAL_NAME."""
        for name, inst in self._all_adapters():
            assert inst.PORTAL_NAME, f"{name} missing PORTAL_NAME"
            assert inst.name, f"{name} missing name property"

    def test_all_adapters_have_version(self):
        """Every adapter declares VERSION."""
        for name, inst in self._all_adapters():
            assert inst.VERSION, f"{name} missing VERSION"
            assert isinstance(inst.VERSION, str)

    def test_all_adapters_have_field_map(self):
        """Every adapter has a FIELD_MAP dict."""
        for name, inst in self._all_adapters():
            from src.models.adapter_base import ModelAdapter
            cls = type(inst)
            if cls is not ModelAdapter and issubclass(cls, ModelAdapter):
                assert hasattr(cls, "FIELD_MAP"), f"{name} missing FIELD_MAP"

    def test_all_adapters_extract_policy(self):
        """Every adapter can extract_policy (may produce empty model)."""
        for name, inst in self._all_adapters():
            p = inst.extract_policy({})
            assert p is not None, f"{name} extract_policy returned None"

    def test_all_adapters_extract_claim(self):
        """Every adapter can extract_claim (may produce empty model)."""
        for name, inst in self._all_adapters():
            c = inst.extract_claim({})
            assert c is not None, f"{name} extract_claim returned None"

    def test_all_adapters_extract_customer(self):
        """Every adapter can extract_customer (may produce empty model)."""
        for name, inst in self._all_adapters():
            c = inst.extract_customer({})
            assert c is not None, f"{name} extract_customer returned None"

    def test_all_adapters_validate_policy(self):
        """Every adapter has validate_policy."""
        from src.models.policy import Policy
        for name, inst in self._all_adapters():
            result = inst.validate_policy(Policy(policy_number="TEST"))
            assert result is not None, f"{name} validate_policy returned None"
            assert isinstance(result.valid, bool)

    def test_all_adapters_stats(self):
        """Every adapter tracks stats."""
        for name, inst in self._all_adapters():
            s = inst.stats
            assert "extracted" in s
            assert "validated" in s
            assert "errors" in s


# ══════════════════════════════════════════════════════════════════
# 10. Cross-insurer Switching (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestCrossInsurerSwitching:
    """Same executor switches seamlessly between insurers."""

    def test_switch_ge_to_allianz(self):
        """Same executor handles GE then Allianz data."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()

        # GE
        r1 = executor.extract_policy({
            "policy_number": "GE-001", "insured_name": "Alice",
        })
        assert r1.success
        assert "Great Eastern" in r1.adapter_name

        # Allianz
        r2 = executor.extract_policy({
            "certificate_no": "AL-001", "insured_name": "Bob",
        })
        assert r2.success
        assert "Allianz" in r2.adapter_name

    def test_switch_allianz_to_aia(self):
        """Allianz → AIA seamless switch."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()

        r1 = executor.extract_policy({
            "certificate_no": "AL-001",
        })
        assert "Allianz" in r1.adapter_name

        r2 = executor.extract_policy({
            "policy_id": "AIA-001", "life_assured": "Charlie",
        })
        assert "AIA" in r2.adapter_name

    def test_three_insurer_mix(self):
        """GE → Allianz → AIA in sequence."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()

        datasets = [
            ({"policy_no": "GE-001"}, "Great Eastern"),
            ({"certificate_no": "AL-001"}, "Allianz"),
            ({"policy_id": "AIA-001", "life_assured": "Test"}, "AIA"),
        ]
        for data, expected in datasets:
            result = executor.extract_policy(data)
            assert result.success, f"Failed for {expected}"
            assert expected.lower() in result.adapter_name.lower()

    def test_cross_insurer_batch(self):
        """Batch with mixed insurer data."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        items = [
            {"policy_number": "GE-001", "insured_name": "Alice"},
            {"certificate_no": "AL-001", "insured_name": "Bob"},
            {"policy_id": "AIA-001", "life_assured": "Charlie"},
        ]
        batch = executor.batch_extract(items)
        assert batch.total == 3
        assert batch.succeeded == 3

        # Check different adapters were used
        adapter_names = {r.adapter_name for r in batch.results}
        assert len(adapter_names) >= 2  # At least 2 different insurers

    def test_cross_insurer_claim_extraction(self):
        """Extract claims across different insurers."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()

        # GE claim
        r1 = executor.extract_claim({
            "claim_id": "GE-CL-001", "policy_number": "GE-001", "claim_amount": "10000",
        }, portal_hint="great_eastern")
        assert r1.success
        assert r1.model.claim_id == "GE-CL-001"

        # AIA claim
        r2 = executor.extract_claim({
            "claim_id": "AIA-CL-001", "policy_number": "AIA-001", "claim_amount": "50000",
        }, portal_hint="aia")
        assert r2.success
        assert r2.model.claim_id == "AIA-CL-001"
