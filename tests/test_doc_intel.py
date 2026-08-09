"""Tests: Document Intelligence Plugin — Parser, Converter, Plugin.

Tests the insurance-specific layers only.
PDF extraction is delegated to the standalone document-intelligence SDK
(https://github.com/antkkds/document-intelligence) — not tested here.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ══════════════════════════════════════════════════════════════════
# Sample Malaysian insurance policy texts
# ══════════════════════════════════════════════════════════════════

SAMPLE_FIRE_POLICY = """
                          GREAT EASTERN
                     FIRE INSURANCE POLICY
                     =====================

Policy Number: GEG123456789
Policy Type: Houseowner Insurance

Insured Name: John Tan Ah Kow
IC Number: 881010-01-1234
Address: 12, Jalan SS2/72, 47300 Petaling Jaya, Selangor

Period of Insurance: From 01/01/2024 to 31/12/2024

Total Sum Insured: RM 500,000.00
Total Premium: RM 1,234.50

Coverage:
----------

Section I - Buildings
    Sum Insured: RM 350,000.00
    Premium: RM 864.15

Section II - Contents
    Sum Insured: RM 150,000.00
    Premium: RM 370.35

Exclusions:
1. War and nuclear risks
2. Wear and tear
3. Intentional damage
4. Flood damage unless specifically covered
5. Earthquake damage
"""

SAMPLE_MOTOR_POLICY = """
                            ALLIANZ GENERAL
                          MOTOR INSURANCE POLICY

Policy No: A1234567890
Product: Comprehensive Motor Insurance

Name of Insured: Lim Mei Ling
IC: 920505-14-5678

Vehicle: Proton X70 1.5 TGDI (2023)
Plate Number: ABC 1234

Cover Period: 15/03/2024 - 14/03/2025

Sum Insured: RM 98,000.00
Annual Premium: RM 2,456.80

Exclusions:
1. Driving under influence of alcohol or drugs
2. Using vehicle for illegal purposes
3. Damage during war or civil commotion
4. Normal wear and tear
5. Driving without valid license
"""

SAMPLE_LIFE_POLICY = """
                         AIA BHD
                      LIFE INSURANCE POLICY

Policy Number: AIA87654321
Plan: AIA Secure Life Plus

Insured: Sarah Tan
IC No: 780101-01-5678

Coverage:

Death Benefit: RM 500,000
Total Permanent Disability: RM 500,000
Critical Illness: RM 300,000

Monthly Premium: RM 450.00
Annual Premium: RM 5,400.00

Issue Date: 01/06/2020
Policy Period: 01/06/2020 - 01/06/2040
Premium Paying Term: 20 years

Exclusions:
1. Suicide within first 12 months
2. Pre-existing conditions not disclosed
3. War or military service
4. Hazardous activities
5. Intentionally self-inflicted injury
"""

SAMPLE_EMPTY = "This is not a policy document. Just some random text."

SAMPLE_PARTIAL = """
Policy Number: ABC789XYZ
Name of Insured: Testing Only
"""


# ══════════════════════════════════════════════════════════════════
# 1. Parser Tests (insurance-specific, NOT in standalone SDK)
# ══════════════════════════════════════════════════════════════════


class TestPolicyParser:
    def test_parse_fire_policy(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser

        parser = PolicyTextParser()
        result = parser.parse(SAMPLE_FIRE_POLICY)

        assert result.policy_number.value == "GEG123456789"
        assert result.insurer.value == "Great Eastern"
        assert result.insured_name.value == "John Tan Ah Kow"
        assert result.insured_ic.value == "881010-01-1234"
        assert result.total_premium.value == 1234.50
        assert result.total_sum_insured.value == 500000.0
        assert result.start_date.value is not None
        assert result.end_date.value is not None
        assert len(result.coverages) >= 2
        assert len(result.exclusions) >= 3

    def test_parse_motor_policy(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser

        parser = PolicyTextParser()
        result = parser.parse(SAMPLE_MOTOR_POLICY)

        assert result.insurer.value == "Allianz General"
        assert result.insured_name.value == "Lim Mei Ling"
        assert result.insured_ic.value == "920505-14-5678"
        assert result.total_premium.value == 2456.80
        assert result.total_sum_insured.value == 98000.0
        assert result.product_type.value == "motor"

    def test_parse_life_policy(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser

        parser = PolicyTextParser()
        result = parser.parse(SAMPLE_LIFE_POLICY)

        assert result.insurer.value == "Aia Bhd"
        assert result.insured_name.value == "Sarah Tan"
        assert result.policy_number.value == "AIA87654321"
        assert result.product_type.value == "life"

    def test_parse_empty_text(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser

        parser = PolicyTextParser()
        result = parser.parse("")
        assert result.errors is not None
        assert "Empty" in result.errors[0]

    def test_parse_partial_data(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser

        parser = PolicyTextParser()
        result = parser.parse(SAMPLE_PARTIAL)

        assert result.policy_number.value == "ABC789XYZ"
        assert result.insured_name.value == "Testing Only"
        assert result.total_premium.value is None
        assert result.insurer.value is None

    def test_parse_noise_text(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser

        parser = PolicyTextParser()
        result = parser.parse(SAMPLE_EMPTY)

        assert result.confidence_overall.value == "unknown"

    def test_to_json_compatible(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser

        parser = PolicyTextParser()
        result = parser.parse(SAMPLE_FIRE_POLICY)

        json_data = result.to_json_compatible()

        assert "policy" in json_data
        assert json_data["policy"]["number"] == "GEG123456789"
        assert json_data["policy"]["insurer"] == "Great Eastern"

        assert "insured" in json_data
        assert json_data["insured"]["name"] == "John Tan Ah Kow"

        assert "premium" in json_data
        assert json_data["premium"]["total"] == 1234.50
        assert json_data["premium"]["currency"] == "MYR"

        assert "coverages" in json_data
        assert "exclusions" in json_data
        assert "_meta" in json_data
        assert json_data["_meta"]["confidence"] in ("high", "medium")


# ══════════════════════════════════════════════════════════════════
# 2. Converter Tests (insurance-specific)
# ══════════════════════════════════════════════════════════════════


class TestPolicyConverter:
    def test_to_db_record(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser
        from src.plugins.document_intelligence.converter import PolicyConverter

        parser = PolicyTextParser()
        parsed = parser.parse(SAMPLE_FIRE_POLICY)

        db = PolicyConverter.to_db_record(parsed, "cust_001", "doc_001")

        assert db["customer_id"] == "cust_001"
        assert db["document_id"] == "doc_001"
        assert db["policy_number"] == "GEG123456789"
        assert db["company"] == "Great Eastern"
        assert db["policy_type"] == "fire"
        # Verify raw_json is valid JSON with expected keys
        rj = json.loads(db["raw_json"])
        assert "policy" in rj
        assert "insured" in rj
        assert "premium" in rj
        # Verify coverages_json is valid JSON
        cj = json.loads(db["coverages_json"])
        assert isinstance(cj, list)
        # Verify exclusions_json is valid JSON
        ej = json.loads(db["exclusions_json"])
        assert isinstance(ej, list)

    def test_to_db_record_document_fields_present(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser
        from src.plugins.document_intelligence.converter import PolicyConverter

        parser = PolicyTextParser()
        parsed = parser.parse(SAMPLE_FIRE_POLICY)
        db = PolicyConverter.to_db_record(parsed, "cust_001", "doc_001")

        assert db.get("customer_id") == "cust_001"
        assert db.get("document_id") == "doc_001"
        assert db.get("version") == 1
        assert db.get("summary") is not None

    def test_to_uipai_format(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser
        from src.plugins.document_intelligence.converter import PolicyConverter

        parser = PolicyTextParser()
        parsed = parser.parse(SAMPLE_FIRE_POLICY)

        uipai = PolicyConverter.to_uipai_format(parsed)

        assert "_query" in uipai
        assert uipai["_query"]["has_coverage"]
        assert uipai["_query"]["has_exclusions"]
        assert uipai["_query"]["confidence"] in ("high", "medium", "low")

    def test_to_natural_language(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser
        from src.plugins.document_intelligence.converter import PolicyConverter

        parser = PolicyTextParser()
        parsed = parser.parse(SAMPLE_FIRE_POLICY)

        nl = PolicyConverter.to_natural_language(parsed)

        assert "Great Eastern" in nl
        assert "Buildings" in nl
        assert "Contents" in nl


# ══════════════════════════════════════════════════════════════════
# 3. Plugin Tests (thin integration layer)
# ══════════════════════════════════════════════════════════════════


class TestDocumentIntelligencePlugin:
    def test_plugin_properties(self):
        from src.plugins.document_intelligence.plugin import (
            DocumentIntelligencePlugin,
        )

        plugin = DocumentIntelligencePlugin()

        assert plugin.id == "document_intelligence"
        assert plugin.version == "1.0.0"
        assert "document.parse" in plugin.capabilities
        assert "document.extract_policy" in plugin.capabilities
        assert "document.index" in plugin.capabilities

    def test_plugin_initialize_with_context(self):
        from src.plugins.base import PluginContext
        from src.plugins.document_intelligence.plugin import (
            DocumentIntelligencePlugin,
        )

        plugin = DocumentIntelligencePlugin()
        ctx = PluginContext()
        plugin.initialize(ctx)
        # Should not raise

    def test_plugin_shutdown(self):
        from src.plugins.document_intelligence.plugin import (
            DocumentIntelligencePlugin,
        )

        plugin = DocumentIntelligencePlugin()
        plugin.shutdown()
        # Should not raise

    def test_plugin_fallback_pymupdf(self):
        """Test that the plugin's fallback PyMuPDF extraction works.

        This tests the _extract_pymupdf path when no SDK is available.
        """
        from src.plugins.document_intelligence.plugin import (
            DocumentIntelligencePlugin,
        )

        plugin = DocumentIntelligencePlugin()

        try:
            import fitz

            # Create a temp PDF with known text
            import tempfile

            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((50, 100), SAMPLE_FIRE_POLICY, fontsize=8)
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.close()
            doc.save(tmp.name)
            doc.close()

            # Parse with fallback (SDK not available in this env)
            parsed = plugin.parse_policy(tmp.name, use_sdk=False)

            assert parsed.policy_number.value == "GEG123456789"
            assert parsed.insurer.value == "Great Eastern"
            assert parsed.insured_name.value == "John Tan Ah Kow"

            os.unlink(tmp.name)

        except ImportError:
            pytest.skip("PyMuPDF not installed")

    def test_parse_to_db_via_plugin(self):
        from src.plugins.document_intelligence.plugin import (
            DocumentIntelligencePlugin,
        )

        plugin = DocumentIntelligencePlugin()

        try:
            import fitz
            import tempfile

            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((50, 100), SAMPLE_FIRE_POLICY, fontsize=8)
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.close()
            doc.save(tmp.name)
            doc.close()

            db = plugin.parse_to_db(tmp.name, "cust_001", "doc_001", use_sdk=False)

            assert db["policy_number"] == "GEG123456789"
            assert db["customer_id"] == "cust_001"

            os.unlink(tmp.name)

        except ImportError:
            pytest.skip("PyMuPDF not installed")

    def test_parse_to_natural_language_via_plugin(self):
        from src.plugins.document_intelligence.plugin import (
            DocumentIntelligencePlugin,
        )

        plugin = DocumentIntelligencePlugin()

        try:
            import fitz
            import tempfile

            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((50, 100), SAMPLE_FIRE_POLICY, fontsize=8)
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.close()
            doc.save(tmp.name)
            doc.close()

            nl = plugin.parse_to_natural_language(
                tmp.name, use_sdk=False
            )

            assert "Great Eastern" in nl
            assert "Buildings" in nl

            os.unlink(tmp.name)

        except ImportError:
            pytest.skip("PyMuPDF not installed")

    def test_parse_file_not_found(self):
        from src.plugins.document_intelligence.plugin import (
            DocumentIntelligencePlugin,
        )

        plugin = DocumentIntelligencePlugin()

        with pytest.raises(FileNotFoundError):
            plugin.parse_policy("/nonexistent/file.pdf")

    def test_registration_with_registry(self):
        """Test the plugin can be registered with PluginRegistry."""
        from src.plugins.registry import PluginRegistry
        from src.plugins.base import PluginContext
        from src.plugins.document_intelligence.plugin import (
            DocumentIntelligencePlugin,
        )

        registry = PluginRegistry()
        plugin = DocumentIntelligencePlugin()

        registry.register(plugin)
        registry.initialize_all(PluginContext())

        # Find by capability
        parsers = registry.find_capability("document.extract_policy")
        assert len(parsers) == 1
        assert parsers[0].id == "document_intelligence"

        # Get by ID
        fetched = registry.get("document_intelligence")
        assert fetched is not None
        assert fetched.version == "1.0.0"

        registry.shutdown_all()


# ══════════════════════════════════════════════════════════════════
# 4. Integration — Parser → Converter pipeline (text-only, no PDF)
# ══════════════════════════════════════════════════════════════════


class TestDocIntelPipeline:
    def test_parser_to_converter_pipeline(self):
        """Text → Parser → Converter → UIP-AI format."""
        from src.plugins.document_intelligence.parser import PolicyTextParser
        from src.plugins.document_intelligence.converter import PolicyConverter

        parser = PolicyTextParser()
        converter = PolicyConverter()

        parsed = parser.parse(SAMPLE_FIRE_POLICY)
        assert parsed.policy_number.value == "GEG123456789"

        uipai = converter.to_uipai_format(parsed)
        assert uipai["_query"]["has_coverage"]
        assert uipai["_query"]["confidence"] in ("high", "medium")

        db = converter.to_db_record(parsed, "cust_001", "doc_001")
        assert db["policy_number"] == "GEG123456789"

    def test_parser_to_natural_language(self):
        """Text → Parser → Natural Language summary."""
        from src.plugins.document_intelligence.parser import PolicyTextParser
        from src.plugins.document_intelligence.converter import PolicyConverter

        parser = PolicyTextParser()
        parsed = parser.parse(SAMPLE_FIRE_POLICY)

        nl = PolicyConverter.to_natural_language(parsed)
        assert "Great Eastern" in nl
        assert "Buildings" in nl
        assert "Contents" in nl
        assert "500,000" in nl or "350,000" in nl
