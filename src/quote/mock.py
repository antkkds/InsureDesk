"""InsureDesk — Mock Quote Runtime.

A local-only quote engine that simulates insurance quotation
without touching any real portal. Used for:

1. Testing QuoteAdapter interfaces and workflows
2. Validating the business logic chain
   (QuoteAdapter → Workflow → Tool Runtime → Assistant)
3. Development when no real portal is available
4. CI/CD test environments

Usage:
    adapter = MockQuoteAdapter()
    result = await adapter.create_quote(request)
    result = await adapter.calculate(request)

Mock responses are configurable via MockQuoteConfig:
    adapter = MockQuoteAdapter(config=MockQuoteConfig(
        product_codes=["FIRE", "PA"],
        fail_rate=0.0,  # 0-1 probability of simulated failure
        delay_range=(0.1, 0.5),  # simulated processing delay
    ))
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from src.quote.base import QuoteAdapter
from src.quote.models import (
    QuoteRequest, QuoteResult, QuoteDraft,
    QuoteStatus,
)
from src.portals.base import SessionMode


# ══════════════════════════════════════════════════════════════════
# Mock Configuration
# ══════════════════════════════════════════════════════════════════


@dataclass
class MockQuoteConfig:
    """Configuration for MockQuoteAdapter behavior."""

    # Available product codes
    product_codes: List[str] = field(default_factory=lambda: [
        "FIRE", "ENGINEERING", "PA", "MOTOR", "TRAVEL", "MARINE",
    ])

    # Failure simulation (0.0 = never fail, 1.0 = always fail)
    fail_rate: float = 0.0

    # Simulated processing delay range in seconds (min, max)
    delay_range: tuple = (0.1, 0.5)

    # Premium calculation rules (simple multipliers)
    # base_premium * (sum_insured / 1000) * risk_multiplier
    base_premium: float = 50.0
    risk_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "fire": 2.5,
        "engineering": 3.0,
        "motor": 4.0,
        "marine": 2.0,
        "personal_accident": 1.5,
        "medical": 5.0,
        "travel": 0.8,
        "liability": 3.5,
        "unknown": 2.0,
    })

    # Stamp duty & levies
    stamp_duty_rate: float = 0.05  # 5%
    service_tax_rate: float = 0.06  # 6%


# ══════════════════════════════════════════════════════════════════
# Mock Quote Adapter
# ══════════════════════════════════════════════════════════════════


class MockQuoteAdapter(QuoteAdapter):
    """Standalone mock quote engine. No browser needed.

    Simulates the full quote lifecycle:
        create_quote → calculate → save_draft → submit

    All responses are deterministic (no real portal involved).
    Use MockQuoteConfig to control behavior.
    """

    def __init__(self, engine=None,
                 mode: SessionMode = SessionMode.READ_WRITE,
                 config: Optional[MockQuoteConfig] = None):
        super().__init__(engine)
        self._mode = mode
        self._config = config or MockQuoteConfig()
        self._quote_counter: int = 0
        self._drafts: Dict[str, QuoteDraft] = {}
        self._active_quote: Optional[dict] = None

    # ── Properties ────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "mock_quote"

    @property
    def channel_type(self) -> str:
        return "MOCK"

    @property
    def config(self) -> MockQuoteConfig:
        return self._config

    @property
    def mode(self) -> SessionMode:
        return self._mode

    @mode.setter
    def mode(self, new_mode: SessionMode):
        self._mode = new_mode

    # ── Safety ────────────────────────────────────────────────

    def _assert_write_permitted(self):
        """Raise ReadOnlyViolationError if in READ_ONLY mode."""
        if self._mode == SessionMode.READ_ONLY:
            from src.portals.base import ReadOnlyViolationError
            raise ReadOnlyViolationError(
                f"Write operation denied: '{self.name}' is in READ_ONLY mode."
            )

    # ── Simulated delay ──────────────────────────────────────

    async def _simulate_delay(self):
        """Simulate processing delay to mimic real portal behavior."""
        import asyncio
        delay = random.uniform(*self._config.delay_range)
        await asyncio.sleep(delay)

    # ── Premium Calculation ──────────────────────────────────

    def _calculate_premium(self, request: QuoteRequest) -> dict:
        """Calculate mock premium based on request parameters."""
        total_sum_insured = sum(
            item.sum_insured for item in request.items
        ) or 100000

        # Determine risk class (str in QuoteRequest, map to known keys)
        risk_key = (request.risk_class or "fire").lower()
        multiplier = self._config.risk_multipliers.get(risk_key, 2.0)

        # Calculate premiums
        base = self._config.base_premium * (total_sum_insured / 1000)
        gross_premium = round(base * multiplier, 2)
        stamp_duty = round(gross_premium * self._config.stamp_duty_rate, 2)
        service_tax = round(gross_premium * self._config.service_tax_rate, 2)
        total_premium = round(gross_premium + stamp_duty + service_tax, 2)

        return {
            "gross_premium": gross_premium,
            "stamp_duty": stamp_duty,
            "service_tax": service_tax,
            "total_premium": total_premium,
            "sum_insured": total_sum_insured,
        }

    def _simulate_failure(self) -> Optional[str]:
        """Simulate a failure if fail_rate triggers. Returns error message or None."""
        if random.random() < self._config.fail_rate:
            errors = [
                "Sum insured exceeds maximum limit for this risk class.",
                "Occupancy classification not supported for selected product.",
                "Required field 'construction_type' is missing.",
                "Policy period exceeds maximum 12 months.",
                "Selected territory is not covered under this policy.",
            ]
            return random.choice(errors)
        return None

    # ── Mock Data Generator ───────────────────────────────────

    def _generate_mock_form_data(self) -> dict:
        """Generate a realistic set of mock form fields and values."""
        return {
            "insured_name": "Mock Insured Sdn Bhd",
            "insured_email": "mock@insured.my",
            "insured_phone": "012-3456789",
            "business_type": "Manufacturing",
            "occupation": "Factory",
            "construction_type": "Reinforced Concrete",
            "building_area_sqft": 50000,
            "sum_insured_building": 5000000,
            "sum_insured_contents": 2000000,
            "sum_insured_machinery": 3000000,
            "year_built": 2015,
            "security_features": "Sprinkler System, Alarm, CCTV, 24hr Guard",
            "policy_period_months": 12,
            "commencement_date": datetime.now().strftime("%Y-%m-%d"),
            "territory": "Malaysia (Peninsular)",
            "deductible": 1000,
        }

    # ── QuoteAdapter Interface ────────────────────────────────

    async def create_quote(self, request: QuoteRequest) -> QuoteResult:
        """Create a new mock quotation.

        Simulates launching the quote system and returning
        a quote reference number.
        """
        await self._simulate_delay()

        error = self._simulate_failure()
        if error:
            return QuoteResult(
                status=QuoteStatus.ERROR,
                errors=[error],
            )

        self._quote_counter += 1
        quote_no = f"MOCK-{datetime.now().strftime('%Y%m')}-{self._quote_counter:04d}"

        # Generate mock form data based on request
        self._active_quote = {
            "quote_number": quote_no,
            "request": request,
            "form_data": self._generate_mock_form_data(),
            "created_at": datetime.now().isoformat(),
        }

        return QuoteResult(
            status=QuoteStatus.DRAFT,
            quote_number=quote_no,
            message=f"Mock quote {quote_no} created successfully.",
        )

    async def calculate(self, request: QuoteRequest) -> QuoteResult:
        """Calculate premium for a mock quotation."""
        self._assert_write_permitted()
        await self._simulate_delay()

        error = self._simulate_failure()
        if error:
            return QuoteResult(
                status=QuoteStatus.ERROR,
                errors=[error],
            )

        premium = self._calculate_premium(request)

        if not self._active_quote:
            self._active_quote = {
                "request": request,
                "form_data": self._generate_mock_form_data(),
                "created_at": datetime.now().isoformat(),
            }

        self._active_quote["premium"] = premium
        self._active_quote["calculated_at"] = datetime.now().isoformat()

        quote_no = self._active_quote.get("quote_number", f"MOCK-{datetime.now().strftime('%Y%m')}-{self._quote_counter:04d}")

        return QuoteResult(
            status=QuoteStatus.CALCULATED,
            quote_number=quote_no,
            gross_premium=premium["gross_premium"],
            net_premium=premium["gross_premium"],
            stamp_duty=premium["stamp_duty"],
            tax_amount=premium["service_tax"],
            total_premium=premium["total_premium"],
            breakdown={
                "gross_premium": premium["gross_premium"],
                "stamp_duty": premium["stamp_duty"],
                "service_tax": premium["service_tax"],
                "sum_insured": premium["sum_insured"],
            },
            raw_response={
                "risk_class": request.risk_class or "unknown",
            },
            message="Premium calculated successfully.",
        )

    async def save_draft(self, quote_number: str) -> Optional[QuoteDraft]:
        """Save the current quote as a draft."""
        self._assert_write_permitted()
        await self._simulate_delay()

        draft_id = f"DRFT-{quote_number}"

        draft = QuoteDraft(
            draft_id=draft_id,
            quote_number=quote_number,
            channel_type="MOCK",
            portal="mock",
            status=QuoteStatus.SAVED,
            data=self._active_quote.get("form_data", {}) if self._active_quote else {},
        )

        self._drafts[quote_number] = draft
        return draft

    async def submit(self, quote_number: str) -> QuoteResult:
        """Submit a mock quotation."""
        self._assert_write_permitted()
        await self._simulate_delay()

        error = self._simulate_failure()
        if error:
            return QuoteResult(
                status=QuoteStatus.ERROR,
                errors=[error],
            )

        return QuoteResult(
            status=QuoteStatus.SUBMITTED,
            quote_number=quote_number,
            message=f"Mock quote {quote_number} submitted successfully.",
        )

    async def resume_draft(self, quote_number: str) -> Optional[QuoteDraft]:
        """Resume a previously saved draft."""
        await self._simulate_delay()

        if quote_number in self._drafts:
            draft = self._drafts[quote_number]
            self._active_quote = {
                "quote_number": quote_number,
                "form_data": draft.data,
                "resumed_at": datetime.now().isoformat(),
            }
            return draft

        return None

    async def health_check(self) -> Dict[str, Any]:
        base = await super().health_check()
        base.update({
            "name": self.name,
            "mode": self._mode.value,
            "quotes_created": self._quote_counter,
            "drafts_saved": len(self._drafts),
            "active_quote": self._active_quote is not None,
            "fail_rate": self._config.fail_rate,
        })
        return base

    # ── Test Helpers ───────────────────────────────────────────

    def reset(self):
        """Reset all mock state (for test isolation)."""
        self._quote_counter = 0
        self._drafts.clear()
        self._active_quote = None
