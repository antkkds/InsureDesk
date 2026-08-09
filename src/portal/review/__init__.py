"""Portal Review Engine.

AI explainability layer for InsureDesk portal execution.
Transforms execution + validation results into structured,
human/AI-readable reviews with changes, issues, and suggestions.

Output is designed for Bridge Protocol communication back to UIP-AI.
"""

from __future__ import annotations

from src.portal.review.models import (
    ReviewContext,
    ReviewResult,
    Change,
    ReviewIssue,
    Suggestion,
    ReviewStatus,
    ChangeType,
)
from src.portal.review.engine import ReviewEngine
from src.portal.review.diff import DiffEngine
from src.portal.review.collector import ReviewCollector
from src.portal.review.suggestions import SuggestionEngine
from src.portal.review.formatter import ReviewFormatter
from src.portal.review.exceptions import (
    ReviewError,
    ReviewCollectionError,
    ReviewDiffError,
    ReviewFormatError,
)

__all__ = [
    "ReviewContext",
    "ReviewResult",
    "Change",
    "ReviewIssue",
    "Suggestion",
    "ReviewStatus",
    "ChangeType",
    "ReviewEngine",
    "DiffEngine",
    "ReviewCollector",
    "SuggestionEngine",
    "ReviewFormatter",
    "ReviewError",
    "ReviewCollectionError",
    "ReviewDiffError",
    "ReviewFormatError",
]
