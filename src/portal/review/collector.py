"""Portal Review Engine — Review Collector.

Gathers data from ExecutionEngine and ValidationEngine to build
a complete ReviewContext for the ReviewEngine.

Acts as the bridge between execution/validation outputs and review input.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.review.models import ReviewContext
from src.portal.validation.models import ValidationResult
from src.portal.execution.models import ExecutionResult

logger = logging.getLogger("insuredesk.review.collector")


class ReviewCollector:
    """Collects and assembles review data from multiple sources.

    Usage:
        collector = ReviewCollector()
        context = collector.collect(
            portal="great_eastern",
            action="create_quote",
            before_data=before,
            after_data=after,
            validation_result=val_result,
            execution_result=exec_result,
        )
        result = review_engine.review(context)
    """

    def collect(
        self,
        portal: str,
        action: str,
        before_data: Optional[Dict[str, Any]] = None,
        after_data: Optional[Dict[str, Any]] = None,
        validation_result: Optional[ValidationResult] = None,
        execution_result: Optional[ExecutionResult] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReviewContext:
        """Assemble a ReviewContext from all available data sources.

        Args:
            portal: Portal name
            action: Action name
            before_data: Data snapshot before execution
            after_data: Data snapshot after execution
            validation_result: Result from ValidationEngine
            execution_result: Result from ExecutionEngine
            metadata: Additional metadata

        Returns:
            A populated ReviewContext
        """
        # Extract execution errors
        execution_errors: List[str] = []
        if execution_result:
            execution_errors = list(execution_result.errors)

        # Ensure data defaults
        before_data = before_data or {}
        after_data = after_data or {}

        context = ReviewContext(
            portal=portal,
            action=action,
            before_data=before_data,
            after_data=after_data,
            validation_result=validation_result,
            execution_errors=execution_errors,
            metadata=metadata or {},
        )

        logger.info(
            "ReviewContext assembled: %s/%s (%d fields before, %d after%s)",
            portal, action,
            len(before_data), len(after_data),
            ", has validation" if validation_result else "",
        )
        return context

    def collect_from_execution(
        self,
        portal: str,
        action: str,
        before_data: Dict[str, Any],
        after_data: Dict[str, Any],
        execution_result: ExecutionResult,
        validation_result: Optional[ValidationResult] = None,
    ) -> ReviewContext:
        """Convenience method: collect from execution output."""
        return self.collect(
            portal=portal,
            action=action,
            before_data=before_data,
            after_data=after_data,
            validation_result=validation_result,
            execution_result=execution_result,
        )
