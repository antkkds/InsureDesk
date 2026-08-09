"""Tests: Quote Engine — models, base adapter, GE adapters.

All tests use MockEngine (no Playwright/CDP required).
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ══════════════════════════════════════════════════════════════════
# 1. Quote Models (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestQuoteModels:
    """QuoteRequest, QuoteResult, QuoteDraft, QuoteItem, enums."""

    def test_quote_status_enum(self):
        from src.quote.models import QuoteStatus
        assert QuoteStatus.DRAFT.value == "draft"
        assert QuoteStatus.CALCULATED.value == "calculated"
        assert QuoteStatus.SUBMITTED.value == "submitted"

    def test_risk_class_enum(self):
        from src.quote.models import RiskClass
        assert RiskClass.FIRE.value == "fire"
        assert RiskClass.ENGINEERING.value == "engineering"

    def test_quote_item_defaults(self):
        from src.quote.models import QuoteItem
        item = QuoteItem()
        assert item.description == ""
        assert item.sum_insured == 0.0
        assert item.risk_class == ""

    def test_quote_item_with_values(self):
        from src.quote.models import QuoteItem
        item = QuoteItem(
            description="Factory Building",
            sum_insured=5000000.0,
            risk_class="fire",
            location="Kuala Lumpur",
        )
        assert item.sum_insured == 5000000.0
        assert item.location == "Kuala Lumpur"

    def test_quote_request_defaults(self):
        from src.quote.models import QuoteRequest
        r = QuoteRequest()
        assert r.proposer_name == ""
        assert r.channel_type == ""
        assert len(r.items) == 0

    def test_quote_request_with_fields(self):
        from src.quote.models import QuoteRequest, QuoteItem
        r = QuoteRequest(
            portal="great_eastern",
            channel_type="IFE",
            proposer_name="Test Company Sdn Bhd",
            risk_class="fire",
            items=[QuoteItem(description="Warehouse", sum_insured=2000000.0)],
        )
        assert r.portal == "great_eastern"
        assert r.channel_type == "IFE"
        assert len(r.items) == 1

    def test_quote_result_is_valid(self):
        from src.quote.models import QuoteResult, QuoteStatus
        r = QuoteResult(status=QuoteStatus.CALCULATED, total_premium=1500.0)
        assert r.is_valid is True

    def test_quote_draft_defaults(self):
        from src.quote.models import QuoteDraft
        d = QuoteDraft()
        assert d.draft_id == ""
        assert d.total_premium == 0.0


# ══════════════════════════════════════════════════════════════════
# 2. QuoteAdapter Base (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestQuoteAdapterBase:
    """QuoteAdapter abstract base class."""

    @pytest.mark.asyncio
    async def test_create_concrete_adapter(self):
        from src.quote.base import QuoteAdapter
        from src.browser.foundation import MockEngine

        class TestAdapter(QuoteAdapter):
            @property
            def name(self): return "test"
            @property
            def channel_type(self): return "TEST"
            async def create_quote(self, request): return None
            async def calculate(self, request): return None
            async def save_draft(self, qn): return None
            async def submit(self, qn): return None

        adapter = TestAdapter(MockEngine())
        assert adapter.name == "test"
        assert adapter.channel_type == "TEST"

    @pytest.mark.asyncio
    async def test_set_engine(self):
        from src.quote.base import QuoteAdapter
        from src.browser.foundation import MockEngine

        class TestAdapter(QuoteAdapter):
            @property
            def name(self): return "test"
            @property
            def channel_type(self): return "TEST"
            async def create_quote(self, request): return None
            async def calculate(self, request): return None
            async def save_draft(self, qn): return None
            async def submit(self, qn): return None

        e1 = MockEngine()
        e2 = MockEngine()
        adapter = TestAdapter(e1)
        assert adapter._engine is e1
        adapter.set_engine(e2)
        assert adapter._engine is e2

    @pytest.mark.asyncio
    async def test_health_check_default(self):
        from src.quote.base import QuoteAdapter
        from src.browser.foundation import MockEngine

        class TestAdapter(QuoteAdapter):
            def name(self): return "test"
            def channel_type(self): return "T"
            async def create_quote(self, request): return None
            async def calculate(self, request): return None
            async def save_draft(self, qn): return None
            async def submit(self, qn): return None

        adapter = TestAdapter(MockEngine())
        h = await adapter.health_check()
        assert "adapter" in h

    @pytest.mark.asyncio
    async def test_abstract_cannot_instantiate(self):
        from src.quote.base import QuoteAdapter
        with pytest.raises(TypeError):
            QuoteAdapter()  # Abstract

    @pytest.mark.asyncio
    async def test_engine_none_by_default(self):
        from src.quote.base import QuoteAdapter
        from src.browser.foundation import MockEngine

        class TestAdapter(QuoteAdapter):
            @property
            def name(self): return "test"
            @property
            def channel_type(self): return "T"
            async def create_quote(self, request): return None
            async def calculate(self, request): return None
            async def save_draft(self, qn): return None
            async def submit(self, qn): return None

        adapter = TestAdapter()
        assert adapter._engine is None


# ══════════════════════════════════════════════════════════════════
# 3. GE Quote Adapters (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestGEQuoteAdapters:
    """IFEQuoteAdapter, EQQuoteAdapter."""

    @pytest.mark.asyncio
    async def test_ife_adapter_identity(self):
        from src.quote.ge_adapters import IFEQuoteAdapter
        from src.browser.foundation import MockEngine
        a = IFEQuoteAdapter(MockEngine())
        assert a.name == "ife_quote"
        assert a.channel_type == "IFE"

    @pytest.mark.asyncio
    async def test_eq_adapter_identity(self):
        from src.quote.ge_adapters import EQQuoteAdapter
        from src.browser.foundation import MockEngine
        a = EQQuoteAdapter(MockEngine())
        assert a.name == "eq_quote"
        assert a.channel_type == "EQ"

    @pytest.mark.asyncio
    async def test_ife_create_quote_no_engine(self):
        from src.quote.ge_adapters import IFEQuoteAdapter
        from src.quote.models import QuoteRequest, QuoteStatus
        a = IFEQuoteAdapter()
        result = await a.create_quote(QuoteRequest())
        assert result.status == QuoteStatus.ERROR
        assert "No browser engine" in str(result.errors)

    @pytest.mark.asyncio
    async def test_eq_create_quote_no_engine(self):
        from src.quote.ge_adapters import EQQuoteAdapter
        from src.quote.models import QuoteRequest, QuoteStatus
        a = EQQuoteAdapter()
        result = await a.create_quote(QuoteRequest())
        assert result.status == QuoteStatus.ERROR

    @pytest.mark.asyncio
    async def test_ife_health_check(self):
        from src.quote.ge_adapters import IFEQuoteAdapter
        from src.browser.foundation import MockEngine
        a = IFEQuoteAdapter(MockEngine())
        h = await a.health_check()
        assert h["adapter"] == "ife_quote"
        assert h["channel_type"] == "IFE"
        assert h["engine_connected"] is True

    @pytest.mark.asyncio
    async def test_eq_health_check(self):
        from src.quote.ge_adapters import EQQuoteAdapter
        from src.browser.foundation import MockEngine
        a = EQQuoteAdapter(MockEngine())
        h = await a.health_check()
        assert h["adapter"] == "eq_quote"


# ══════════════════════════════════════════════════════════════════
# 4. GEGLinkAdapter Quote Launch (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestGEGLinkQuoteLaunch:
    """GEGLinkAdapter.launch_ife_quote(), launch_eq_quote()."""

    @pytest.mark.asyncio
    async def test_launch_ife_quote(self):
        from src.portals.great_eastern import GEGLinkAdapter
        from src.portal.mapping import load_portal_mapping
        adapter = GEGLinkAdapter()
        quote_adapter = adapter.launch_ife_quote()
        assert quote_adapter.name == "ife_quote"
        assert quote_adapter.channel_type == "IFE"

    @pytest.mark.asyncio
    async def test_launch_eq_quote(self):
        from src.portals.great_eastern import GEGLinkAdapter
        adapter = GEGLinkAdapter()
        quote_adapter = adapter.launch_eq_quote()
        assert quote_adapter.name == "eq_quote"
        assert quote_adapter.channel_type == "EQ"

    @pytest.mark.asyncio
    async def test_launch_quote_shares_engine(self):
        from src.portals.great_eastern import GEGLinkAdapter
        from src.browser.foundation import MockEngine
        adapter = GEGLinkAdapter()
        engine = MockEngine()
        adapter._engine = engine
        ife = adapter.launch_ife_quote()
        assert ife._engine is engine


# ══════════════════════════════════════════════════════════════════
# 5. Edge Cases (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestQuoteEdgeCases:
    """Edge cases for quote engine."""

    def test_quote_result_invalid_when_draft(self):
        from src.quote.models import QuoteResult, QuoteStatus
        r = QuoteResult(status=QuoteStatus.DRAFT, total_premium=5000.0)
        assert r.is_valid is False

    def test_quote_result_invalid_when_zero(self):
        from src.quote.models import QuoteResult, QuoteStatus
        r = QuoteResult(status=QuoteStatus.CALCULATED, total_premium=0.0)
        assert r.is_valid is False

    def test_quote_result_error_has_message(self):
        from src.quote.models import QuoteResult, QuoteStatus
        r = QuoteResult(
            status=QuoteStatus.ERROR,
            errors=["System unavailable", "Timeout"],
        )
        assert len(r.errors) == 2
        assert "Timeout" in r.errors
