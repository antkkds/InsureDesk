"""Portal Review Engine — ReviewEngine.

The central orchestrator for the review process.
Transforms execution + validation outputs into a structured,
human/AI-readable review with changes, issues, and suggestions.

Architecture:
    ReviewEngine.review(context)
        │
        ├── DiffEngine.compute_diff(before, after) → changes
        ├── ValidationEngine results → issues
        ├── SuggestionEngine.generate() → suggestions
        │
        └── ReviewResult (structured output)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.portal.review.models import (
    Change,
    ReviewContext,
    ReviewIssue,
    ReviewResult,
    ReviewStatus,
    Suggestion,
)
from src.portal.review.diff import DiffEngine
from src.portal.review.suggestions import SuggestionEngine
from src.portal.review.formatter import ReviewFormatter

logger = logging.getLogger("insuredesk.review.engine")


class ReviewEngine:
    """Produces structured reviews of portal execution results.

    Usage:
        engine = ReviewEngine()
        result = engine.review(context)

        # Quick review without full context
        result = engine.review_changes(before_data, after_data)
    """

    def __init__(
        self,
        diff_engine: Optional[DiffEngine] = None,
        suggestion_engine: Optional[SuggestionEngine] = None,
        formatter: Optional[ReviewFormatter] = None,
    ):
        self._diff = diff_engine or DiffEngine()
        self._suggestions = suggestion_engine or SuggestionEngine()
        self._formatter = formatter or ReviewFormatter()

    def review(self, context: ReviewContext) -> ReviewResult:
        """Full review of an execution, producing a structured result.

        Args:
            context: ReviewContext with before/after data and validation results

        Returns:
            ReviewResult with changes, issues, suggestions, and status
        """
        result = ReviewResult(
            execution_id=context.execution_id,
            created_at=datetime.now(),
        )

        # 1. Compute field-level diff
        changes = self._diff.compute_diff(
            context.before_data, context.after_data
        )
        for change in changes:
            result.add_change(change)

        # 2. Collect validation errors/warnings
        if context.validation_result:
            for err in context.validation_result.errors:
                result.add_error(ReviewIssue(
                    rule_id=err.rule_id,
                    field=err.field,
                    message=err.message,
                    severity=err.severity,
                    category=err.category,
                ))
            for warn in context.validation_result.warnings:
                result.add_warning(ReviewIssue(
                    rule_id=warn.rule_id,
                    field=warn.field,
                    message=warn.message,
                    severity="warning",
                    category="business",
                ))

        # 3. Collect execution errors
        for error_msg in context.execution_errors:
            result.add_error(ReviewIssue(
                message=error_msg,
                severity="error",
                category="execution",
            ))

        # 4. Generate suggestions
        suggestions = self._suggestions.generate(context, changes)
        for s in suggestions:
            result.add_suggestion(s)

        # 5. Determine status
        result.status = self._determine_status(result)
        result.requires_human_review = (
            result.status in ("failed", "needs_review")
            or any(s.requires_approval for s in suggestions)
        )

        # 6. Generate summary
        result.summary = self._generate_summary(result)

        logger.info(
            "Review complete: status=%s, %d changes, %d errors, %d warnings, %d suggestions",
            result.status, len(result.changes), len(result.errors),
            len(result.warnings), len(result.suggestions),
        )
        return result

    def review_changes(
        self,
        before_data: Dict[str, Any],
        after_data: Dict[str, Any],
    ) -> ReviewResult:
        """Quick review: diff only, no validation or suggestions."""
        context = ReviewContext(
            portal="",
            action="",
            before_data=before_data,
            after_data=after_data,
        )
        return self.review(context)

    def format(self, result: ReviewResult) -> Dict[str, Any]:
        """Convenience: format result as Bridge Protocol dict."""
        return self._formatter.to_bridge_protocol(result)

    def to_text(self, result: ReviewResult) -> str:
        """Convenience: format result as human-readable text."""
        return self._formatter.to_human_readable(result)

    @staticmethod
    def _determine_status(result: ReviewResult) -> str:
        if result.errors:
            return ReviewStatus.FAILED.value
        if result.warnings:
            return ReviewStatus.WARNING.value
        if result.changes:
            return ReviewStatus.APPROVED.value
        return ReviewStatus.APPROVED.value

    @staticmethod
    def _generate_summary(result: ReviewResult) -> str:
        parts = []
        if result.changes:
            parts.append(f"{len(result.changes)} field(s) modified")
        if result.errors:
            parts.append(f"{len(result.errors)} error(s)")
        if result.warnings:
            parts.append(f"{len(result.warnings)} warning(s)")
        if result.suggestions:
            parts.append(f"{len(result.suggestions)} suggestion(s)")

        if not parts:
            return "No changes detected"

        status_prefix = {
            "approved": "Execution completed successfully.",
            "warning": "Execution completed with warnings.",
            "failed": "Execution failed.",
            "needs_review": "Execution needs human review.",
        }.get(result.status, "")

        return f"{status_prefix} {', '.join(parts)}" if status_prefix else ", ".join(parts)
