"""InsureDesk Quote Tools — Data schemas.

Defines the input/output models for quote operations.
These are shared between tools, executors, and tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class QuoteRequest:
    """Request to calculate an insurance quote.

    Attributes:
        portal: Portal identifier (e.g. 'great_eastern').
        product: Product code (e.g. 'IFE', 'EQ').
        customer: Customer details (name, IC, etc.).
        risk: Risk/property details (sum_insured, address, etc.).
        coverage: Coverage options (add-ons, etc.).
    """
    portal: str = ""
    product: str = ""
    customer: Dict[str, Any] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)
    coverage: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuoteRequest":
        return cls(
            portal=data.get("portal", ""),
            product=data.get("product", ""),
            customer=data.get("customer", {}),
            risk=data.get("risk", {}),
            coverage=data.get("coverage", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portal": self.portal,
            "product": self.product,
            "customer": self.customer,
            "risk": self.risk,
            "coverage": self.coverage,
        }


@dataclass
class QuoteResult:
    """Result of a quote calculation.

    Attributes:
        success: Whether the calculation succeeded.
        premium: The calculated premium amount (0 if failed).
        currency: Currency code (e.g. 'MYR').
        breakdown: Optional premium breakdown by coverage.
        details: Raw premium display text from portal.
        error: Error message if failed.
        error_code: Machine-readable error code.
    """
    success: bool = True
    premium: float = 0.0
    currency: str = "MYR"
    breakdown: Dict[str, float] = field(default_factory=dict)
    details: str = ""
    error: str = ""
    error_code: str = ""

    @classmethod
    def ok(
        cls,
        premium: float,
        currency: str = "MYR",
        breakdown: Optional[Dict[str, float]] = None,
        details: str = "",
    ) -> "QuoteResult":
        return cls(
            success=True,
            premium=premium,
            currency=currency,
            breakdown=breakdown or {},
            details=details,
        )

    @classmethod
    def fail(cls, error: str, error_code: str = "quote_error") -> "QuoteResult":
        return cls(success=False, error=error, error_code=error_code)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "premium": self.premium,
            "currency": self.currency,
            "breakdown": self.breakdown,
            "details": self.details,
            "error": self.error,
            "error_code": self.error_code,
        }
