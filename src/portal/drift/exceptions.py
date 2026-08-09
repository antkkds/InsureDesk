"""InsureDesk — Portal Drift Detection: Exceptions."""
from __future__ import annotations


class DriftError(Exception):
    """Base exception for drift detection errors."""
    pass


class BaselineNotFoundError(DriftError):
    """No baseline snapshot exists for the requested portal."""
    def __init__(self, portal_id: str):
        super().__init__(f"No baseline snapshot found for portal: {portal_id}")
        self.portal_id = portal_id


class CaptureError(DriftError):
    """Failed to capture current portal state."""
    def __init__(self, portal_id: str, reason: str):
        super().__init__(f"Failed to capture portal '{portal_id}': {reason}")
        self.portal_id = portal_id


class ComparisonError(DriftError):
    """Error during baseline comparison."""
    pass


class StorageError(DriftError):
    """Error reading/writing baseline data."""
    pass
