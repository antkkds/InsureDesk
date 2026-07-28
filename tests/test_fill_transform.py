"""Tests for Fill Engine — Transformer, Mapper, Verifier."""
from __future__ import annotations

import pytest
from dataclasses import dataclass

from src.fill.transformer import TransformerRegistry
from src.fill.mapper import FieldMapper
from src.fill.verifier import Verifier
from src.fill.exceptions import TransformationError
from tests.mock_browser import MockBrowser


class TestTransformerRegistry:
    def test_empty_registry(self):
        r = TransformerRegistry()
        assert r.has("gender") is False

    def test_register_dict_mapping(self):
        r = TransformerRegistry()
        r.register("gender", {"MALE": "M", "FEMALE": "F"})
        assert r.has("gender")
        assert r.transform("gender", "MALE") == "M"
        assert r.transform("gender", "FEMALE") == "F"

    def test_register_from_yaml(self):
        r = TransformerRegistry()
        r.register_from_yaml({"gender": {"MALE": "M", "FEMALE": "F"}})
        assert r.transform("gender", "MALE") == "M"

    def test_builtin_uppercase(self):
        r = TransformerRegistry()
        assert r.transform("uppercase", "hello") == "HELLO"

    def test_builtin_lowercase(self):
        r = TransformerRegistry()
        assert r.transform("lowercase", "HELLO") == "hello"

    def test_builtin_trim(self):
        r = TransformerRegistry()
        assert r.transform("trim", "  hello  ") == "hello"

    def test_missing_mapping_raises(self):
        r = TransformerRegistry()
        r.register("gender", {"MALE": "M"})
        with pytest.raises(TransformationError):
            r.transform("gender", "UNKNOWN")

    def test_unknown_transformer_raises(self):
        r = TransformerRegistry()
        with pytest.raises(TransformationError):
            r.transform("nonexistent", "value")


class TestFieldMapper:
    def test_map_dataclass(self):
        @dataclass
        class Customer:
            full_name: str
            gender: str

        mapper = FieldMapper()
        customer = Customer(full_name="John", gender="MALE")
        result = mapper.map(customer, {
            "customer_name": "full_name",
            "gender": "gender",
        })
        assert result == {"customer_name": "John", "gender": "MALE"}

    def test_map_with_schema(self):
        @dataclass
        class Customer:
            customer_name: str
            gender: str

        mapper = FieldMapper()
        customer = Customer(customer_name="John", gender="MALE")
        schema_fields = {"customer_name": {}, "gender": {}}
        result = mapper.map_with_schema(customer, schema_fields)
        assert result == {"customer_name": "John", "gender": "MALE"}

    def test_map_from_dict(self):
        mapper = FieldMapper()
        data = {"name": "John", "age": 30}
        result = mapper.map(data, {"customer_name": "name", "customer_age": "age"})
        assert result == {"customer_name": "John", "customer_age": 30}

    def test_skips_missing_attrs(self):
        @dataclass
        class Customer:
            name: str

        mapper = FieldMapper()
        customer = Customer(name="John")
        result = mapper.map(customer, {"name": "name", "missing_field": "nonexistent"})
        assert result == {"name": "John"}
        assert "missing_field" not in result


class TestVerifier:
    @pytest.mark.asyncio
    async def test_verify_match(self):
        browser = MockBrowser()
        browser.register_selector("#name")
        browser.register_value("#name", "John")

        verifier = Verifier()
        result = await verifier.verify(
            reader=lambda s: browser.get_value(s),
            selector="#name",
            expected="John",
            field_name="name",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_match_tolerant(self):
        browser = MockBrowser()
        browser.register_selector("#name")
        browser.register_value("#name", "  JOHN  ")

        verifier = Verifier()
        assert verifier.verify_text("  JOHN  ", "john") is True

    @pytest.mark.asyncio
    async def test_verify_mismatch_raises(self):
        browser = MockBrowser()
        browser.register_selector("#name")
        browser.register_value("#name", "Wrong")

        verifier = Verifier()
        from src.fill.exceptions import FillVerificationError
        with pytest.raises(FillVerificationError):
            await verifier.verify(
                reader=lambda s: browser.get_value(s),
                selector="#name",
                expected="Expected",
                field_name="name",
                timeout=500,
            )

    def test_verify_text_exact(self):
        assert Verifier.verify_text("hello", "hello") is True
        assert Verifier.verify_text("hello", "HELLO", tolerant=True) is True
        assert Verifier.verify_text("hello", "world") is False

    def test_verify_boolean_matching(self):
        v = Verifier()
        assert v._match("true", True) is True
        assert v._match("false", False) is True
        assert v._match("checked", True) is True
        assert v._match("", False) is True
