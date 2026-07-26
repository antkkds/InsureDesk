"""InsureDesk Runtime — E2E Workflow Executor.

The primary orchestration layer: takes raw portal data,
auto-selects the right adapter, extracts domain models,
validates them, and returns structured results.

Flow:
    raw_data → select_adapter() → adapter.extract_*() → validate()
    → ExtractResult or BatchResult

Usage:
    from src.runtime.executor import RuntimeExecutor

    executor = RuntimeExecutor()

    # Single extraction
    result = executor.extract_policy({"policy_no": "GE-123"})
    if result.success:
        policy = result.model
    else:
        print(result.error)

    # Batch extraction
    results = executor.batch_extract([data1, data2, data3])
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

from src.models.policy import Policy
from src.models.claim import Claim
from src.models.customer import Customer
from src.runtime.registry import AdapterRegistry, adapter_registry
from src.runtime.selector import select_adapter
from src.runtime.errors import (
    ExtractionError,
    AdapterNotFoundError,
    ValidationFailedError,
    MissingDataError,
    AdapterExecutionError,
    CapabilityNotSupportedError,
)
from src.runtime.capabilities import (
    AdapterCapability,
    supports_capability,
)


# ══════════════════════════════════════════════════════════════════
# Result Types
# ══════════════════════════════════════════════════════════════════


@dataclass
class ExtractResult:
    """Result of a single extraction operation.

    Properties:
        success: True if extraction + validation succeeded
        model: The extracted domain model (Policy, Claim, or Customer)
        adapter_name: Name of the adapter used
        adapter_key: Registry key of the adapter used
        validation: Validation result (None if skipped)
        error: Error code if failed
        error_message: Human-readable error if failed
        error_context: Structured error context
        raw_data: Original raw data (for debugging / retry)
    """
    success: bool = True
    model: Any = None
    adapter_name: str = ""
    adapter_key: str = ""
    validation: Any = None
    error: str = ""
    error_message: str = ""
    error_context: Dict[str, Any] = field(default_factory=dict)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, model, adapter_name: str, adapter_key: str, validation=None,
           raw_data: Optional[Dict] = None) -> "ExtractResult":
        return cls(
            success=True,
            model=model,
            adapter_name=adapter_name,
            adapter_key=adapter_key,
            validation=validation,
            raw_data=raw_data or {},
        )

    @classmethod
    def fail(cls, error: ExtractionError, raw_data: Optional[Dict] = None) -> "ExtractResult":
        return cls(
            success=False,
            error=error.code,
            error_message=str(error),
            error_context=error.context,
            raw_data=raw_data or {},
        )


@dataclass
class BatchResult:
    """Result of a batch extraction operation.

    Properties:
        total: Total items processed
        succeeded: Number of successful extractions
        failed: Number of failed extractions
        results: List of ExtractResult objects (in order)
        summary: Human-readable summary string
    """
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: List[ExtractResult] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"Batch: {self.total} items, "
            f"{self.succeeded} succeeded, "
            f"{self.failed} failed"
        )

    @classmethod
    def from_results(cls, results: List[ExtractResult]) -> "BatchResult":
        succeeded = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        return cls(
            total=len(results),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )


# ══════════════════════════════════════════════════════════════════
# Runtime Executor
# ══════════════════════════════════════════════════════════════════


class RuntimeExecutor:
    """E2E workflow executor: portal data → domain model.

    The primary interface for extracting data from any portal.
    Handles adapter selection, extraction, validation, and error handling.

    Usage:
        executor = RuntimeExecutor()
        result = executor.extract_policy(data)
        if result.success:
            policy = result.model
    """

    def __init__(self, registry: Optional[AdapterRegistry] = None):
        self.registry = registry or adapter_registry
        self._hooks_before: List[Callable] = []
        self._hooks_after: List[Callable] = []

    # ── Main extraction methods ──

    def extract_policy(
        self,
        raw_data: Dict[str, Any],
        portal_hint: Optional[str] = None,
        validate: bool = True,
    ) -> ExtractResult:
        """Extract a Policy from raw portal data.

        Args:
            raw_data: Raw portal data dict
            portal_hint: Optional portal name hint
            validate: Whether to validate the extracted model (default: True)

        Returns:
            ExtractResult with the Policy model or error info
        """
        return self._extract(
            raw_data,
            extract_method="extract_policy",
            validate_method="validate_policy",
            portal_hint=portal_hint,
            validate=validate,
        )

    def extract_claim(
        self,
        raw_data: Dict[str, Any],
        portal_hint: Optional[str] = None,
        validate: bool = True,
    ) -> ExtractResult:
        """Extract a Claim from raw portal data."""
        return self._extract(
            raw_data,
            extract_method="extract_claim",
            validate_method="validate_claim",
            portal_hint=portal_hint,
            validate=validate,
        )

    def extract_customer(
        self,
        raw_data: Dict[str, Any],
        portal_hint: Optional[str] = None,
        validate: bool = False,
    ) -> ExtractResult:
        """Extract a Customer from raw portal data.

        Customer validation is off by default (minimal required fields).
        """
        return self._extract(
            raw_data,
            extract_method="extract_customer",
            validate_method=None,
            portal_hint=portal_hint,
            validate=validate,
        )

    # ── Batch operations ──

    def batch_extract(
        self,
        items: List[Dict[str, Any]],
        portal_hint: Optional[str] = None,
        validate: bool = True,
        extract_type: str = "policy",
    ) -> BatchResult:
        """Extract models from multiple raw data items.

        Each item is processed independently — failures don't stop
        subsequent items. The batch completes all items even if
        some fail.

        Args:
            items: List of raw data dicts
            portal_hint: Optional portal name hint for all items
            validate: Whether to validate extracted models
            extract_type: 'policy', 'claim', or 'customer'

        Returns:
            BatchResult with all individual results
        """
        extract_map = {
            "policy": self.extract_policy,
            "claim": self.extract_claim,
            "customer": self.extract_customer,
        }
        extract_fn = extract_map.get(extract_type, self.extract_policy)

        results = []
        for item in items:
            result = extract_fn(item, portal_hint=portal_hint, validate=validate)
            results.append(result)

        return BatchResult.from_results(results)

    # ── Capability checks ──

    def supports(self, portal_hint: str, capability: AdapterCapability) -> bool:
        """Check if a named adapter supports a capability.

        Args:
            portal_hint: Portal name or key
            capability: Capability to check

        Returns:
            True if supported
        """
        key = portal_hint.lower().replace(" ", "_")
        return supports_capability(key, capability)

    def find_by_capability(self, capability: AdapterCapability) -> List[Dict[str, Any]]:
        """Find all adapters supporting a capability."""
        return self.registry.find_by_capability(capability)

    # ── Lifecycle hooks ──

    def before_extract(self, hook: Callable):
        """Register a hook called before each extraction.

        Hook signature: (raw_data, extract_method, portal_hint) -> None
        Can raise to abort extraction.
        """
        self._hooks_before.append(hook)

    def after_extract(self, hook: Callable):
        """Register a hook called after each extraction.

        Hook signature: (result) -> None
        Receives the final ExtractResult.
        """
        self._hooks_after.append(hook)

    # ── Stats ──

    def stats(self) -> Dict[str, Any]:
        """Get aggregate stats from the registry."""
        return self.registry.stats()

    # ── Internal ──

    def _extract(
        self,
        raw_data: Dict[str, Any],
        extract_method: str,
        validate_method: Optional[str],
        portal_hint: Optional[str] = None,
        validate: bool = True,
    ) -> ExtractResult:
        """Internal: select adapter → extract → validate → result."""
        if not raw_data:
            return ExtractResult.fail(MissingDataError([]), raw_data={})

        # 1. Run before hooks
        try:
            for hook in self._hooks_before:
                hook(raw_data, extract_method, portal_hint)
        except ExtractionError as e:
            return ExtractResult.fail(e, raw_data=raw_data)

        # 2. Select adapter via DetectionResult
        try:
            detection = select_adapter(raw_data, portal_hint=portal_hint,
                                       registry=self.registry)
        except ExtractionError as e:
            return ExtractResult.fail(e, raw_data=raw_data)

        adapter = detection.get_adapter(self.registry)

        if adapter is None:
            return ExtractResult.fail(
                AdapterNotFoundError(portal_hint or "", available=self.registry.list()),
                raw_data=raw_data,
            )

        # 3. Extract
        try:
            extract_fn = getattr(adapter, extract_method, None)
            if extract_fn is None:
                return ExtractResult.fail(
                    AdapterExecutionError(adapter.name, f"Method {extract_method} not found"),
                    raw_data=raw_data,
                )
            model = extract_fn(raw_data)
        except Exception as e:
            return ExtractResult.fail(
                AdapterExecutionError(adapter.name, str(e)),
                raw_data=raw_data,
            )

        # 4. Validate (if requested)
        validation_result = None
        if validate and validate_method:
            try:
                validate_fn = getattr(adapter, validate_method, None)
                if validate_fn:
                    validation_result = validate_fn(model)
                    if not validation_result.valid:
                        return ExtractResult.fail(
                            ValidationFailedError(
                                extract_method.replace("extract_", ""),
                                validation_result.errors,
                            ),
                            raw_data=raw_data,
                        )
            except Exception:
                pass  # Validation errors don't block extraction

        # 5. Run after hooks
        result = ExtractResult.ok(
            model, adapter.name,
            detection.adapter or adapter.name.lower().replace(" ", "_"),
            validation=validation_result,
            raw_data=raw_data,
        )
        for hook in self._hooks_after:
            try:
                hook(result)
            except Exception:
                pass

        return result
