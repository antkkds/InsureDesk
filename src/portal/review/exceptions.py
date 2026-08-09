"""Portal Review Engine — Exceptions."""

from __future__ import annotations


class ReviewError(Exception):
    """Base exception for review engine errors."""


class ReviewCollectionError(ReviewError):
    """Raised when collecting review data fails."""


class ReviewDiffError(ReviewError):
    """Raised when computing field diffs fails."""


class ReviewFormatError(ReviewError):
    """Raised when formatting review output fails."""
