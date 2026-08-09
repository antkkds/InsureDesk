"""Portal Workflow Recorder — Exceptions."""

from __future__ import annotations


class RecorderError(Exception):
    """Base exception for recorder errors."""


class CaptureError(RecorderError):
    """Raised when capturing browser events fails."""


class SelectorGenerationError(RecorderError):
    """Raised when a stable selector cannot be generated."""


class NormalizationError(RecorderError):
    """Raised when normalizing events to steps fails."""


class SerializationError(RecorderError):
    """Raised when serializing workflow to YAML fails."""


class ReplayError(RecorderError):
    """Raised when replaying a workflow fails."""


class RecordingNotFoundError(RecorderError):
    """Raised when a requested recording session is not found."""
