"""InsureDesk Quote Tools — Quote Validation Layer (Phase 4B).

Validates quote requests *before* they reach the browser.
This is the first line of defense: catch missing/invalid fields
early so the user gets clear, structured error messages instead
of mysterious browser timeouts.

Integration:
    CalculateQuoteTool calls validator.validate() before
    QuoteExecutor.calculate().  If validation fails the tool
    returns the structured errors immediately — no browser needed.

    UIP-AI can read the ValidationError codes to ask the customer
    for the right fields in the right format.

Design principles:
    - Zero browser dependency — pure Python validation
    - Driven by YAML portal field definitions (type, required, options)
    - Shares REQUEST_TO_YAML_FIELD with QuoteExecutor for consistency
    - Strict on required fields, lenient on optional fields
    - Business rules are extensible per portal
"""

from __future__ import annotations

import os
import re
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Same mapping used by QuoteExecutor — single source of truth
from src.portal.quote_executor import REQUEST_TO_YAML_FIELD
from src.portal.mapping import load_portal_mapping, PortalMapping, PORTALS_DIR

# ══════════════════════════════════════════════════════════════════
# Result types
# ══════════════════════════════════════════════════════════════════


@dataclass
class ValidationError:
    """A single validation error.

    Attributes:
        field: Original request field name (e.g. 'sum_insured').
        yaml_field: YAML field name the request key maps to
            (e.g. 'sum_insured_building').
        message: Human-readable error description.
        code: Machine-readable error code for UIP-AI logic.
        value: The value that failed validation (if applicable).
    """
    field: str
    yaml_field: str = ""
    message: str = ""
    code: str = "validation_error"
    value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "yaml_field": self.yaml_field,
            "message": self.message,
            "code": self.code,
            "value": self.value,
        }


@dataclass
class ValidationResult:
    """Result of validating a quote request.

    Attributes:
        valid: True if the request passed all validation checks.
        errors: List of ValidationError (empty if valid).
        warnings: Non-blocking advisory notes.
    """
    valid: bool = True
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(valid=True)

    @classmethod
    def fail(cls, errors: List[ValidationError]) -> "ValidationResult":
        return cls(valid=False, errors=errors)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": self.warnings,
        }


# ══════════════════════════════════════════════════════════════════
# QuoteValidator
# ══════════════════════════════════════════════════════════════════


class QuoteValidator:
    """Validate quote requests before browser execution.

    Usage:
        validator = QuoteValidator()
        result = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {"sum_insured": 500000},
            "customer": {"name": "Alice"},
        })
        if not result.valid:
            for err in result.errors:
                print(f"{err.field}: {err.message} ({err.code})")
    """

    # ── Public API ──

    def validate(self, request: Dict[str, Any]) -> ValidationResult:
        """Validate a complete quote request.

        Args:
            request: Dict with keys: portal, product, customer, risk, coverage.

        Returns:
            ValidationResult with errors/warnings.
        """
        errors: List[ValidationError] = []
        warnings: List[str] = []

        # 1. Basic structural checks
        self._check_presence_errors(request, errors)

        if errors:
            # Can't proceed without portal/product
            return ValidationResult.fail(errors)

        # 2. Load portal mapping
        portal_name = request["portal"]
        mapping = load_portal_mapping(portal_name)
        if mapping is None:
            errors.append(ValidationError(
                field="portal",
                message=f"Unknown portal: '{portal_name}'. "
                        f"No YAML mapping configured.",
                code="unknown_portal",
                value=portal_name,
            ))
            return ValidationResult.fail(errors)

        # 3. Check product is supported (non-blocking warning)
        product = request["product"]
        products = self._load_portal_products(portal_name)
        if products and product.upper() not in {k.upper() for k in products}:
            supported = list(products.keys())
            warnings.append(
                f"Product '{product}' not listed in portal config. "
                f"Supported: {', '.join(supported)}. "
                f"The portal may reject it."
            )

        # 4. Merge customer + risk + coverage
        merged = self._merge_request(request)

        # 5. Validate against YAML field definitions
        fields_yaml = (
            mapping.selectors
            .get("quotation", {})
            .get("fields", {})
        )
        if not fields_yaml:
            warnings.append("No quotation fields defined in YAML — skipping field validation.")

        self._validate_required_fields(merged, fields_yaml, errors)
        self._validate_field_types(merged, fields_yaml, errors)
        self._validate_business_rules(merged, fields_yaml, errors, warnings)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # ── Step 1: Structural checks ──

    @staticmethod
    def _check_presence_errors(
        request: Dict[str, Any], errors: List[ValidationError]
    ) -> None:
        """Check portal and product exist."""
        portal = request.get("portal", "")
        if not portal:
            errors.append(ValidationError(
                field="portal",
                message="Missing required field: 'portal'. "
                        "Must be a portal identifier (e.g. 'great_eastern').",
                code="missing_required",
            ))
        elif not isinstance(portal, str):
            errors.append(ValidationError(
                field="portal",
                message="'portal' must be a string.",
                code="type_error",
                value=portal,
            ))

        product = request.get("product", "")
        if not product:
            errors.append(ValidationError(
                field="product",
                message="Missing required field: 'product'. "
                        "Must be a product code (e.g. 'IFE', 'EQ').",
                code="missing_required",
            ))
        elif not isinstance(product, str):
            errors.append(ValidationError(
                field="product",
                message="'product' must be a string.",
                code="type_error",
                value=product,
            ))

    # ── Product list loader ──

    @staticmethod
    def _load_portal_products(portal_name: str) -> Dict[str, Any]:
        """Load the products dict directly from YAML (not in PortalMapping)."""
        yaml_path = PORTALS_DIR / f"{portal_name}.yaml"
        if not yaml_path.exists():
            return {}
        try:
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
            if data and "portal" in data:
                return data["portal"].get("products", {})
        except Exception:
            pass
        return {}

    # ── Step 4: Merge request sections ──

    @staticmethod
    def _merge_request(request: Dict[str, Any]) -> Dict[str, Any]:
        """Merge customer + risk + coverage into a single flat dict."""
        merged: Dict[str, Any] = {}
        for section in ("customer", "risk", "coverage"):
            data = request.get(section, {})
            if isinstance(data, dict):
                merged.update(data)
        return merged

    # ── Step 5a: Required fields ──

    @staticmethod
    def _validate_required_fields(
        data: Dict[str, Any],
        fields_yaml: Dict[str, Any],
        errors: List[ValidationError],
    ) -> None:
        """Check all YAML-required fields are present in the request."""
        for yaml_field_name, field_def in fields_yaml.items():
            if not isinstance(field_def, dict):
                continue
            if not field_def.get("required", False):
                continue

            # Find which request key maps to this YAML field
            request_keys = _yaml_field_to_request_keys(yaml_field_name)
            # Check if any of the request keys have a non-empty value
            found = False
            for req_key in request_keys:
                if req_key in data and data[req_key] is not None and data[req_key] != "":
                    found = True
                    break

            if not found:
                # Build helpful message
                req_key = request_keys[0] if request_keys else yaml_field_name
                field_type = field_def.get("type", "text")
                hint = _hint_for_field(yaml_field_name, field_type)
                errors.append(ValidationError(
                    field=req_key,
                    yaml_field=yaml_field_name,
                    message=(
                        f"Missing required field: '{req_key}' "
                        f"(type: {field_type}). {hint}"
                    ),
                    code="missing_required",
                ))

    # ── Step 5b: Type validation ──

    @staticmethod
    def _validate_field_types(
        data: Dict[str, Any],
        fields_yaml: Dict[str, Any],
        errors: List[ValidationError],
    ) -> None:
        """Check field values match expected types from YAML."""
        for req_key, value in data.items():
            if value is None or value == "":
                continue
            yaml_field = REQUEST_TO_YAML_FIELD.get(req_key, req_key)
            field_def = fields_yaml.get(yaml_field)
            if not isinstance(field_def, dict):
                continue
            field_type = field_def.get("type", "text")
            type_errors = _validate_type(req_key, yaml_field, value, field_type)
            errors.extend(type_errors)

    # ── Step 5c: Business rules ──

    @staticmethod
    def _validate_business_rules(
        data: Dict[str, Any],
        fields_yaml: Dict[str, Any],
        errors: List[ValidationError],
        warnings: List[str],
    ) -> None:
        """Apply business-rule validations."""
        si_building = _get_first_value(data, "sum_insured_building")
        si_contents = _get_first_value(data, "sum_insured_contents")

        # Rule: At least one sum_insured must be > 0
        has_building = (
            si_building is not None
            and _to_float(si_building, None) is not None
            and _to_float(si_building, 0) > 0
        )
        has_contents = (
            si_contents is not None
            and _to_float(si_contents, None) is not None
            and _to_float(si_contents, 0) > 0
        )

        if not has_building and not has_contents:
            warnings.append(
                "No sum_insured provided. "
                "At least one of 'sum_insured' or "
                "'sum_insured_contents' is usually required."
            )

        # Rule: sum_insured > 0
        for key, yf in [("sum_insured", "sum_insured_building"),
                        ("sum_insured_contents", "sum_insured_contents")]:
            val = _get_first_value(data, yf)
            if val is not None and val != "":
                f = _to_float(val, None)
                if f is not None and f <= 0:
                    errors.append(ValidationError(
                        field=key,
                        yaml_field=yf,
                        message=f"'{key}' must be greater than 0. Got: {val}",
                        code="business_rule",
                        value=val,
                    ))

        # Rule: coverage_end > coverage_start
        cov_start = data.get("coverage_start")
        cov_end = data.get("coverage_end")
        if cov_start and cov_end:
            ds = _parse_date(cov_start)
            de = _parse_date(cov_end)
            if ds and de and de <= ds:
                errors.append(ValidationError(
                    field="coverage_end",
                    yaml_field="coverage_end",
                    message=(
                        f"coverage_end ({cov_end}) must be after "
                        f"coverage_start ({cov_start})."
                    ),
                    code="business_rule",
                    value=cov_end,
                ))


# ══════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════


def _yaml_field_to_request_keys(yaml_field: str) -> List[str]:
    """Reverse-lookup: YAML field → list of possible request keys."""
    keys = [yaml_field]
    for req_key, yf in REQUEST_TO_YAML_FIELD.items():
        if yf == yaml_field and req_key not in keys:
            keys.append(req_key)
    return keys


def _hint_for_field(field_name: str, field_type: str) -> str:
    """Generate a human hint for a field name."""
    hints = {
        "sum_insured_building": "e.g. 500000",
        "sum_insured_contents": "e.g. 100000",
        "property_address": "Full street address",
        "property_postcode": "5-digit postcode",
        "occupancy": "e.g. 'Owner', 'Tenant', 'Vacant'",
        "coverage_start": "Date format: YYYY-MM-DD",
        "coverage_end": "Date format: YYYY-MM-DD",
        "construction_type": "e.g. 'Brick', 'Concrete', 'Wood'",
        "year_built": "4-digit year, e.g. 2010",
    }
    hint = hints.get(field_name, "")
    if hint:
        return hint
    if field_type == "number":
        return "Must be a numeric value."
    if field_type == "date":
        return "Use YYYY-MM-DD format."
    if field_type == "select":
        return "Must be one of the available options."
    return ""


def _validate_type(
    req_key: str,
    yaml_field: str,
    value: Any,
    field_type: str,
) -> List[ValidationError]:
    """Validate a single value against its expected type.

    Returns a list of ValidationError (empty if valid).
    """
    errors: List[ValidationError] = []

    if field_type == "number":
        if isinstance(value, bool):
            errors.append(ValidationError(
                field=req_key,
                yaml_field=yaml_field,
                message=f"'{req_key}' must be a number. Got boolean: {value}.",
                code="type_error",
                value=value,
            ))
        elif isinstance(value, (int, float)):
            pass  # Valid number
        elif isinstance(value, str):
            f = _to_float(value, None)
            if f is None:
                errors.append(ValidationError(
                    field=req_key,
                    yaml_field=yaml_field,
                    message=f"'{req_key}' must be a numeric value. "
                            f"Got: '{value}' (not a valid number).",
                    code="type_error",
                    value=value,
                ))
        else:
            errors.append(ValidationError(
                field=req_key,
                yaml_field=yaml_field,
                message=f"'{req_key}' expected a number. Got {type(value).__name__}: {value}.",
                code="type_error",
                value=value,
            ))

    elif field_type == "date":
        if isinstance(value, str):
            if _parse_date(value) is None:
                errors.append(ValidationError(
                    field=req_key,
                    yaml_field=yaml_field,
                    message=f"'{req_key}' must be a valid date. "
                            f"Got: '{value}'. Expected format: YYYY-MM-DD.",
                    code="type_error",
                    value=value,
                ))
        elif isinstance(value, (int, float)):
            pass  # Accept timestamp numbers
        elif not isinstance(value, str):
            errors.append(ValidationError(
                field=req_key,
                yaml_field=yaml_field,
                message=f"'{req_key}' expected a date string. "
                        f"Got {type(value).__name__}: {value}.",
                code="type_error",
                value=value,
            ))

    elif field_type == "text":
        if not isinstance(value, str):
            errors.append(ValidationError(
                field=req_key,
                yaml_field=yaml_field,
                message=f"'{req_key}' must be a string. "
                        f"Got {type(value).__name__}: {value}.",
                code="type_error",
                value=value,
            ))

    return errors


def _to_float(value: Any, default: Any = 0.0) -> float:
    """Safely convert a value to float."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").replace(" ", ""))
        except (ValueError, AttributeError):
            return default
    return default


def _parse_date(value: Any) -> Optional[datetime]:
    """Try to parse a date value."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(value.strip(), fmt)
            except (ValueError, AttributeError):
                continue
    return None


def _get_first_value(data: Dict[str, Any], yaml_name: str) -> Any:
    """Get the first non-empty value matching a YAML field name.

    Checks all possible request keys that map to this YAML field.
    """
    keys = _yaml_field_to_request_keys(yaml_name)
    for k in keys:
        if k in data and data[k] is not None and data[k] != "":
            return data[k]
    return None
