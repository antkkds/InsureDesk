"""InsureDesk — Fill Engine.

Orchestrates field filling across a form section using
strategy pattern + verification + error handling.

Architecture:
    FillEngine.fill_section()
        → For each field:
            → Lookup strategy by FieldType
            → Transform value if needed
            → Strategy.fill()
            → Collect FieldResult
        → Return FillResult
"""
from __future__ import annotations

from typing import Any, Optional
import time

from src.fill.schema import FillSchema, FieldDefinition, FieldType
from src.fill.result import FillResult, FieldResult
from src.fill.mapper import FieldMapper
from src.fill.transformer import TransformerRegistry
from src.fill.verifier import Verifier
from src.fill.strategies.base import FillStrategy
from src.fill.strategies import DEFAULT_STRATEGIES
from src.fill.exceptions import (
    FillError,
    UnsupportedFieldTypeError,
    RequiredFieldMissingError,
)


class FillEngine:
    """Main fill engine — fills form sections using strategies.

    Usage:
        engine = FillEngine(transformer_registry)
        result = await engine.fill_section(
            browser=browser_session,
            schema=portal_schema.customer,
            data=quote_data,
        )
    """

    def __init__(
        self,
        transformer_registry: Optional[TransformerRegistry] = None,
        strategies: Optional[dict[FieldType, FillStrategy]] = None,
        mapper: Optional[FieldMapper] = None,
        verifier: Optional[Verifier] = None,
    ):
        self.transformer = transformer_registry or TransformerRegistry()
        self.mapper = mapper or FieldMapper()
        self.verifier = verifier or Verifier()

        # Build strategy instances
        self._strategies: dict[FieldType, FillStrategy] = {}
        strategy_classes = strategies or DEFAULT_STRATEGIES
        for ft, cls in strategy_classes.items():
            self._strategies[ft] = cls(verifier=self.verifier)

    def register_strategy(self, field_type: FieldType, strategy: FillStrategy):
        """Register a custom strategy for a field type."""
        self._strategies[field_type] = strategy

    async def fill_section(
        self,
        browser,
        schema: FillSchema,
        data: dict[str, Any],
    ) -> FillResult:
        """Fill all fields in a section.

        Args:
            browser: BrowserEngine-like object with interaction methods.
            schema: FillSchema with field definitions.
            data: Dict of field_name -> value.

        Returns:
            FillResult with per-field results.
        """
        start = time.monotonic()
        result = FillResult(section=schema.name, total_fields=len(schema.fields))

        for field_name, field_def in schema.fields.items():
            value = data.get(field_name)

            # Check required fields
            if value is None and field_def.required:
                result.fields.append(FieldResult(
                    field=field_name,
                    success=False,
                    error=f"Required field '{field_name}' has no value",
                ))
                result.failed += 1
                continue

            # Skip if no value (not required)
            if value is None:
                result.fields.append(FieldResult(
                    field=field_name,
                    success=True,
                    message="Skipped (no value, not required)",
                ))
                result.succeeded += 1
                continue

            # Transform value if transformer specified
            if field_def.transform and self.transformer.has(field_def.transform):
                try:
                    value = self.transformer.transform(field_def.transform, value)
                except FillError as e:
                    result.fields.append(FieldResult(
                        field=field_name,
                        success=False,
                        error=str(e),
                    ))
                    result.failed += 1
                    continue

            # Apply the strategy
            field_start = time.monotonic()
            field_result = await self._fill_field(browser, field_def, value)
            field_result.duration_ms = int((time.monotonic() - field_start) * 1000)
            result.fields.append(field_result)

            if field_result.success:
                result.succeeded += 1
            else:
                result.failed += 1

        result.success = result.failed == 0
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    async def fill_field(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> FieldResult:
        """Fill a single field.

        Args:
            browser: BrowserEngine-like object.
            field: Field definition.
            value: Value to fill.

        Returns:
            FieldResult with outcome.
        """
        start = time.monotonic()
        result = await self._fill_field(browser, field, value)
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    async def _fill_field(
        self,
        browser,
        field: FieldDefinition,
        value: Any,
    ) -> FieldResult:
        """Internal: fill a single field and return a FieldResult."""
        strategy = self._strategies.get(field.type)
        if strategy is None:
            return FieldResult(
                field=field.name,
                success=False,
                error=f"No strategy registered for type '{field.type.value}'",
            )

        try:
            for attempt in range(field.retry + 1):
                try:
                    await strategy.fill(browser, field, value)
                    return FieldResult(
                        field=field.name,
                        success=True,
                        attempts=attempt + 1,
                        message="OK",
                    )
                except FillError as e:
                    if attempt >= field.retry:
                        raise
                    # Brief pause before retry
                    import asyncio
                    await asyncio.sleep(0.5)
                    continue

        except FillError as e:
            return FieldResult(
                field=field.name,
                success=False,
                attempts=field.retry + 1,
                error=str(e),
            )
        except Exception as e:
            return FieldResult(
                field=field.name,
                success=False,
                error=f"Unexpected error: {e}",
            )
