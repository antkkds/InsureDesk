"""Tests for Fill Engine — Schema, Exceptions, Results."""
from __future__ import annotations

import pytest
from src.fill.schema import (
    FieldDefinition,
    FieldType,
    FillSchema,
    fill_schema_from_dict,
)
from src.fill.exceptions import (
    FillError,
    FieldNotFoundError,
    UnsupportedFieldTypeError,
    FillTimeoutError,
    FillVerificationError,
    TransformationError,
    RequiredFieldMissingError,
    UploadFailedError,
)
from src.fill.result import FieldResult, FillResult


class TestFieldDefinition:
    def test_defaults(self):
        fd = FieldDefinition(name="test")
        assert fd.name == "test"
        assert fd.type == FieldType.TEXT
        assert fd.required is False
        assert fd.verify is True
        assert fd.retry == 2
        assert fd.clear_first is True
        assert fd.timeout == 5000
        assert fd.transform is None
        assert fd.format is None

    def test_with_all_fields(self):
        fd = FieldDefinition(
            name="full",
            selector="#test",
            type=FieldType.SELECT,
            required=True,
            verify=True,
            retry=3,
            clear_first=False,
            timeout=10000,
            transform="gender",
            format="%d/%m/%Y",
            options={"mode": "label"},
            max_length=100,
        )
        assert fd.name == "full"
        assert fd.selector == "#test"
        assert fd.type == FieldType.SELECT
        assert fd.max_length == 100


class TestFieldType:
    def test_case_insensitive(self):
        assert FieldType("TEXT") == FieldType.TEXT
        assert FieldType("Select") == FieldType.SELECT
        assert FieldType("CHECKBOX") == FieldType.CHECKBOX

    def test_invalid_type(self):
        with pytest.raises(ValueError):
            FieldType("unknown_type")


class TestFillSchemaFromDict:
    def test_simple_schema(self):
        data = {
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
        }
        schema = fill_schema_from_dict("customer", data)
        assert schema.name == "customer"
        assert len(schema.fields) == 2
        assert schema.fields["customer_name"].selector == "#name"
        assert schema.fields["customer_name"].required is True
        assert schema.fields["gender"].type == FieldType.RADIO
        assert schema.fields["gender"].transform == "gender"

    def test_empty_dict(self):
        schema = fill_schema_from_dict("empty", {})
        assert schema.name == "empty"
        assert len(schema.fields) == 0


class TestExceptions:
    def test_fill_error_default(self):
        e = FillError()
        assert str(e) == ""

    def test_fill_error_with_context(self):
        e = FillError(
            message="Something broke",
            field="test_field",
            selector="#test",
            section="customer",
        )
        assert "Something broke" in str(e)
        assert "field=test_field" in str(e)
        assert "selector=#test" in str(e)
        assert "section=customer" in str(e)

    def test_field_not_found(self):
        e = FieldNotFoundError(field="name", selector="#name", section="customer")
        assert isinstance(e, FillError)

    def test_unsupported_type(self):
        e = UnsupportedFieldTypeError(field_type="foo", field="test")
        assert "foo" in str(e)

    def test_verification_error(self):
        e = FillVerificationError(field="test", selector="#t")
        assert isinstance(e, FillError)

    def test_required_field_missing(self):
        e = RequiredFieldMissingError(field="required_field")
        assert isinstance(e, FillError)

    def test_upload_failed(self):
        e = UploadFailedError(field="file", selector="#upload")
        assert isinstance(e, FillError)

    def test_transformation_error(self):
        e = TransformationError(message="No mapping", field="gender")
        assert "No mapping" in str(e)

    def test_timeout_error(self):
        e = FillTimeoutError(field="test", selector="#t")
        assert isinstance(e, FillError)


class TestResult:
    def test_field_result_defaults(self):
        r = FieldResult(field="test")
        assert r.field == "test"
        assert r.success is False
        assert r.attempts == 0
        assert r.duration_ms == 0
        assert r.message is None
        assert r.error is None

    def test_fill_result_summary(self):
        r = FillResult(
            section="customer",
            total_fields=5,
            succeeded=4,
            failed=1,
            duration_ms=1200,
        )
        summary = r.summary
        assert "customer" in summary
        assert "4/5" in summary
        assert "1 failed" in summary
        assert "1200ms" in summary
