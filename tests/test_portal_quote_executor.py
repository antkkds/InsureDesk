"""Tests: Sprint 5.2 — FieldMapper and PortalQuoteExecutor.

Tests for:
1. FieldMapper — domain-to-portal field mapping
2. PortalQuoteExecutor — quote execution flow (with mock engine)
"""

from __future__ import annotations

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. FieldMapper (12 tests)
# ══════════════════════════════════════════════════════════════════


class TestFieldMapper:
    """Field mapping from domain to portal fields."""

    @pytest.fixture
    def sample_elements(self):
        return {
            "fire.jpj_f_q_insured_name": {
                "label": "fire.jpj_f_q_insured_name",
                "selector": "#f_insured_name",
                "tag": "input",
                "field_type": "text",
                "required": True,
                "max_length": 50,
            },
            "fire.jpj_f_q_cov_start_date": {
                "label": "fire.jpj_f_q_cov_start_date",
                "selector": "#f_period_from",
                "tag": "input",
                "field_type": "text",
                "required": True,
                "max_length": 10,
            },
            "fire.jpj_f_q_cov_end_date": {
                "label": "fire.jpj_f_q_cov_end_date",
                "selector": "#f_period_to",
                "tag": "input",
                "field_type": "text",
                "required": True,
                "max_length": 10,
            },
            "fire.jpj_f_q_si_fc": {
                "label": "fire.jpj_f_q_si_fc",
                "selector": "#f_si_fc",
                "tag": "input",
                "field_type": "text",
                "required": True,
                "max_length": 16,
            },
            "fire.jpj_f_q_si_building": {
                "label": "fire.jpj_f_q_si_building",
                "selector": "#f_si_building",
                "tag": "input",
                "field_type": "text",
                "required": False,
            },
            "fire.jpj_f_q_occupancy": {
                "label": "fire.jpj_f_q_occupancy",
                "selector": "#f_occupancy",
                "tag": "select",
                "field_type": "select",
                "required": True,
            },
            "fire.jpj_f_q_occupation": {
                "label": "fire.jpj_f_q_occupation",
                "selector": "#f_occupation",
                "tag": "select",
                "field_type": "select",
                "required": True,
            },
            "fire.jpj_f_q_email": {
                "label": "fire.jpj_f_q_email",
                "selector": "#f_email",
                "tag": "input",
                "field_type": "text",
                "required": False,
            },
        }

    def test_map_to_portal_basic(self, sample_elements):
        """Basic domain-to-portal field mapping."""
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper(channel_type="IFE")
        mapper._elements = sample_elements

        result = mapper.map_to_portal({
            "proposer_name": "Tiong Hoe Hung",
            "sum_insured": "5000000",
            "occupancy": "Factory",
        })

        assert "#f_insured_name" in result
        assert result["#f_insured_name"] == "Tiong Hoe Hung"
        assert "#f_si_fc" in result
        assert result["#f_si_fc"] == "5000000"
        assert "#f_occupancy" in result

    def test_map_to_portal_skips_empty_values(self, sample_elements):
        """Empty/None values should be skipped."""
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper(channel_type="IFE")
        mapper._elements = sample_elements

        result = mapper.map_to_portal({
            "proposer_name": "Test User",
            "sum_insured": None,
            "occupancy": "",
        })

        assert "#f_insured_name" in result
        assert "#f_si_fc" not in result
        assert "#f_occupancy" not in result

    def test_map_to_portal_partial_mapping(self, sample_elements):
        """Unmapped fields don't cause errors."""
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper(channel_type="IFE")
        mapper._elements = sample_elements

        result = mapper.map_to_portal({
            "proposer_name": "Test",
            "unknown_field": "should be ignored",
        })

        assert "#f_insured_name" in result
        assert len(result) == 1

    def test_map_to_domain_reverse(self, sample_elements):
        """Reverse mapping from portal fields to domain."""
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper(channel_type="IFE")
        mapper._elements = sample_elements

        # Portal data uses YAML keys (from profile), not CSS selectors
        result = mapper.map_to_domain({
            "jpj_f_q_insured_name": "Tiong Hoe Hung",
            "jpj_f_q_si_fc": "5000000",
        })

        assert result.get("proposer_name") == "Tiong Hoe Hung"
        assert result.get("sum_insured") == "5000000"

    def test_get_selector(self, sample_elements):
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper(channel_type="IFE")
        mapper._elements = sample_elements

        sel = mapper.get_selector("jpj_f_q_insured_name")
        assert sel == "#f_insured_name"

        sel = mapper.get_selector("nonexistent")
        assert sel is None

    def test_get_required_fields(self, sample_elements):
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper(channel_type="IFE")
        mapper._elements = sample_elements

        required = mapper.get_required_fields()
        # Fields with required=True in sample_elements
        required_keys = {r["domain_key"] for r in required}
        assert "proposer_name" in required_keys
        assert "sum_insured" in required_keys
        assert "occupancy" in required_keys
        assert "occupation" in required_keys

    def test_element_count(self, sample_elements):
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper(channel_type="IFE")
        mapper._elements = sample_elements
        assert mapper.element_count == 8

    def test_profile_not_found(self):
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper()
        with pytest.raises(FileNotFoundError):
            mapper.load_profile("/nonexistent/path.yaml")

    def test_elements_empty_without_profile(self):
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper()
        assert mapper.elements == {}

    def test_channel_type_case_insensitive(self):
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper(channel_type="ife")
        assert mapper.channel_type == "IFE"

    def test_map_to_portal_email_field(self, sample_elements):
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper(channel_type="IFE")
        mapper._elements = sample_elements

        result = mapper.map_to_portal({
            "proposer_email": "test@example.com",
        })
        assert "#f_email" in result
        assert result["#f_email"] == "test@example.com"

    def test_get_selector_exact_key(self, sample_elements):
        from src.quote.field_mapper import FieldMapper

        mapper = FieldMapper(channel_type="IFE")
        mapper._elements = sample_elements

        sel = mapper.get_selector("fire.jpj_f_q_insured_name")
        assert sel == "#f_insured_name"


# ══════════════════════════════════════════════════════════════════
# 2. PortalQuoteExecutor (8 tests)
# ══════════════════════════════════════════════════════════════════


class TestPortalQuoteExecutor:
    """PortalQuoteExecutor with mock engine."""

    @pytest.fixture
    def mock_engine(self):
        engine = MagicMock()
        engine.navigate = AsyncMock(return_value=True)
        engine.evaluate = AsyncMock(return_value="{}")
        return engine

    @pytest.fixture
    def mock_engine_with_form(self):
        """Mock engine that simulates a form-filled page."""
        engine = MagicMock()
        engine.navigate = AsyncMock(return_value=True)
        engine.evaluate = AsyncMock(side_effect=[
            '{"totalPremium": "RM 3,200", "quoteNumber": "Q12345"}',
            True,  # button click
        ])
        return engine

    @pytest.fixture
    def mapper_with_elements(self):
        from src.quote.field_mapper import FieldMapper
        mapper = FieldMapper(channel_type="IFE")
        mapper._elements = {
            "fire.jpj_f_q_insured_name": {
                "selector": "#f_insured_name",
                "tag": "input",
                "field_type": "text",
                "required": True,
            },
            "fire.jpj_f_q_si_fc": {
                "selector": "#f_si_fc",
                "tag": "input",
                "field_type": "text",
                "required": True,
            },
        }
        return mapper

    def test_create_with_minimal_args(self):
        from src.quote.portal_executor import PortalQuoteExecutor
        from src.portals.base import SessionMode

        executor = PortalQuoteExecutor()
        assert executor.mode == SessionMode.READ_ONLY
        assert executor.field_mapper is None

    def test_create_with_profile_path(self, tmp_path):
        from src.quote.portal_executor import PortalQuoteExecutor
        import yaml

        # Create a small test profile
        profile = tmp_path / "test_profile.yaml"
        profile.write_text(yaml.dump({
            "portal": "great_eastern",
            "quote_channel": "IFE",
            "pages": {
                "quote_form": {
                    "elements": {
                        "fire.jpj_f_q_insured_name": {
                            "selector": "#f_insured_name",
                            "tag": "input",
                            "field_type": "text",
                        },
                    },
                },
            },
        }))

        executor = PortalQuoteExecutor(profile_path=str(profile))
        assert executor.field_mapper is not None
        assert executor.field_mapper.element_count == 1

    def test_calculate_quote_no_engine(self):
        from src.quote.portal_executor import PortalQuoteExecutor

        executor = PortalQuoteExecutor()
        import asyncio
        result = asyncio.run(executor.calculate_quote({"test": "value"}))
        assert result.success is False
        assert "No browser engine" in result.error

    def test_calculate_quote_no_profile(self, mock_engine):
        from src.quote.portal_executor import PortalQuoteExecutor

        executor = PortalQuoteExecutor(engine=mock_engine)
        import asyncio
        result = asyncio.run(executor.calculate_quote({"test": "value"}))
        assert result.success is False
        assert "No profile loaded" in result.error

    def test_set_engine(self):
        from src.quote.portal_executor import PortalQuoteExecutor
        from unittest.mock import MagicMock

        executor = PortalQuoteExecutor()
        engine = MagicMock()
        executor.set_engine(engine)
        import asyncio
        result = asyncio.run(executor.calculate_quote({"test": "value"}))
        assert result.success is False
        assert "No profile loaded" in result.error

    def test_set_profile(self, tmp_path):
        from src.quote.portal_executor import PortalQuoteExecutor
        import yaml

        profile = tmp_path / "test.yaml"
        profile.write_text(yaml.dump({
            "portal": "great_eastern",
            "quote_channel": "IFE",
            "pages": {"quote_form": {"elements": {}}},
        }))

        executor = PortalQuoteExecutor()
        executor.set_profile(str(profile))
        assert executor.field_mapper is not None

    def test_check_form_ready_no_engine(self):
        from src.quote.portal_executor import PortalQuoteExecutor
        import asyncio

        executor = PortalQuoteExecutor()
        result = asyncio.run(executor.check_form_ready())
        assert result["ready"] is False
        assert "No browser engine" in result["error"]

    def test_check_form_ready_with_engine(self, mock_engine):
        from src.quote.portal_executor import PortalQuoteExecutor
        import asyncio

        # Mock 3 sequential evaluate calls: title, url, form_count
        mock_engine.evaluate = AsyncMock(side_effect=[
            "Fire Quote",
            "https://geglink.com/getquote/fireQuote.html",
            "42",
        ])
        executor = PortalQuoteExecutor(engine=mock_engine)
        result = asyncio.run(executor.check_form_ready())
        assert result["ready"] is True
        assert "getquote" in result["url"].lower()


# ══════════════════════════════════════════════════════════════════
# 3. QuoteExtractResult (3 tests)
# ══════════════════════════════════════════════════════════════════


class TestQuoteExtractResult:
    """QuoteExtractResult dataclass."""

    def test_defaults(self):
        from src.quote.portal_executor import QuoteExtractResult
        r = QuoteExtractResult(success=False)
        assert r.success is False
        assert r.premium == 0.0
        assert r.quote_number == ""
        assert r.raw_data == {}

    def test_success_fields(self):
        from src.quote.portal_executor import QuoteExtractResult
        r = QuoteExtractResult(
            success=True, premium=3200.0, quote_number="Q12345",
            gross_premium=3500.0, message="Calculated",
        )
        assert r.premium == 3200.0
        assert r.quote_number == "Q12345"
        assert r.gross_premium == 3500.0

    def test_to_dict(self):
        from src.quote.portal_executor import QuoteExtractResult
        r = QuoteExtractResult(success=True, premium=1500.0)
        d = r.to_dict()
        assert d["success"] is True
        assert d["premium"] == 1500.0
