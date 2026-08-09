"""Tests: Sprint B — Form Discovery (Models + Scanner).

All tests use MockEngine (no browser required).
"""

from __future__ import annotations

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ══════════════════════════════════════════════════════════════════
# 1. FormField / FieldOption / FieldDependency (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestFormFieldModels:
    """FormField, FieldOption, FieldDependency dataclasses."""

    def test_field_defaults(self):
        from src.quote.discovery.models import FormField
        f = FormField()
        assert f.key == ""
        assert f.field_type == "text"
        assert f.required is False

    def test_field_with_values(self):
        from src.quote.discovery.models import FormField
        f = FormField(
            key="proposer_name",
            label="Proposer Name",
            selector="input[name='propName']",
            field_type="text",
            required=True,
        )
        assert f.key == "proposer_name"
        assert f.required is True

    def test_field_to_dict(self):
        from src.quote.discovery.models import FormField
        f = FormField(
            key="email",
            label="Email",
            selector="#email",
            field_type="email",
            required=True,
        )
        d = f.to_dict()
        assert d["key"] == "email"
        assert d["field_type"] == "email"
        assert d["required"] is True

    def test_field_with_options(self):
        from src.quote.discovery.models import FormField, FieldOption
        f = FormField(
            key="occupation",
            label="Occupation",
            field_type="select",
            options=[
                FieldOption(value="office", label="Office Worker"),
                FieldOption(value="factory", label="Factory Worker"),
            ],
        )
        d = f.to_dict()
        assert len(d["options"]) == 2
        assert d["options"][0]["value"] == "office"

    def test_field_option(self):
        from src.quote.discovery.models import FieldOption
        o = FieldOption(value="fire", label="Fire Insurance", selected=True)
        assert o.value == "fire"
        assert o.selected is True

    def test_field_dependency(self):
        from src.quote.discovery.models import FieldDependency
        d = FieldDependency(
            field="business_type",
            equals="factory",
            show_fields=["machine_value", "hazard_type"],
        )
        assert d.field == "business_type"
        assert "machine_value" in d.show_fields

    def test_field_min_max(self):
        from src.quote.discovery.models import FormField
        f = FormField(key="age", min_value=18.0, max_value=100.0, pattern="[0-9]+")
        assert f.min_value == 18.0
        assert f.pattern == "[0-9]+"

    def test_field_section_and_order(self):
        from src.quote.discovery.models import FormField
        f = FormField(key="name", section="proposer", order=1)
        assert f.section == "proposer"
        assert f.order == 1


# ══════════════════════════════════════════════════════════════════
# 2. FormPage (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestFormPage:
    """FormPage — collection of fields within a wizard step."""

    def test_page_defaults(self):
        from src.quote.discovery.models import FormPage
        p = FormPage(name="proposer")
        assert p.name == "proposer"
        assert len(p.fields) == 0

    def test_page_get_field(self):
        from src.quote.discovery.models import FormPage, FormField
        p = FormPage(name="risk")
        p.fields.append(FormField(key="sum_insured"))
        p.fields.append(FormField(key="occupation"))
        assert p.get_field("sum_insured") is not None
        assert p.get_field("nonexistent") is None

    def test_page_list_field_keys(self):
        from src.quote.discovery.models import FormPage, FormField
        p = FormPage(name="form")
        p.fields.append(FormField(key="a"))
        p.fields.append(FormField(key="b"))
        assert p.list_field_keys() == ["a", "b"]

    def test_page_required_fields(self):
        from src.quote.discovery.models import FormPage, FormField
        p = FormPage(name="form")
        p.fields.append(FormField(key="opt", required=False))
        p.fields.append(FormField(key="req", required=True))
        reqs = p.required_fields()
        assert len(reqs) == 1
        assert reqs[0].key == "req"


# ══════════════════════════════════════════════════════════════════
# 3. FormSchema (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestFormSchema:
    """FormSchema — complete form structure."""

    def test_schema_defaults(self):
        from src.quote.discovery.models import FormSchema
        s = FormSchema(portal="great_eastern", quote_channel="IFE")
        assert s.portal == "great_eastern"
        assert s.quote_channel == "IFE"
        assert s.total_fields() == 0

    def test_schema_get_page(self):
        from src.quote.discovery.models import FormSchema, FormPage
        s = FormSchema()
        s.pages.append(FormPage(name="page1"))
        s.pages.append(FormPage(name="page2"))
        assert s.get_page("page1") is not None
        assert s.get_page("nonexistent") is None

    def test_schema_all_fields(self):
        from src.quote.discovery.models import FormSchema, FormPage, FormField
        s = FormSchema()
        p1 = FormPage(name="p1")
        p1.fields.append(FormField(key="a"))
        p1.fields.append(FormField(key="b"))
        p2 = FormPage(name="p2")
        p2.fields.append(FormField(key="c"))
        s.pages.extend([p1, p2])
        assert len(s.all_fields()) == 3

    def test_schema_required_fields(self):
        from src.quote.discovery.models import FormSchema, FormPage, FormField
        s = FormSchema()
        p = FormPage(name="form")
        p.fields.append(FormField(key="req1", required=True))
        p.fields.append(FormField(key="opt", required=False))
        p.fields.append(FormField(key="req2", required=True))
        s.pages.append(p)
        reqs = s.required_fields()
        assert len(reqs) == 2

    def test_schema_to_profile_yaml_structure(self):
        from src.quote.discovery.models import FormSchema, FormPage, FormField, FieldOption
        s = FormSchema(
            portal="great_eastern",
            quote_channel="IFE",
            version="1.0",
        )
        p = FormPage(name="proposer", url_pattern="/quote/proposer")
        p.fields.append(FormField(
            key="name",
            label="Name",
            selector="#name",
            field_type="text",
            required=True,
        ))
        p.fields.append(FormField(
            key="occupation",
            label="Occupation",
            field_type="select",
            options=[
                FieldOption(value="office", label="Office"),
            ],
        ))
        p.actions.append({"key": "next", "selector": "#nextBtn", "type": "button"})
        s.pages.append(p)

        y = s.to_profile_yaml()
        assert y["portal"] == "great_eastern"
        assert y["quote_channel"] == "IFE"
        assert "proposer" in y["pages"]
        assert y["pages"]["proposer"]["elements"]["name"]["selector"] == "#name"
        assert y["pages"]["proposer"]["elements"]["name"]["required"] is True
        assert len(y["pages"]["proposer"]["actions"]) == 1


# ══════════════════════════════════════════════════════════════════
# 4. FormScanner (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestFormScanner:
    """FormScanner with MockEngine."""

    @pytest.mark.asyncio
    async def test_scanner_create(self):
        from src.quote.discovery.scanner import FormScanner
        from src.browser.foundation import MockEngine
        scanner = FormScanner(MockEngine())
        assert scanner is not None
        assert len(scanner.scan_history) == 0

    @pytest.mark.asyncio
    async def test_scan_current_page_returns_none_without_engine(self):
        from src.quote.discovery.scanner import FormScanner
        scanner = FormScanner(None)  # type: ignore
        schema = await scanner.scan_current_page()
        assert schema is None

    @pytest.mark.asyncio
    async def test_scan_current_page_with_mock_data(self):
        from src.quote.discovery.scanner import FormScanner
        from src.browser.foundation import MockEngine
        e = MockEngine()

        # Mock evaluate to return scan results
        async def mock_evaluate(script):
            if "SCAN_FORM_JS" in script or "querySelectorAll" in script:
                return {
                    "fields": [
                        {
                            "key": "username",
                            "tag": "input",
                            "type": "text",
                            "label": "Username",
                            "selector": "#username",
                            "candidates": {"#username": 95},
                            "required": True,
                            "placeholder": "",
                            "options": [],
                            "multiple": False,
                            "minLength": None,
                            "maxLength": None,
                            "min": None,
                            "max": None,
                            "pattern": "",
                        },
                        {
                            "key": "password",
                            "tag": "input",
                            "type": "password",
                            "label": "Password",
                            "selector": "#password",
                            "candidates": {"#password": 95},
                            "required": True,
                            "placeholder": "",
                            "options": [],
                            "multiple": False,
                            "minLength": None,
                            "maxLength": None,
                            "min": None,
                            "max": None,
                            "pattern": "",
                        },
                        {
                            "key": "occupation",
                            "tag": "select",
                            "type": "select-one",
                            "label": "Occupation",
                            "selector": "#occupation",
                            "candidates": {"#occupation": 82},
                            "required": False,
                            "placeholder": "",
                            "options": [
                                {"value": "office", "label": "Office", "selected": True},
                                {"value": "factory", "label": "Factory", "selected": False},
                            ],
                            "multiple": False,
                        },
                    ],
                    "actions": [
                        {"key": "next", "text": "Next", "selector": "#nextBtn", "type": "button"},
                    ],
                    "url": "https://example.com/quote",
                    "title": "Quote Form",
                }
            return None

        e.evaluate = mock_evaluate
        scanner = FormScanner(e)
        schema = await scanner.scan_current_page(
            page_name="proposer",
            portal="great_eastern",
            channel="IFE",
        )

        assert schema is not None
        assert schema.portal == "great_eastern"
        assert schema.quote_channel == "IFE"
        assert schema.total_fields() == 3
        assert len(schema.pages) == 1

        page = schema.get_page("proposer")
        assert page is not None
        assert page.get_field("username") is not None
        assert page.get_field("username").required is True
        assert page.get_field("password").field_type == "password"
        assert len(page.actions) == 1

        # Check options
        occ = page.get_field("occupation")
        assert occ is not None
        assert len(occ.options) == 2
        assert occ.options[0].value == "office"

    @pytest.mark.asyncio
    async def test_scan_history(self):
        from src.quote.discovery.scanner import FormScanner
        from src.browser.foundation import MockEngine
        e = MockEngine()

        async def mock_eval(script):
            return {"fields": [], "actions": [], "url": "", "title": ""}

        e.evaluate = mock_eval
        scanner = FormScanner(e)
        await scanner.scan_current_page(page_name="page1")
        await scanner.scan_current_page(page_name="page2")
        assert len(scanner.scan_history) == 2

    @pytest.mark.asyncio
    async def test_merge_schemas(self):
        from src.quote.discovery.scanner import FormScanner
        from src.quote.discovery.models import FormSchema, FormPage, FormField
        from src.browser.foundation import MockEngine

        scanner = FormScanner(MockEngine())

        s1 = FormSchema(portal="ge", quote_channel="IFE")
        s1.pages.append(FormPage(name="page1", fields=[FormField(key="a")]))

        s2 = FormSchema(portal="ge", quote_channel="IFE")
        s2.pages.append(FormPage(name="page2", fields=[FormField(key="b")]))

        merged = scanner.merge_schemas([s1, s2])
        assert merged is not None
        assert merged.total_fields() == 2
        assert merged.get_page("page1") is not None
        assert merged.get_page("page2") is not None

    @pytest.mark.asyncio
    async def test_safe_int_and_float(self):
        from src.quote.discovery.scanner import FormScanner
        from src.browser.foundation import MockEngine

        scanner = FormScanner(MockEngine())
        assert scanner._safe_int("5") == 5
        assert scanner._safe_int(None) is None
        assert scanner._safe_int("abc") is None
        assert scanner._safe_float("3.14") == 3.14
        assert scanner._safe_float(None) is None
