"""Tests: Document Intelligence Plugin — Extractor, Parser, Converter."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ══════════════════════════════════════════════════════════════════
# Sample Malaysian insurance policy texts
# ══════════════════════════════════════════════════════════════════

SAMPLE_FIRE_POLICY = """
                          GREAT EASTERN
                     FIRE INSURANCE POLICY
                     ======================

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
Policy Period: Whole Life

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
# 1. Parser Tests
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
        result = parser.parse(SAMPLE_EMPTY)

        assert result.policy_number.value is None
        assert result.insured_name.value is None
        assert result.confidence_overall.value == "unknown"

    def test_parse_partial_text(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser

        parser = PolicyTextParser()
        result = parser.parse(SAMPLE_PARTIAL)

        assert result.policy_number.value == "ABC789XYZ"
        assert result.insured_name.value == "Testing Only"

    def test_field_value_reliable(self):
        from src.plugins.document_intelligence.models import FieldValue, PolicyFieldConfidence

        fv = FieldValue(value="test", confidence=PolicyFieldConfidence.HIGH)
        assert fv.is_reliable

        fv = FieldValue(value="test", confidence=PolicyFieldConfidence.LOW)
        assert not fv.is_reliable


# ══════════════════════════════════════════════════════════════════
# 2. Converter Tests
# ══════════════════════════════════════════════════════════════════


class TestPolicyConverter:
    def test_to_uipai_format(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser
        from src.plugins.document_intelligence.converter import PolicyConverter

        parser = PolicyTextParser()
        parsed = parser.parse(SAMPLE_FIRE_POLICY)

        uipai = PolicyConverter.to_uipai_format(parsed)
        assert uipai["policy"]["number"] == "GEG123456789"
        assert uipai["insured"]["name"] == "John Tan Ah Kow"
        assert uipai["premium"]["total"] == 1234.50
        assert len(uipai["coverages"]) >= 2
        assert len(uipai["exclusions"]) >= 3
        assert "_query" in uipai
        assert uipai["_query"]["has_coverage"]

    def test_to_natural_language(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser
        from src.plugins.document_intelligence.converter import PolicyConverter

        parser = PolicyTextParser()
        parsed = parser.parse(SAMPLE_FIRE_POLICY)

        nl = PolicyConverter.to_natural_language(parsed)
        assert "Policy Number:" in nl
        assert "Great Eastern" in nl
        assert "John Tan Ah Kow" in nl
        assert "1,234.50" in nl
        assert "Buildings" in nl

    def test_to_db_record(self):
        from src.plugins.document_intelligence.parser import PolicyTextParser
        from src.plugins.document_intelligence.converter import PolicyConverter

        parser = PolicyTextParser()
        parsed = parser.parse(SAMPLE_FIRE_POLICY)

        db = PolicyConverter.to_db_record(parsed, "cust_001", "doc_001")
        assert db["customer_id"] == "cust_001"
        assert db["document_id"] == "doc_001"
        assert db["company"] == "Great Eastern"
        assert db["policy_number"] == "GEG123456789"
        assert db["policy_type"] == "fire"
        assert "coverages_json" in db
        assert "raw_json" in db

        # Verify JSON fields are valid
        coverages = json.loads(db["coverages_json"])
        assert len(coverages) >= 2


# ══════════════════════════════════════════════════════════════════
# 3. Extractor Tests (with temp PDF)
# ══════════════════════════════════════════════════════════════════


class TestPDFExtractor:
    def test_file_not_found(self):
        from src.plugins.document_intelligence.extractor import PDFExtractor

        ext = PDFExtractor()
        result = ext.extract("/nonexistent/file.pdf")
        assert result.error is not None
        assert "not found" in result.error

    def test_not_a_pdf(self):
        from src.plugins.document_intelligence.extractor import PDFExtractor

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not a pdf")
            tmp = f.name
        try:
            ext = PDFExtractor()
            result = ext.extract(tmp)
            assert result.error is not None
            assert "Not a PDF" in result.error
        finally:
            os.unlink(tmp)

    def test_extract_digital_pdf(self):
        """Create a minimal PDF with PyMuPDF and verify extraction."""
        from src.plugins.document_intelligence.extractor import PDFExtractor

        # Create a minimal PDF using PyMuPDF
        try:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((50, 100), "Policy Number: TEST001", fontsize=12)
            page.insert_text((50, 130), "Insured: Test User", fontsize=12)
            page.insert_text((50, 160), "Total Premium: RM 1,000.00", fontsize=12)

            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.close()
            doc.save(tmp.name)
            doc.close()

            ext = PDFExtractor()
            result = ext.extract(tmp.name)
            assert result.succeeded
            assert result.format.value == "digital"
            assert result.page_count == 1
            assert "TEST001" in result.raw_text
            assert "Test User" in result.raw_text

            os.unlink(tmp.name)
        except ImportError:
            pytest.skip("PyMuPDF not installed")

    def test_extract_metadata(self):
        from src.plugins.document_intelligence.extractor import PDFExtractor

        try:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((50, 100), "Test metadata", fontsize=12)
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.close()
            doc.save(tmp.name)
            doc.close()

            ext = PDFExtractor()
            meta = ext.get_metadata(tmp.name)
            assert meta["page_count"] == 1
            assert meta["file_size"] > 0

            os.unlink(tmp.name)
        except ImportError:
            pytest.skip("PyMuPDF not installed")

    def test_is_digital(self):
        from src.plugins.document_intelligence.extractor import PDFExtractor

        try:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((50, 100), "A" * 200, fontsize=12)
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.close()
            doc.save(tmp.name)
            doc.close()

            ext = PDFExtractor()
            assert ext.is_digital(tmp.name)

            os.unlink(tmp.name)
        except ImportError:
            pytest.skip("PyMuPDF not installed")


# ══════════════════════════════════════════════════════════════════
# 4. Integration — full pipeline
# ══════════════════════════════════════════════════════════════════


class TestDocIntelPipeline:
    def test_parser_to_converter_pipeline(self):
        """Text → Parser → Converter → UIP-AI format."""
        from src.plugins.document_intelligence.parser import PolicyTextParser
        from src.plugins.document_intelligence.converter import PolicyConverter

        parser = PolicyTextParser()
        converter = PolicyConverter()

        # Parse
        parsed = parser.parse(SAMPLE_FIRE_POLICY)
        assert parsed.policy_number.value == "GEG123456789"

        # Convert to UIP-AI
        uipai = converter.to_uipai_format(parsed)
        assert uipai["_query"]["has_coverage"]
        assert uipai["_query"]["confidence"] in ("high", "medium")

        # Convert to DB
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

    def test_to_json_compatible(self):
        """Verify ParsedPolicy.to_json_compatible() output structure."""
        from src.plugins.document_intelligence.parser import PolicyTextParser

        parser = PolicyTextParser()
        parsed = parser.parse(SAMPLE_FIRE_POLICY)

        json_data = parsed.to_json_compatible()
        # Verify nested structure
        assert "policy" in json_data
        assert "insured" in json_data
        assert "premium" in json_data
        assert "coverages" in json_data
        assert "exclusions" in json_data
        assert "_meta" in json_data

        # Verify types
        assert isinstance(json_data["coverages"], list)
        assert isinstance(json_data["exclusions"], list)
        assert isinstance(json_data["premium"]["total"], float)
