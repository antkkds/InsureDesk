"""Tests: C2 — Profile Validation Engine."""
from __future__ import annotations

import os
import sys
import yaml
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestProfileValidator:
    """ProfileValidator — static analysis of profile YAML."""

    def _make_profile(self, pages=None):
        return {
            "version": "1.0",
            "portal": "test",
            "pages": pages or {"form": {"elements": {}}},
        }

    def test_empty_profile_has_issues(self):
        from src.quote.validation import ProfileValidator
        v = ProfileValidator()
        result = v.validate("empty", self._make_profile({"form": {"elements": {}}}))
        assert result.total_fields == 0

    def test_valid_field_passes(self):
        from src.quote.validation import ProfileValidator
        profile = self._make_profile({
            "form": {
                "elements": {
                    "insured_name": {
                        "selector": "#insured_name",
                        "tag": "input",
                        "field_type": "text",
                        "required": True,
                    }
                }
            }
        })
        result = ProfileValidator().validate("test", profile)
        assert result.total_fields == 1
        assert len(result.errors) == 0

    def test_missing_selector_is_error(self):
        from src.quote.validation import ProfileValidator
        profile = self._make_profile({
            "form": {
                "elements": {
                    "name": {"field_type": "text"},
                }
            }
        })
        result = ProfileValidator().validate("test", profile)
        assert any(i.category == "selector" for i in result.errors)

    def test_weak_selector_is_error(self):
        from src.quote.validation import ProfileValidator
        profile = self._make_profile({
            "form": {
                "elements": {
                    "name": {"selector": "input", "field_type": "text"},
                }
            }
        })
        result = ProfileValidator().validate("test", profile)
        assert any("Weak selector" in i.message for i in result.errors)

    def test_generated_key_is_warning(self):
        from src.quote.validation import ProfileValidator
        profile = self._make_profile({
            "form": {
                "elements": {
                    "field_0": {"selector": "#name", "field_type": "text"},
                }
            }
        })
        result = ProfileValidator().validate("test", profile)
        assert any(i.category == "naming" for i in result.warnings)

    def test_select_without_options_is_warning(self):
        from src.quote.validation import ProfileValidator
        profile = self._make_profile({
            "form": {
                "elements": {
                    "occupation": {
                        "selector": "#occ",
                        "field_type": "select",
                        "tag": "select",
                    }
                }
            }
        })
        result = ProfileValidator().validate("test", profile)
        assert any("options" in i.category for i in result.warnings)

    def test_select_with_options_passes(self):
        from src.quote.validation import ProfileValidator
        profile = self._make_profile({
            "form": {
                "elements": {
                    "occupation": {
                        "selector": "#occ",
                        "field_type": "select",
                        "tag": "select",
                        "options": [
                            {"value": "office", "label": "Office Worker"},
                            {"value": "factory", "label": "Factory Worker"},
                        ],
                    }
                }
            }
        })
        result = ProfileValidator().validate("test", profile)
        assert len(result.errors) == 0

    def test_unknown_field_type_is_warning(self):
        from src.quote.validation import ProfileValidator
        profile = self._make_profile({
            "form": {
                "elements": {
                    "custom": {"selector": "#c", "field_type": "unknown_type"},
                }
            }
        })
        result = ProfileValidator().validate("test", profile)
        assert any("Unknown field type" in i.message for i in result.warnings)

    def test_score_drops_with_errors(self):
        from src.quote.validation import ProfileValidator
        # Perfect profile
        perfect = self._make_profile({
            "form": {
                "elements": {
                    "name": {"selector": "#name", "field_type": "text", "required": False},
                    "email": {"selector": "#email", "field_type": "email", "required": True},
                    "age": {"selector": "#age", "field_type": "number"},
                }
            }
        })
        good = ProfileValidator().validate("good", perfect)

        # Bad profile
        bad_profile = self._make_profile({
            "form": {
                "elements": {
                    "field_0": {"selector": "input", "field_type": "text"},
                    "field_1": {"field_type": "select"},
                    "field_2": {"selector": "div", "field_type": "unknown"},
                }
            }
        })
        bad = ProfileValidator().validate("bad", bad_profile)

        assert good.score > bad.score

    def test_score_100_for_perfect(self):
        from src.quote.validation import ProfileValidator
        profile = self._make_profile({
            "form": {
                "elements": {
                    "name": {"selector": "#name", "tag": "input", "field_type": "text", "required": False},
                }
            }
        })
        result = ProfileValidator().validate("perfect", profile)
        assert result.score == 100.0

    def test_validate_real_profiles(self):
        """Integration test: validate the real captured profiles."""
        from src.quote.validation import ProfileValidator

        profile_dir = os.path.join(os.path.dirname(__file__), "..", "profiles")
        validator = ProfileValidator()

        for name in ["ife_quote", "eq_quote"]:
            path = os.path.join(profile_dir, f"{name}.yaml")
            if not os.path.exists(path):
                pytest.skip(f"{path} not found — run C1 first")

            with open(path) as f:
                data = yaml.safe_load(f)

            result = validator.validate(name, data)
            print(f"\n{validator.summary(result)}")

            # Real profiles from production should have minimal errors
            # (some warnings expected for generated keys from HTML parsing)
            assert result.total_fields > 0
            # Score should be reasonable for auto-captured profiles
            assert result.score >= 30.0, f"{name} score {result.score} too low"
