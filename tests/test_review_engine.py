"""Tests for Portal Review Engine.

Covers:
- Data models (ReviewContext, ReviewResult, Change, ReviewIssue, Suggestion)
- DiffEngine (before/after comparison, nested dicts, change classification)
- ReviewCollector (data assembly from execution + validation)
- SuggestionEngine (auto-fix suggestions, value range checks, optional fields)
- ReviewFormatter (Bridge Protocol, human-readable, Telegram)
- ReviewEngine (full review pipeline, status determination, summary)
- Integration (with Execution + Validation engines)
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.portal.review.models import (
    Change,
    ChangeType,
    ReviewContext,
    ReviewIssue,
    ReviewResult,
    ReviewStatus,
    Suggestion,
)
from src.portal.review.engine import ReviewEngine
from src.portal.review.diff import DiffEngine
from src.portal.review.collector import ReviewCollector
from src.portal.review.suggestions import SuggestionEngine
from src.portal.review.formatter import ReviewFormatter
from src.portal.review.exceptions import ReviewError
from src.portal.validation.models import ValidationResult, ValidationError


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def diff_engine() -> DiffEngine:
    return DiffEngine()


@pytest.fixture
def review_engine() -> ReviewEngine:
    return ReviewEngine()


@pytest.fixture
def sample_before() -> dict:
    return {
        "customer": {"name": "John Tan", "age": 35, "occupation": "Engineer"},
        "quote": {"premium": 500.0},
    }


@pytest.fixture
def sample_after() -> dict:
    return {
        "customer": {"name": "John Tan", "age": 35, "occupation": "Software Engineer"},
        "quote": {"premium": 523.0, "quote_no": "GE12345"},
    }


# =============================================================================
# Data Models
# =============================================================================


class TestReviewStatus:
    def test_values(self):
        assert ReviewStatus.APPROVED.value == "approved"
        assert ReviewStatus.FAILED.value == "failed"
        assert ReviewStatus.NEEDS_REVIEW.value == "needs_review"


class TestChangeType:
    def test_values(self):
        assert ChangeType.CREATED.value == "created"
        assert ChangeType.NORMALIZED.value == "normalized"
        assert ChangeType.AUTO_FIXED.value == "auto_fixed"


class TestChange:
    def test_to_dict(self):
        c = Change(field="age", before=35, after=36, change_type="updated")
        d = c.to_dict()
        assert d["field"] == "age"
        assert d["before"] == 35
        assert d["after"] == 36


class TestReviewIssue:
    def test_to_dict(self):
        issue = ReviewIssue(
            rule_id="age_check", message="Age exceeds limit",
            severity="error",
        )
        d = issue.to_dict()
        assert d["severity"] == "error"
        assert d["suggested_action"] is None


class TestSuggestion:
    def test_to_dict(self):
        s = Suggestion(
            field="dob", message="Normalize date",
            current_value="1990/01/01", suggested_value="1990-01-01",
            auto_fixable=True,
        )
        d = s.to_dict()
        assert d["auto_fixable"] is True
        assert d["requires_approval"] is True


class TestReviewContext:
    def test_has_errors_false(self):
        ctx = ReviewContext(portal="ge", action="create_quote")
        assert ctx.has_errors is False

    def test_has_errors_with_execution_errors(self):
        ctx = ReviewContext(portal="ge", action="create_quote",
                             execution_errors=["Timeout"])
        assert ctx.has_errors is True

    def test_has_errors_with_validation_failure(self):
        val_result = ValidationResult(passed=False)
        val_result.add_error(ValidationError(rule_id="r1", message="fail"))
        ctx = ReviewContext(portal="ge", action="create_quote",
                             validation_result=val_result)
        assert ctx.has_errors is True


class TestReviewResult:
    def test_defaults(self):
        r = ReviewResult()
        assert r.status == "approved"
        assert r.changes == []
        assert r.has_changes is False

    def test_add_error_changes_status(self):
        r = ReviewResult()
        r.add_error(ReviewIssue(rule_id="r1", message="fail", severity="error"))
        assert r.status == "failed"
        assert r.requires_human_review is True

    def test_add_warning_changes_status(self):
        r = ReviewResult()
        r.add_warning(ReviewIssue(rule_id="r1", message="warn"))
        assert r.status == "warning"

    def test_to_dict(self):
        r = ReviewResult(execution_id="exec_1")
        r.add_change(Change(field="age", before=35, after=36))
        d = r.to_dict()
        assert d["execution_id"] == "exec_1"
        assert d["has_changes"] is True
        assert "stats" not in d  # No stats in to_dict


# =============================================================================
# DiffEngine
# =============================================================================


class TestDiffEngine:
    def test_no_changes(self, diff_engine: DiffEngine):
        data = {"a": 1, "b": 2}
        changes = diff_engine.compute_diff(data, data)
        assert len(changes) == 0

    def test_field_created(self, diff_engine: DiffEngine):
        before = {"a": 1}
        after = {"a": 1, "b": 2}
        changes = diff_engine.compute_diff(before, after)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.CREATED.value
        assert changes[0].field == "b"

    def test_field_removed(self, diff_engine: DiffEngine):
        before = {"a": 1, "b": 2}
        after = {"a": 1}
        changes = diff_engine.compute_diff(before, after)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.REMOVED.value

    def test_field_updated(self, diff_engine: DiffEngine):
        before = {"a": 1}
        after = {"a": 2}
        changes = diff_engine.compute_diff(before, after)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.UPDATED.value

    def test_field_normalized(self, diff_engine: DiffEngine):
        """Same value, different case/whitespace = NORMALIZED."""
        before = {"name": "John Tan"}
        after = {"name": "john tan"}
        changes = diff_engine.compute_diff(before, after)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.NORMALIZED.value

    def test_nested_dict_diff(self, diff_engine: DiffEngine):
        before = {"customer": {"name": "John", "age": 35}}
        after = {"customer": {"name": "John", "age": 36}}
        changes = diff_engine.compute_diff(before, after)
        assert len(changes) == 1
        assert changes[0].field == "customer.age"

    def test_nested_dict_created(self, diff_engine: DiffEngine):
        before = {"customer": {"name": "John"}}
        after = {"customer": {"name": "John", "email": "j@b.com"}}
        changes = diff_engine.compute_diff(before, after)
        assert len(changes) == 1
        assert changes[0].field == "customer.email"

    def test_has_changes(self, diff_engine: DiffEngine):
        assert diff_engine.has_changes({"a": 1}, {"a": 2}) is True
        assert diff_engine.has_changes({"a": 1}, {"a": 1}) is False

    def test_get_changed_fields(self, diff_engine: DiffEngine):
        fields = diff_engine.get_changed_fields(
            {"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4}
        )
        assert "b" in fields
        assert "c" in fields

    def test_ignores_internal_fields(self, diff_engine: DiffEngine):
        before = {"session_id": "old", "data": "keep"}
        after = {"session_id": "new", "data": "keep"}
        changes = diff_engine.compute_diff(before, after)
        # session_id should be ignored
        assert len(changes) == 0

    def test_mixed_dict_and_scalar(self, diff_engine: DiffEngine):
        """One side dict, other side scalar — treat as update."""
        before = {"field": {"nested": "value"}}
        after = {"field": "scalar"}
        changes = diff_engine.compute_diff(before, after)
        assert len(changes) == 1
        assert changes[0].field == "field"

    def test_empty_dicts(self, diff_engine: DiffEngine):
        changes = diff_engine.compute_diff({}, {})
        assert len(changes) == 0


# =============================================================================
# ReviewCollector
# =============================================================================


class TestReviewCollector:
    def test_collect_basic(self):
        collector = ReviewCollector()
        context = collector.collect(
            portal="great_eastern",
            action="create_quote",
            before_data={"a": 1},
            after_data={"a": 2},
        )
        assert context.portal == "great_eastern"
        assert context.before_data["a"] == 1
        assert context.after_data["a"] == 2

    def test_collect_with_validation(self):
        collector = ReviewCollector()
        val_result = ValidationResult(passed=False)
        val_result.add_error(ValidationError(rule_id="r1", message="fail"))
        context = collector.collect(
            portal="ge", action="quote",
            validation_result=val_result,
        )
        assert context.has_validation is True
        assert context.has_errors is True

    def test_collect_with_execution_errors(self):
        collector = ReviewCollector()
        from src.portal.execution.models import ExecutionResult
        exec_result = ExecutionResult(
            success=False, errors=["Step failed: timeout"]
        )
        context = collector.collect(
            portal="ge", action="quote",
            execution_result=exec_result,
        )
        assert "timeout" in context.execution_errors[0]

    def test_collect_defaults(self):
        collector = ReviewCollector()
        context = collector.collect(portal="ge", action="quote")
        assert context.before_data == {}
        assert context.after_data == {}
        assert context.validation_result is None


# =============================================================================
# SuggestionEngine
# =============================================================================


class TestSuggestionEngine:
    def test_date_format_suggestion(self):
        engine = SuggestionEngine()
        ctx = ReviewContext(
            portal="ge", action="quote",
            after_data={"dob": "1990/01/01"},
        )
        suggestions = engine.generate(ctx, [])
        assert len(suggestions) >= 1
        assert any(s.field == "dob" for s in suggestions)

    def test_high_premium_suggestion(self):
        engine = SuggestionEngine()
        ctx = ReviewContext(
            portal="ge", action="quote",
            after_data={"premium": 9500},
        )
        suggestions = engine.generate(ctx, [])
        assert any("Premium is high" in s.message for s in suggestions)

    def test_missing_optional_fields(self):
        engine = SuggestionEngine()
        ctx = ReviewContext(portal="ge", action="quote")
        suggestions = engine.generate(ctx, [])
        assert any(s.field == "email" for s in suggestions)

    def test_custom_rule(self):
        engine = SuggestionEngine()

        def custom_rule(ctx, changes):
            return Suggestion(
                field="test", message="Custom suggestion",
                confidence=1.0,
            )

        engine.add_custom_rule(custom_rule)
        suggestions = engine.generate(ReviewContext(portal="ge", action="q"), [])
        assert any("Custom" in s.message for s in suggestions)


# =============================================================================
# ReviewFormatter
# =============================================================================


class TestReviewFormatter:
    def test_bridge_protocol_format(self):
        formatter = ReviewFormatter()
        result = ReviewResult(execution_id="exec_1")
        result.add_change(Change(field="age", before=35, after=36))
        payload = formatter.to_bridge_protocol(result)
        assert payload["type"] == "review"
        assert payload["stats"]["change_count"] == 1

    def test_human_readable_approved(self):
        formatter = ReviewFormatter()
        result = ReviewResult(execution_id="exec_1")
        text = formatter.to_human_readable(result)
        assert "APPROVED" in text

    def test_human_readable_with_changes(self):
        formatter = ReviewFormatter()
        result = ReviewResult(execution_id="exec_1")
        result.add_change(Change(
            field="occupation", before="Engineer", after="Software Engineer",
        ))
        text = formatter.to_human_readable(result)
        assert "occupation" in text
        assert "Engineer" in text
        assert "Software Engineer" in text

    def test_human_readable_with_errors(self):
        formatter = ReviewFormatter()
        result = ReviewResult()
        result.add_error(ReviewIssue(
            rule_id="r1", message="Age exceeds limit", severity="error",
        ))
        text = formatter.to_human_readable(result)
        assert "FAILED" in text or "Error" in text

    def test_telegram_format(self):
        formatter = ReviewFormatter()
        result = ReviewResult(execution_id="exec_1")
        result.add_change(Change(field="premium", before=500, after=523))
        text = formatter.to_telegram(result)
        assert "APPROVED" in text or "✅" in text
        assert "change" in text.lower()


# =============================================================================
# ReviewEngine
# =============================================================================


class TestReviewEngine:
    def test_review_no_changes(self, review_engine: ReviewEngine):
        result = review_engine.review_changes({"a": 1}, {"a": 1})
        assert result.status == "approved"
        assert result.has_changes is False

    def test_review_with_changes(self, review_engine: ReviewEngine):
        result = review_engine.review_changes(
            {"name": "John"}, {"name": "John Tan"}
        )
        assert result.has_changes is True
        assert len(result.changes) == 1

    def test_review_with_validation(self, review_engine: ReviewEngine):
        val_result = ValidationResult(passed=False)
        val_result.add_error(ValidationError(
            rule_id="age", field="age", message="Too young",
        ))
        context = ReviewContext(
            portal="ge", action="quote",
            validation_result=val_result,
        )
        result = review_engine.review(context)
        assert result.status == "failed"
        assert result.has_issues is True

    def test_review_with_warnings(self, review_engine: ReviewEngine):
        val_result = ValidationResult(passed=True)
        val_result.add_warning(type('W', (), {
            "rule_id": "occ", "message": "Check occupation", "field": "occ",
            "category": "business",
        })())
        # Manually add a warning
        context = ReviewContext(
            portal="ge", action="quote",
            validation_result=val_result,
        )
        result = review_engine.review(context)
        assert result.status == "warning"

    def test_review_with_high_premium_suggestion(
        self, review_engine: ReviewEngine
    ):
        context = ReviewContext(
            portal="ge", action="quote",
            after_data={"premium": 9500},
        )
        result = review_engine.review(context)
        assert len(result.suggestions) >= 1

    def test_summary_generated(self, review_engine: ReviewEngine):
        result = review_engine.review_changes({"a": 1}, {"a": 2})
        assert result.summary != ""
        assert "modified" in result.summary

    def test_full_review_pipeline(self, review_engine: ReviewEngine):
        """End-to-end review with changes, validation, and suggestions."""
        context = ReviewContext(
            portal="great_eastern",
            action="create_quote",
            before_data={
                "customer": {"occupation": "Engineer"},
                "quote": {"premium": 500},
            },
            after_data={
                "customer": {"occupation": "Software Engineer"},
                "quote": {"premium": 523, "quote_no": "GE123"},
            },
        )
        result = review_engine.review(context)
        assert result.has_changes
        assert result.status == "approved"
        assert result.summary != ""

    def test_bridge_protocol_output(self, review_engine: ReviewEngine):
        """Verify ReviewEngine output is Bridge Protocol ready."""
        context = ReviewContext(
            portal="ge", action="quote",
            before_data={"premium": 500},
            after_data={"premium": 523},
        )
        result = review_engine.review(context)
        payload = review_engine.format(result)
        assert payload["type"] == "review"
        assert "changes" in payload
        assert "status" in payload
        assert "stats" in payload


# =============================================================================
# Integration — Execution + Validation + Review
# =============================================================================


class TestFullIntegration:
    def test_execution_validation_review_pipeline(
        self, review_engine: ReviewEngine
    ):
        """Simulate full pipeline: execute → validate → review."""
        # Step 1: Simulate execution (before → after)
        before_data = {
            "customer": {"name": "", "age": 17, "occupation": "Unknown"},
            "quote": {"premium": 0},
        }
        after_data = {
            "customer": {"name": "John Tan", "age": 17, "occupation": "Engineer"},
            "quote": {"premium": 523, "quote_no": "GE123"},
        }

        # Step 2: Simulate validation
        val_result = ValidationResult(passed=False)
        val_result.add_error(ValidationError(
            rule_id="age_check", field="age",
            message="Age must be 18-65", severity="error",
        ))
        val_result.add_warning(type('W', (), {
            "rule_id": "occ", "message": "Occupation updated",
            "field": "occupation", "category": "business",
        })())

        # Step 3: Review
        context = ReviewContext(
            portal="great_eastern",
            action="create_quote",
            before_data=before_data,
            after_data=after_data,
            validation_result=val_result,
        )
        result = review_engine.review(context)

        # Step 4: Assertions
        assert result.has_changes is True
        assert result.has_issues is True
        assert result.status in ("failed", "warning")

        # Bridge Protocol output
        payload = review_engine.format(result)
        assert payload["type"] == "review"
        assert len(payload["errors"]) >= 1
        assert len(payload["changes"]) >= 1
