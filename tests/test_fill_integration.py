"""Tests for Fill Engine — PortalAdapter integration."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.fill.schema import FillSchema, FieldDefinition, FieldType, fill_schema_from_dict


class TestPortalConfigSchemaLoading:
    def test_load_schema_from_yaml_dict(self):
        """Schemas can be loaded from a YAML-like dict."""
        yaml_data = {
            "schemas": {
                "customer": {
                    "customer_name": {
                        "selector": "#name",
                        "type": "text",
                        "required": True,
                    },
                    "gender": {
                        "selector": "#gender",
                        "type": "radio",
                        "transform": "gender",
                    },
                },
                "risk": {
                    "sum_insured": {
                        "selector": "#si",
                        "type": "text",
                        "required": True,
                    },
                },
            },
            "transformers": {
                "gender": {
                    "MALE": "M",
                    "FEMALE": "F",
                },
            },
        }

        schemas = {}
        for name, data in yaml_data.get("schemas", {}).items():
            schemas[name] = fill_schema_from_dict(name, data)

        assert "customer" in schemas
        assert "risk" in schemas
        assert schemas["customer"].fields["customer_name"].required is True
        assert schemas["customer"].fields["gender"].type == FieldType.RADIO
        assert schemas["risk"].fields["sum_insured"].selector == "#si"

    def test_schema_fields_have_correct_types(self):
        """Each field type maps correctly from YAML string."""
        data = {
            "text_field": {"selector": "#t", "type": "text"},
            "select_field": {"selector": "#s", "type": "select"},
            "checkbox_field": {"selector": "#c", "type": "checkbox"},
            "radio_field": {"selector": "#r", "type": "radio"},
            "date_field": {"selector": "#d", "type": "date"},
            "lookup_field": {"selector": "#l", "type": "lookup"},
            "upload_field": {"selector": "#u", "type": "upload"},
            "hidden_field": {"selector": "#h", "type": "hidden"},
            "textarea_field": {"selector": "#ta", "type": "textarea"},
            "readonly_field": {"selector": "#ro", "type": "readonly"},
        }

        schema = fill_schema_from_dict("types", data)
        assert schema.fields["text_field"].type == FieldType.TEXT
        assert schema.fields["select_field"].type == FieldType.SELECT
        assert schema.fields["checkbox_field"].type == FieldType.CHECKBOX
        assert schema.fields["radio_field"].type == FieldType.RADIO
        assert schema.fields["date_field"].type == FieldType.DATE
        assert schema.fields["lookup_field"].type == FieldType.LOOKUP
        assert schema.fields["upload_field"].type == FieldType.UPLOAD
        assert schema.fields["hidden_field"].type == FieldType.HIDDEN
        assert schema.fields["textarea_field"].type == FieldType.TEXTAREA
        assert schema.fields["readonly_field"].type == FieldType.READONLY


class TestPortalAdapterIntegration:
    """Tests for Fill schema loading via PortalAdapter (integration contract)."""

    def test_fill_engine_instantiation(self):
        """FillEngine can be created standalone without PortalAdapter."""
        from src.fill.engine import FillEngine
        engine = FillEngine()
        assert engine is not None
        assert engine.mapper is not None
        assert engine.verifier is not None
        assert engine.transformer is not None

    def test_transformer_from_yaml(self):
        """TransformerRegistry loads from YAML format."""
        from src.fill.transformer import TransformerRegistry
        registry = TransformerRegistry()
        registry.register_from_yaml({
            "gender": {"MALE": "M", "FEMALE": "F"},
            "occupation": {
                "ENGINEER": "002",
                "TEACHER": "018",
                "DOCTOR": "015",
            },
        })
        assert registry.transform("gender", "MALE") == "M"
        assert registry.transform("occupation", "DOCTOR") == "015"


class TestGreatEasternSchema:
    """Verify Great Eastern portal schema definition from YAML."""

    def test_ge_customer_schema_loads(self):
        """GE customer schema fields can be loaded."""
        data = {
            "customer_name": {"selector": "input[name='customerName']", "type": "text", "required": True},
            "customer_ic": {"selector": "input[name='customerIC']", "type": "text"},
            "gender": {"selector": "input[name='gender']", "type": "radio", "transform": "gender"},
            "dob": {"selector": "input[name='dob']", "type": "date", "format": "%d/%m/%Y"},
        }
        schema = fill_schema_from_dict("customer", data)
        assert schema.fields["customer_name"].required is True
        assert schema.fields["dob"].format == "%d/%m/%Y"
        assert schema.fields["gender"].transform == "gender"

    def test_ge_risk_schema_loads(self):
        """GE risk schema fields can be loaded."""
        data = {
            "sum_insured_building": {"selector": "input[name='siBuilding']", "type": "text", "required": True},
            "occupancy": {"selector": "select[name='occupancy']", "type": "select", "required": True},
        }
        schema = fill_schema_from_dict("risk", data)
        assert schema.fields["sum_insured_building"].required is True
        assert schema.fields["occupancy"].type == FieldType.SELECT

    def test_ge_coverage_schema_loads(self):
        """GE coverage schema fields can be loaded."""
        data = {
            "basic_cover": {"selector": "input[name='basicCover']", "type": "checkbox"},
            "excess": {"selector": "select[name='excess']", "type": "select"},
        }
        schema = fill_schema_from_dict("coverage", data)
        assert schema.fields["basic_cover"].type == FieldType.CHECKBOX
        assert schema.fields["excess"].type == FieldType.SELECT

    def test_ge_transformers_load(self):
        """GE transformer definitions can be processed."""
        from src.fill.transformer import TransformerRegistry
        registry = TransformerRegistry()
        registry.register_from_yaml({
            "gender": {"MALE": "M", "FEMALE": "F"},
        })
        assert registry.transform("gender", "MALE") == "M"
        assert registry.transform("gender", "FEMALE") == "F"
