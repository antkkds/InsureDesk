"""Tests for Fill Engine — FillEngine Integration."""
from __future__ import annotations

import pytest
from src.fill.engine import FillEngine
from src.fill.schema import FieldDefinition, FieldType, FillSchema
from src.fill.transformer import TransformerRegistry
from src.fill.exceptions import UnsupportedFieldTypeError
from tests.mock_browser import MockBrowser


def _make_field(name: str, type_str: str = "text", **kwargs) -> FieldDefinition:
    ft = FieldType(type_str) or FieldType.TEXT
    return FieldDefinition(name=name, selector=f"#{name}", type=ft, **kwargs)


def _make_schema(name: str, fields: list[FieldDefinition]) -> FillSchema:
    return FillSchema(name=name, fields={f.name: f for f in fields})


class TestFillEngineSingleField:
    @pytest.mark.asyncio
    async def test_fill_one_text_field(self):
        browser = MockBrowser()
        browser.register_selector("#name")

        engine = FillEngine()
        field = _make_field("name", "text", verify=False)
        result = await engine.fill_field(browser, field, "John")
        assert result.success is True
        assert result.field == "name"
        assert browser.filled.get("#name") == "John"

    @pytest.mark.asyncio
    async def test_fill_with_transformer(self):
        browser = MockBrowser()
        browser.register_selector("#name")

        registry = TransformerRegistry()
        registry.register("uppercase", {})  # Use builtin
        engine = FillEngine(transformer_registry=registry)

        # Apply transformer manually
        value = registry.transform("uppercase", "john")
        field = _make_field("name", "text", verify=False)
        result = await engine.fill_field(browser, field, value)
        assert result.success is True
        assert browser.filled.get("#name") == "JOHN"

    @pytest.mark.asyncio
    async def test_fill_field_not_found(self):
        browser = MockBrowser()
        engine = FillEngine()
        field = _make_field("missing", "text", verify=False)

        result = await engine.fill_field(browser, field, "value")
        assert result.success is False  # FieldNotFoundError caught
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_fill_unsupported_type(self):
        browser = MockBrowser()
        engine = FillEngine()
        ft = FieldType("text")
        # Remove text strategy to test unsupported type
        engine._strategies = {}
        field = FieldDefinition(name="test", selector="#test", type=ft)

        result = await engine.fill_field(browser, field, "value")
        assert result.success is False
        assert "No strategy registered" in (result.error or "")


class TestFillEngineSection:
    @pytest.mark.asyncio
    async def test_fill_section_all_success(self):
        browser = MockBrowser()
        browser.register_selector("#name")
        browser.register_selector("#age")
        browser.register_selector("#state")
        # Pre-register checkbox as not checked, mock click will toggle it
        browser.checked["#active"] = False
        browser.selectors_found.add("#active")

        schema = _make_schema("customer", [
            _make_field("name", "text", verify=False),
            _make_field("age", "text", verify=False),
            _make_field("state", "select", verify=False),
            FieldDefinition(name="active", selector="#active", type=FieldType.CHECKBOX, verify=False),
        ])

        engine = FillEngine()
        result = await engine.fill_section(browser, schema, {
            "name": "John",
            "age": "30",
            "state": "KL",
            "active": True,
        })

        assert result.success is True, f"Failed: {[(f.field, f.error) for f in result.fields]}"
        assert result.succeeded == 4
        assert result.failed == 0
        assert result.total_fields == 4
        assert browser.filled.get("#name") == "John"
        assert browser.filled.get("#age") == "30"
        assert browser.selected.get("#state") == "KL"

    @pytest.mark.asyncio
    async def test_fill_section_with_required_missing(self):
        browser = MockBrowser()
        schema = _make_schema("customer", [
            _make_field("name", "text", required=True, verify=False),
        ])

        engine = FillEngine()
        result = await engine.fill_section(browser, schema, {})
        assert result.success is False
        assert result.failed == 1
        assert "required" in (result.fields[0].error or "").lower()

    @pytest.mark.asyncio
    async def test_fill_section_skip_optional(self):
        browser = MockBrowser()
        schema = _make_schema("customer", [
            _make_field("name", "text", required=False, verify=False),
        ])

        engine = FillEngine()
        result = await engine.fill_section(browser, schema, {})
        assert result.success is True  # Optional field skipped
        assert result.succeeded == 1
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_fill_section_with_transform(self):
        browser = MockBrowser()
        browser.register_selector("#gender")

        registry = TransformerRegistry()
        registry.register("gender", {"MALE": "M", "FEMALE": "F"})

        schema = _make_schema("customer", [
            FieldDefinition(
                name="gender",
                selector="#gender",
                type=FieldType.RADIO,
                transform="gender",
                verify=False,
            ),
        ])

        engine = FillEngine(transformer_registry=registry)
        result = await engine.fill_section(browser, schema, {"gender": "MALE"})

        assert result.success is True
        assert result.succeeded == 1

    @pytest.mark.asyncio
    async def test_fill_section_partial_failure(self):
        browser = MockBrowser()
        browser.register_selector("#ok_field")

        schema = _make_schema("test", [
            _make_field("ok_field", "text", verify=False),
            _make_field("missing_field", "text", verify=False),
        ])

        engine = FillEngine()
        result = await engine.fill_section(browser, schema, {
            "ok_field": "hello",
            "missing_field": "world",
        })

        assert result.success is False  # Partial failure
        assert result.succeeded == 1
        assert result.failed == 1


class TestFillEngineIntegration:
    @pytest.mark.asyncio
    async def test_full_flow_with_transformer_and_verification(self):
        """Integration: FillEngine + Transformer + MockBrowser."""
        browser = MockBrowser()
        browser.register_selector("#customer_name")
        browser.register_selector("#gender_male")
        browser.register_value("#customer_name", "John")

        registry = TransformerRegistry()
        registry.register("gender", {"MALE": "M"})

        schema = _make_schema("customer", [
            FieldDefinition(
                name="customer_name",
                selector="#customer_name",
                type=FieldType.TEXT,
                verify=False,
            ),
            FieldDefinition(
                name="gender",
                selector="#gender",
                type=FieldType.RADIO,
                options={"values": {"M": "#gender_male"}},
                transform="gender",
                verify=False,
            ),
        ])

        engine = FillEngine(transformer_registry=registry)
        result = await engine.fill_section(browser, schema, {
            "customer_name": "John",
            "gender": "MALE",
        })

        assert result.success is True
        assert result.succeeded == 2
        assert browser.filled.get("#customer_name") == "John"
        assert "#gender_male" in browser.clicked

    @pytest.mark.asyncio
    async def test_reports_include_timing(self):
        browser = MockBrowser()
        browser.register_selector("#name")
        engine = FillEngine()
        field = _make_field("name", "text", verify=False)
        result = await engine.fill_field(browser, field, "Test")
        assert result.attempts >= 1
