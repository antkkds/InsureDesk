"""InsureDesk Runtime — Adapter Runtime Integration Layer.

The runtime layer sits between portal data and domain models.
It handles adapter selection, extraction orchestration, validation,
error normalization, and cross-insurer workflows.

Architecture:
    raw_data → select_adapter() → adapter.extract_*() → validate() → result

Main Components:
    - RuntimeExecutor: Primary orchestration entry point
    - adapter_registry: Dynamic registry singleton
    - AdapterCapability: Capability enums for adapters
    - ExtractionError: Normalized error hierarchy

Usage:
    from src.runtime import RuntimeExecutor, adapter_registry

    executor = RuntimeExecutor()
    result = executor.extract_policy({"policy_no": "GE-123"})
    if result.success:
        print(result.model.policy_number)
"""

from src.runtime.executor import RuntimeExecutor, ExtractResult, BatchResult
from src.runtime.registry import AdapterRegistry, adapter_registry
from src.runtime.capabilities import AdapterCapability
from src.runtime.errors import (
    ExtractionError,
    AdapterNotFoundError,
    ValidationFailedError,
    MissingDataError,
    AdapterExecutionError,
    CapabilityNotSupportedError,
)
from src.runtime.selector import select_adapter, detect_portal_from_data, DetectionResult, DetectionCandidate
from src.runtime.browser_session import (
    BrowserSession, BrowserPage, Selector, SessionContext, Credentials,
    MockBrowserSession, MockPage,
    DriverCapabilities, BrowserFactory,
    BrowserError, BrowserTimeout, ElementNotFound,
    NavigationFailed, AuthenticationFailed, SessionExpired, BrowserClosed,
)

__all__ = [
    # Executor
    "RuntimeExecutor",
    "ExtractResult",
    "BatchResult",
    # Registry
    "AdapterRegistry",
    "adapter_registry",
    # Capabilities
    "AdapterCapability",
    # Selector
    "select_adapter",
    "detect_portal_from_data",
    "DetectionResult",
    "DetectionCandidate",
    # Errors
    "ExtractionError",
    "AdapterNotFoundError",
    "ValidationFailedError",
    "MissingDataError",
    "AdapterExecutionError",
    "CapabilityNotSupportedError",
    # Browser
    "BrowserSession",
    "BrowserPage",
    "Selector",
    "SessionContext",
    "Credentials",
    "MockBrowserSession",
    "MockPage",
    "DriverCapabilities",
    "BrowserFactory",
    "BrowserError",
    "BrowserTimeout",
    "ElementNotFound",
    "NavigationFailed",
    "AuthenticationFailed",
    "SessionExpired",
    "BrowserClosed",
]
