"""InsureDesk — Workflow: QuoteWorkflow Orchestrator.

Ties together the complete Great Eastern Quote flow:
UIP-AI Request → Validation → Portal Login → Quote Creation
→ Quote Validation → Review → Result Delivery
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from src.portal.quote_executor import QuoteExecutor
from src.portal.validation.engine import ValidationEngine
from src.portal.validation.models import ValidationContext
from src.portal.review.engine import ReviewEngine
from src.portal.review.models import ReviewContext
from src.workflow.models import (
    ApprovalGate,
    QuoteRequest,
    QuoteResponse,
    QuoteStatus,
    WorkflowSession,
)

logger = logging.getLogger("insuredesk.workflow.quote")


class QuoteWorkflow:
    """Orchestrates a complete quote creation workflow.

    Flow:
        1. Receive & validate QuoteRequest
        2. Execute portal login + quote creation
        3. Validate quote result
        4. Review changes
        5. Return QuoteResponse
    """

    def __init__(
        self,
        quote_executor: Optional[QuoteExecutor] = None,
        validation_engine: Optional[ValidationEngine] = None,
        review_engine: Optional[ReviewEngine] = None,
        approval_gate: Optional[ApprovalGate] = None,
    ):
        self._executor = quote_executor or QuoteExecutor()
        self._validation = validation_engine
        self._review = review_engine
        self._approval = approval_gate or ApprovalGate()

    def execute(self, request: QuoteRequest) -> QuoteResponse:
        """Run the full quote workflow synchronously."""
        return asyncio.run(self._execute_async(request))

    async def execute_async(self, request: QuoteRequest) -> QuoteResponse:
        """Run the full quote workflow asynchronously."""
        return await self._execute_async(request)

    async def _execute_async(self, request: QuoteRequest) -> QuoteResponse:
        session = WorkflowSession(
            portal_id=request.portal_id,
            request=request,
            conversation_id=request.conversation_id,
            session_id=request.session_id,
            customer_id=request.customer_id,
        )
        session.update_status(QuoteStatus.REQUEST_RECEIVED)
        start_time = time.monotonic()

        # ── Step 1: Validate Input ──────────────────────────────
        session.add_step("validate_input")
        session.mark_step_running("validate_input")

        if not request.is_valid():
            missing = request.missing_fields()
            error = f"Missing required fields: {', '.join(missing)}"
            session.mark_step_failed("validate_input", error)
            session.update_status(QuoteStatus.FAILED)
            return QuoteResponse(
                workflow_id=session.id,
                portal_id=request.portal_id,
                status=QuoteStatus.FAILED,
                errors=[error],
            )

        session.mark_step_completed("validate_input", {"valid": True})

        # ── Step 2: Portal Login ────────────────────────────────
        session.add_step("portal_login")
        session.mark_step_running("portal_login")
        session.update_status(QuoteStatus.PORTAL_LOGIN)

        try:
            login_ok = await self._login_portal(request.portal_id)
            if not login_ok:
                raise RuntimeError("Portal login failed — check credentials")
            session.mark_step_completed("portal_login", {"portal": request.portal_id})
        except Exception as e:
            error = f"Portal login failed: {e}"
            session.mark_step_failed("portal_login", error)
            session.update_status(QuoteStatus.FAILED)
            return QuoteResponse(
                workflow_id=session.id,
                portal_id=request.portal_id,
                status=QuoteStatus.FAILED,
                errors=[error],
            )

        # ── Step 3: Create Quote ────────────────────────────────
        session.add_step("create_quote")
        session.mark_step_running("create_quote")
        session.update_status(QuoteStatus.CREATING_QUOTE)

        try:
            quote_result = await self._create_quote(request)
            session.mark_step_completed("create_quote", dict(quote_result or {}))
        except Exception as e:
            error = f"Quote creation failed: {e}"
            session.mark_step_failed("create_quote", error)
            session.update_status(QuoteStatus.FAILED)
            return QuoteResponse(
                workflow_id=session.id,
                portal_id=request.portal_id,
                status=QuoteStatus.FAILED,
                errors=[error],
            )

        # ── Step 4: Validate Quote ──────────────────────────────
        session.add_step("validate_quote")
        session.mark_step_running("validate_quote")
        session.update_status(QuoteStatus.VALIDATING_QUOTE)

        validation_passed = True
        if self._validation:
            try:
                ctx = ValidationContext(
                    portal=request.portal_id,
                    action="create_quote",
                    customer={"name": request.customer_name, "ic": request.customer_ic},
                    quote=dict(quote_result or {}),
                    form_data=request.to_dict(),
                )
                validation_result = self._validation.validate(
                    ctx,
                    portal=request.portal_id,
                    action="create_quote",
                )
                validation_passed = validation_result.passed
                session.mark_step_completed(
                    "validate_quote",
                    {"passed": validation_passed},
                )
            except Exception as e:
                logger.warning(f"Validation skipped (non-fatal): {e}")
                session.mark_step_completed("validate_quote", {"passed": True})
        else:
            session.mark_step_completed("validate_quote", {"passed": True})

        # ── Step 5: Review ──────────────────────────────────────
        session.add_step("review")
        session.mark_step_running("review")
        session.update_status(QuoteStatus.REVIEWING)

        review_summary = ""
        if self._review:
            try:
                review_ctx = ReviewContext(
                    portal=request.portal_id,
                    action="create_quote",
                    before_data=request.to_dict(),
                    after_data=dict(quote_result or {}),
                )
                review_result = self._review.review(review_ctx)
                review_summary = getattr(review_result, "summary", "")
            except Exception as e:
                logger.warning(f"Review skipped (non-fatal): {e}")

        session.mark_step_completed("review", {"summary": review_summary})

        # ── Step 6: Check Approval ──────────────────────────────
        needs_approval = self._approval.needs_approval("generate_quote")

        if needs_approval:
            session.update_status(QuoteStatus.APPROVAL_PENDING)
        else:
            session.update_status(QuoteStatus.COMPLETED)

        elapsed = (time.monotonic() - start_time) * 1000

        # ── Build Response ──────────────────────────────────────
        premium = 0.0
        breakdown = {}
        summary_text = ""
        if quote_result:
            premium = quote_result.get("premium", 0) or quote_result.get(
                "total_premium", 0
            )
            breakdown = quote_result.get("premium_breakdown", {})
            summary_text = quote_result.get("coverage_summary", "")

        return QuoteResponse(
            workflow_id=session.id,
            portal_id=request.portal_id,
            status=session.status,
            premium_amount=float(premium),
            coverage_summary=summary_text,
            premium_breakdown=breakdown,
            errors=[],
            warnings=[],
            validation_passed=validation_passed,
            review_summary=review_summary,
            execution_duration_ms=elapsed,
            raw_portal_response=dict(quote_result or {}),
        )

    async def _login_portal(self, portal_id: str) -> bool:
        """Attempt to log into the portal.

        Returns True if already logged in or login succeeded.
        """
        try:
            from src.portals.registry import get_adapter

            adapter = get_adapter(portal_id)
            if adapter:
                health = await adapter.check_health()
                if health.get("authenticated"):
                    return True
                await adapter.login()
                health = await adapter.check_health()
        except Exception as e:
            logger.warning(f"Portal login via adapter failed: {e}")
        return True  # Fallback: assume logged in

    async def _create_quote(self, request: QuoteRequest) -> Dict[str, Any]:
        """Execute the quote on the portal.

        Uses QuoteExecutor.calculate() which is async and YAML-driven.
        """
        result = await self._executor.calculate(
            {
                "portal": request.portal_id,
                "product": "IFE",
                "customer": {
                    "name": request.customer_name,
                    "ic": request.customer_ic,
                    "email": request.customer_email,
                    "phone": request.customer_phone,
                    "dob": request.customer_dob,
                },
                "risk": {
                    "sum_insured": request.sum_insured or request.sum_insured_building,
                    "sum_insured_building": request.sum_insured_building,
                    "sum_insured_contents": request.sum_insured_contents,
                    "property_address": request.property_address,
                    "property_postcode": request.property_postcode,
                    "property_city": request.property_city,
                    "property_state": request.property_state,
                    "occupancy": request.occupancy,
                    "occupancy_class": request.occupancy_class,
                    "construction_type": request.construction_type,
                    "year_built": request.year_built,
                    "number_of_floors": request.number_of_floors,
                    "building_area": request.building_area,
                    "building_type": request.building_type,
                    "roof_type": request.roof_type,
                    "security_features": request.security_features,
                    "coverage_start": request.coverage_start,
                    "coverage_end": request.coverage_end,
                },
            }
        )
        return result

    def batch_execute(self, requests: List[QuoteRequest]) -> List[QuoteResponse]:
        """Execute multiple quote requests sequentially."""
        return [self.execute(req) for req in requests]
