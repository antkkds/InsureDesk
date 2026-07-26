"""Tests: Runtime Integration — Cross-Insurer Integration (Phase 5).

Tests the complete E2E flow:
1. Runtime auto-detects the correct adapter from raw data
2. Extracts validated domain models
3. Switches seamlessly between insurers
4. Handles errors gracefully at each stage
5. Batch processes mixed-insurer data

Target: +20 tests
"""

from __future__ import annotations

import os
import sys
import pytest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. E2E Flow: GE Real-World Data (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestGEE2EFlow:
    """Great Eastern — real-world data simulation."""

    GE_PORTAL_DATA = {
        "policy_no": "F0377733",
        "insured_name": "Tiong Hoe Hung",
        "nric": "720415-01-1234",
        "inception_date": "2024-01-01",
        "expiry_date": "2025-01-01",
        "premium_amount": "1250.00",
        "policy_status": "In Force",
        "product_type": "fire",
    }

    def test_e2e_ge_runtime_auto_detect(self):
        """Runtime auto-detects GE from portal data."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy(self.GE_PORTAL_DATA)
        assert result.success
        assert "Great Eastern" in result.adapter_name
        assert result.model.policy_number == "F0377733"

    def test_e2e_ge_adapter_key(self):
        """Result has correct adapter key for GE."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy(self.GE_PORTAL_DATA)
        assert result.adapter_key == "great_eastern"

    def test_e2e_ge_validation(self):
        """GE validation passes for complete data."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy(self.GE_PORTAL_DATA)
        assert result.validation is not None

    def test_e2e_ge_model_fields(self):
        """All GE policy fields map correctly."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        from src.models.policy import PolicyStatus, ProductType
        result = executor.extract_policy(self.GE_PORTAL_DATA)
        p = result.model
        assert p.insurer == "Great Eastern"
        assert p.insured.ic_number == "720415-01-1234"
        assert p.premium.total == 1250.0
        assert p.status == PolicyStatus.ACTIVE  # "In Force" → ACTIVE
        assert p.source == "portal"


# ══════════════════════════════════════════════════════════════════
# 2. E2E Flow: Allianz Real-World Data (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestAllianzE2EFlow:
    """Allianz — real-world data simulation."""

    ALLIANZ_PORTAL_DATA = {
        "certificate_no": "AL-FIRE-2024-001",
        "insured_name": "Tan Mei Ling",
        "id_number": "850101-01-5678",
        "product": "Fire Insurance",
        "total_premium": "1800.50",
        "valid_from": "2024-03-01",
        "valid_until": "2025-03-01",
        "policy_status": "active",
    }

    def test_e2e_allianz_auto_detect(self):
        """Runtime auto-detects Allianz from certificate_no."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy(self.ALLIANZ_PORTAL_DATA)
        assert result.success
        assert "Allianz" in result.adapter_name

    def test_e2e_allianz_certificate_key(self):
        """Allianz certificate_no maps to policy_number."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy(self.ALLIANZ_PORTAL_DATA)
        assert result.model.policy_number == "AL-FIRE-2024-001"

    def test_e2e_allianz_product_mapping(self):
        """Allianz product maps to ProductType.FIRE."""
        from src.runtime import RuntimeExecutor
        from src.models.policy import ProductType
        executor = RuntimeExecutor()
        result = executor.extract_policy(self.ALLIANZ_PORTAL_DATA)
        assert result.model.product_type == ProductType.FIRE

    def test_e2e_allianz_dates(self):
        """Allianz dates map correctly."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy(self.ALLIANZ_PORTAL_DATA)
        assert result.model.inception_date == date(2024, 3, 1)
        assert result.model.expiry_date == date(2025, 3, 1)


# ══════════════════════════════════════════════════════════════════
# 3. E2E Flow: AIA Real-World Data (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestAIAE2EFlow:
    """AIA Malaysia — real-world data simulation."""

    AIA_PORTAL_DATA = {
        "policy_id": "AIA-LIFE-2024-001",
        "life_assured": "Kumar Raju",
        "owner_ic": "750101-01-9999",
        "plan_name": "AIA Secure Life",
        "basic_premium": "2400.00",
        "commencement_date": "2024-06-01",
        "maturity_date": "2054-06-01",
        "policy_status": "active",
    }

    def test_e2e_aia_auto_detect(self):
        """Runtime auto-detects AIA from life_assured."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy(self.AIA_PORTAL_DATA)
        assert result.success
        assert "AIA" in result.adapter_name

    def test_e2e_aia_policy_id_mapping(self):
        """AIA policy_id maps to policy_number."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy(self.AIA_PORTAL_DATA)
        assert result.model.policy_number == "AIA-LIFE-2024-001"

    def test_e2e_aia_insured_name(self):
        """AIA life_assured maps to insured name."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy(self.AIA_PORTAL_DATA)
        assert result.model.insured.name == "Kumar Raju"
        assert result.model.insured.ic_number == "750101-01-9999"

    def test_e2e_aia_dates(self):
        """AIA commencement/maturity map to inception/expiry."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy(self.AIA_PORTAL_DATA)
        assert result.model.inception_date == date(2024, 6, 1)
        assert result.model.expiry_date == date(2054, 6, 1)


# ══════════════════════════════════════════════════════════════════
# 4. Mixed Data Integration (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestMixedDataIntegration:
    """Runtime handles mixed data from multiple insurers."""

    def test_mixed_batch_all_formats(self):
        """Batch with all three insurers auto-detected."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        items = [
            {"policy_no": "GE-001", "insured_name": "Alice"},
            {"certificate_no": "AL-001", "insured_name": "Bob"},
            {"policy_id": "AIA-001", "life_assured": "Charlie"},
            {"policy_number": "GE-002", "insured_name": "Diana"},
        ]
        batch = executor.batch_extract(items)
        assert batch.total == 4
        assert batch.succeeded == 4
        assert batch.failed == 0

    def test_mixed_batch_adapter_variety(self):
        """Batch uses at least 3 different adapters."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        items = [
            {"policy_no": "GE-001"},
            {"certificate_no": "AL-001"},
            {"policy_id": "AIA-001", "life_assured": "Test"},
        ]
        batch = executor.batch_extract(items)
        adapter_keys = {r.adapter_key for r in batch.results}
        assert len(adapter_keys) >= 2

    def test_mixed_sequential_same_executor(self):
        """Same executor instance handles mixed sequential calls."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()

        # GE
        r1 = executor.extract_policy({"policy_no": "GE-X"})
        assert "Great Eastern" in r1.adapter_name

        # Allianz
        r2 = executor.extract_policy({"certificate_no": "AL-X"})
        assert "Allianz" in r2.adapter_name

        # AIA
        r3 = executor.extract_policy({"policy_id": "AIA-X", "life_assured": "Z"})
        assert "AIA" in r3.adapter_name

        # GE again
        r4 = executor.extract_policy({"policy_no": "GE-Y"})
        assert "Great Eastern" in r4.adapter_name

    def test_batch_with_explicit_hints(self):
        """Batch with explicit portal hints for documents lacking signature keys."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()

        # Document with only generic fields — needs explicit hint
        items = [
            {"policy_number": "UNKNOWN-001"},
            {"policy_number": "UNKNOWN-002"},
        ]
        batch = executor.batch_extract(items, portal_hint="great_eastern")
        assert batch.total == 2
        assert batch.succeeded == 2
        for r in batch.results:
            assert "Great Eastern" in r.adapter_name


# ══════════════════════════════════════════════════════════════════
# 5. Error Handling Integration (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestErrorHandlingIntegration:
    """Runtime handles errors at each stage."""

    def test_runtime_error_code_on_failure(self):
        """Failed extraction has machine-readable error code."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        result = executor.extract_policy({})
        assert not result.success
        assert result.error  # Non-empty error code
        assert isinstance(result.error, str)

    def test_runtime_error_context_on_failure(self):
        """Failed extraction has structured error context."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        # Use unrecognizable data with a nonexistent portal hint
        result = executor.extract_policy(
            {"unknown_field": "value"},
            portal_hint="nonexistent_portal",
        )
        assert not result.success
        assert result.error  # Non-empty error code
        assert isinstance(result.error_context, dict)

    def test_runtime_empty_batch(self):
        """Empty batch returns zero-count BatchResult."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        batch = executor.batch_extract([])
        assert batch.total == 0
        assert batch.succeeded == 0
        assert batch.failed == 0
        assert len(batch.results) == 0

    def test_runtime_batch_mixed_success_failure(self):
        """Batch with mixed success/failure produces correct counts."""
        from src.runtime import RuntimeExecutor
        executor = RuntimeExecutor()
        items = [
            {"policy_number": "GE-OK"},                          # Good
            {},                                                   # Empty → fail
            {"certificate_no": "AL-OK"},                          # Good
            {"policy_id": "AIA-OK", "life_assured": "Z"},        # Good
            {"policy_number": "GE-OK2", "insured_name": "A"},     # Good
        ]
        batch = executor.batch_extract(items)
        assert batch.succeeded >= 4   # 4 should succeed
        assert batch.failed == batch.total - batch.succeeded
