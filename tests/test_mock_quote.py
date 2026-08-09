"""Tests: Phase 4 — MockQuoteAdapter + ReadOnlyMode.

Tests the MockQuoteRuntime (no browser needed) and
the READ_ONLY safety guard on quote adapters.
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ══════════════════════════════════════════════════════════════════
# 1. ReadOnlyMode (8 tests)
# ══════════════════════════════════════════════════════════════════


class TestReadOnlyMode:
    """SessionMode enumeration and ReadOnlyViolationError."""

    def test_session_mode_values(self):
        from src.portals.base import SessionMode
        assert SessionMode.READ_ONLY.value == "read_only"
        assert SessionMode.READ_WRITE.value == "read_write"

    def test_read_only_violation_error(self):
        from src.portals.base import ReadOnlyViolationError
        err = ReadOnlyViolationError("test error")
        assert str(err) == "test error"
        assert isinstance(err, RuntimeError)

    def test_adapter_default_mode_is_read_write(self):
        from src.portals.base import PortalAdapter, SessionMode
        # Can't instantiate abstract class, but we can check __init__ signature
        import inspect
        sig = inspect.signature(PortalAdapter.__init__)
        assert sig.parameters["mode"].default == SessionMode.READ_WRITE

    def test_mock_adapter_default_mode(self):
        from src.quote.mock import MockQuoteAdapter
        from src.portals.base import SessionMode
        adapter = MockQuoteAdapter()
        assert adapter.mode == SessionMode.READ_WRITE

    def test_mock_adapter_read_only_mode(self):
        from src.quote.mock import MockQuoteAdapter
        from src.portals.base import SessionMode
        adapter = MockQuoteAdapter(mode=SessionMode.READ_ONLY)
        assert adapter.mode == SessionMode.READ_ONLY

    def test_read_only_blocks_calculate(self):
        from src.quote.mock import MockQuoteAdapter
        from src.portals.base import SessionMode, ReadOnlyViolationError
        from src.quote.models import QuoteRequest

        adapter = MockQuoteAdapter(mode=SessionMode.READ_ONLY)
        request = QuoteRequest(risk_class="fire")

        with pytest.raises(ReadOnlyViolationError, match="READ_ONLY"):
            # calculate is async, need to run in event loop
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(adapter.calculate(request))
            finally:
                loop.close()

    def test_read_only_blocks_save_draft(self):
        from src.quote.mock import MockQuoteAdapter
        from src.portals.base import SessionMode, ReadOnlyViolationError

        adapter = MockQuoteAdapter(mode=SessionMode.READ_ONLY)
        with pytest.raises(ReadOnlyViolationError, match="READ_ONLY"):
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(adapter.save_draft("MOCK-001"))
            finally:
                loop.close()

    def test_read_only_allows_create_quote(self):
        """create_quote is a read operation in READ_ONLY mode."""
        from src.quote.mock import MockQuoteAdapter
        from src.portals.base import SessionMode
        from src.quote.models import QuoteRequest

        adapter = MockQuoteAdapter(mode=SessionMode.READ_ONLY)
        request = QuoteRequest(risk_class="fire")

        import asyncio
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(adapter.create_quote(request))
            assert result.status.value == "draft"
            assert "MOCK" in result.quote_number
        finally:
            loop.close()


# ══════════════════════════════════════════════════════════════════
# 2. MockQuoteAdapter — Quote Lifecycle (12 tests)
# ══════════════════════════════════════════════════════════════════


class TestMockQuoteLifecycle:
    """Full quote lifecycle using MockQuoteAdapter."""

    @pytest.fixture
    def adapter(self):
        from src.quote.mock import MockQuoteAdapter
        a = MockQuoteAdapter()
        a.reset()
        return a

    @pytest.fixture
    def fire_request(self):
        from src.quote.models import QuoteRequest, QuoteItem
        return QuoteRequest(
            portal="mock",
            adapter="mock_quote",
            channel_type="MOCK",
            proposer_name="Test Proposer",
            risk_class="fire",
            items=[QuoteItem(description="Factory Building", sum_insured=5000000)],
        )

    @pytest.fixture
    def event_loop(self):
        import asyncio
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    def test_create_quote(self, adapter, fire_request, event_loop):
        result = event_loop.run_until_complete(adapter.create_quote(fire_request))
        assert result.status.value == "draft"
        assert result.quote_number.startswith("MOCK-")

    def test_create_then_calculate(self, adapter, fire_request, event_loop):
        event_loop.run_until_complete(adapter.create_quote(fire_request))
        result = event_loop.run_until_complete(adapter.calculate(fire_request))
        assert result.status.value == "calculated"
        assert result.total_premium > 0
        assert result.gross_premium > 0

    def test_full_lifecycle(self, adapter, fire_request, event_loop):
        # create
        create = event_loop.run_until_complete(adapter.create_quote(fire_request))
        assert create.status.value == "draft"
        qn = create.quote_number

        # calculate
        calc = event_loop.run_until_complete(adapter.calculate(fire_request))
        assert calc.status.value == "calculated"
        assert calc.total_premium > 0

        # save draft
        draft = event_loop.run_until_complete(adapter.save_draft(qn))
        assert draft is not None
        assert draft.quote_number == qn
        assert draft.status.value == "saved"

        # resume draft
        resumed = event_loop.run_until_complete(adapter.resume_draft(qn))
        assert resumed is not None
        assert resumed.quote_number == qn

        # submit
        submit = event_loop.run_until_complete(adapter.submit(qn))
        assert submit.status.value == "submitted"

    def test_premium_varies_by_risk_class(self, adapter, event_loop):
        from src.quote.models import QuoteRequest, QuoteItem

        fire = event_loop.run_until_complete(adapter.calculate(
            QuoteRequest(risk_class="fire", items=[QuoteItem(sum_insured=1000000)])
        ))
        motor = event_loop.run_until_complete(adapter.calculate(
            QuoteRequest(risk_class="motor", items=[QuoteItem(sum_insured=1000000)])
        ))
        # Motor has higher multiplier (4.0 vs 2.5)
        assert motor.total_premium > fire.total_premium

    def test_stamp_duty_and_tax_included(self, adapter, fire_request, event_loop):
        result = event_loop.run_until_complete(adapter.calculate(fire_request))
        assert result.stamp_duty > 0
        assert result.tax_amount > 0
        # total = gross + stamp_duty + tax
        expected_total = round(result.gross_premium + result.stamp_duty + result.tax_amount, 2)
        assert result.total_premium == expected_total

    def test_breakdown_contains_premium_fields(self, adapter, fire_request, event_loop):
        result = event_loop.run_until_complete(adapter.calculate(fire_request))
        assert "gross_premium" in result.breakdown
        assert "stamp_duty" in result.breakdown
        assert "sum_insured" in result.breakdown

    def test_create_quote_without_items_defaults(self, adapter, event_loop):
        from src.quote.models import QuoteRequest
        request = QuoteRequest(risk_class="fire")
        result = event_loop.run_until_complete(adapter.create_quote(request))
        assert result.status.value == "draft"

    def test_health_check(self, adapter, event_loop):
        health = event_loop.run_until_complete(adapter.health_check())
        assert health["name"] == "mock_quote"
        assert health["mode"] == "read_write"
        assert health["quotes_created"] == 0
        assert health["active_quote"] is False

    def test_reset(self, adapter, fire_request, event_loop):
        event_loop.run_until_complete(adapter.create_quote(fire_request))
        assert adapter._quote_counter == 1
        adapter.reset()
        assert adapter._quote_counter == 0

    def test_config_customization(self):
        from src.quote.mock import MockQuoteConfig, MockQuoteAdapter
        config = MockQuoteConfig(
            base_premium=100.0,
            fail_rate=0.0,
        )
        adapter = MockQuoteAdapter(config=config)
        assert adapter.config.base_premium == 100.0

    def test_submit_without_create(self, adapter, event_loop):
        """Submit should work with just a quote number (no active state needed)."""
        result = event_loop.run_until_complete(adapter.submit("MOCK-001"))
        assert result.status.value == "submitted"


# ══════════════════════════════════════════════════════════════════
# 3. MockQuoteAdapter — Error Simulation (5 tests)
# ══════════════════════════════════════════════════════════════════


class TestMockQuoteErrors:
    """MockQuoteAdapter error simulation."""

    @pytest.fixture
    def adapter(self):
        from src.quote.mock import MockQuoteConfig, MockQuoteAdapter
        a = MockQuoteAdapter(config=MockQuoteConfig(fail_rate=1.0))
        a.reset()
        return a

    @pytest.fixture
    def fire_request(self):
        from src.quote.models import QuoteRequest, QuoteItem
        return QuoteRequest(
            risk_class="fire",
            items=[QuoteItem(description="Building", sum_insured=5000000)],
        )

    @pytest.fixture
    def event_loop(self):
        import asyncio
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    def test_create_quote_with_high_fail_rate(self, adapter, fire_request, event_loop):
        result = event_loop.run_until_complete(adapter.create_quote(fire_request))
        assert result.status.value == "error"
        assert len(result.errors) > 0

    def test_calculate_with_high_fail_rate(self, adapter, fire_request, event_loop):
        result = event_loop.run_until_complete(adapter.calculate(fire_request))
        assert result.status.value == "error"

    def test_submit_with_high_fail_rate(self, adapter, fire_request, event_loop):
        # Submit also triggers fail check
        result = event_loop.run_until_complete(adapter.submit("MOCK-001"))
        assert result.status.value == "error"

    def test_zero_fail_rate_no_errors(self, event_loop):
        from src.quote.mock import MockQuoteConfig, MockQuoteAdapter
        from src.quote.models import QuoteRequest
        adapter = MockQuoteAdapter(config=MockQuoteConfig(fail_rate=0.0))
        adapter.reset()

        for _ in range(10):
            result = event_loop.run_until_complete(
                adapter.create_quote(QuoteRequest(risk_class="fire"))
            )
            assert result.status.value != "error"
