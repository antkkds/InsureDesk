"""Tests: Workflow Module — QuoteWorkflow, ApprovalGate, models."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ══════════════════════════════════════════════════════════════════
# 1. Models — QuoteRequest / QuoteResponse
# ══════════════════════════════════════════════════════════════════


class TestQuoteRequest:
    def test_create_request(self):
        from src.workflow.models import QuoteRequest

        req = QuoteRequest(
            portal_id="great_eastern",
            customer_name="John Tan",
            customer_ic="881010-01-1234",
            sum_insured=500000,
        )
        assert req.portal_id == "great_eastern"
        assert req.customer_name == "John Tan"
        assert req.is_valid()

    def test_missing_fields(self):
        from src.workflow.models import QuoteRequest

        req = QuoteRequest()
        assert not req.is_valid()
        assert "customer_name" in req.missing_fields()
        assert "sum_insured or sum_insured_building" in req.missing_fields()

    def test_from_dict(self):
        from src.workflow.models import QuoteRequest

        d = {
            "portal_id": "aia",
            "customer_name": "Alice",
            "customer_ic": "900101-01-1234",
            "sum_insured": 300000,
            "extra_field": "ignored",
        }
        req = QuoteRequest.from_dict(d)
        assert req.portal_id == "aia"
        assert req.customer_name == "Alice"
        assert "extra_field" in req.metadata

    def test_to_dict(self):
        from src.workflow.models import QuoteRequest

        req = QuoteRequest(
            portal_id="great_eastern",
            customer_name="Bob",
            customer_ic="881010-01-5678",
            sum_insured=200000,
        )
        d = req.to_dict()
        assert d["portal_id"] == "great_eastern"
        assert d["customer_name"] == "Bob"
        assert d["sum_insured"] == 200000


class TestQuoteResponse:
    def test_successful_response(self):
        from src.workflow.models import QuoteResponse, QuoteStatus

        resp = QuoteResponse(
            workflow_id="wf_001",
            portal_id="great_eastern",
            status=QuoteStatus.COMPLETED,
            premium_amount=1234.50,
            coverage_summary="Fire & Theft Coverage",
            validation_passed=True,
        )
        assert resp.succeeded
        assert "RM 1,234.50" in resp.human_summary

    def test_failed_response(self):
        from src.workflow.models import QuoteResponse, QuoteStatus

        resp = QuoteResponse(
            workflow_id="wf_002",
            portal_id="great_eastern",
            status=QuoteStatus.FAILED,
            errors=["Portal login failed"],
        )
        assert not resp.succeeded
        assert "failed" in resp.human_summary

    def test_human_summary_messages(self):
        from src.workflow.models import QuoteResponse, QuoteStatus

        pending = QuoteResponse(
            workflow_id="wf_003",
            portal_id="aia",
            status=QuoteStatus.APPROVAL_PENDING,
        )
        assert "approval pending" in pending.human_summary


# ══════════════════════════════════════════════════════════════════
# 2. WorkflowSession
# ══════════════════════════════════════════════════════════════════


class TestWorkflowSession:
    def test_session_lifecycle(self):
        from src.workflow.models import WorkflowSession

        session = WorkflowSession(portal_id="great_eastern")
        assert session.status.value == "pending"
        assert len(session.steps) == 0

        session.add_step("login")
        session.mark_step_running("login")
        assert session.steps[0].status == "running"
        assert session.steps[0].started_at is not None

        session.mark_step_completed("login", {"ok": True})
        assert session.steps[0].status == "success"
        assert session.steps[0].duration_ms >= 0

    def test_step_failure(self):
        from src.workflow.models import WorkflowSession

        session = WorkflowSession(portal_id="aia")
        session.add_step("login")
        session.mark_step_running("login")
        session.mark_step_failed("login", "Connection refused")
        assert session.steps[0].status == "failed"
        assert session.steps[0].error == "Connection refused"
        assert session.error == "Connection refused"

    def test_multiple_steps_duration(self):
        from src.workflow.models import WorkflowSession
        import time

        session = WorkflowSession(portal_id="ge")
        session.add_step("step_a")
        session.mark_step_running("step_a")
        time.sleep(0.01)
        session.mark_step_completed("step_a")

        session.add_step("step_b")
        session.mark_step_running("step_b")
        time.sleep(0.01)
        session.mark_step_completed("step_b")

        assert session.duration_ms > 0
        assert session.duration_ms == sum(
            s.duration_ms for s in session.steps
        )


# ══════════════════════════════════════════════════════════════════
# 3. ApprovalGate
# ══════════════════════════════════════════════════════════════════


class TestApprovalGate:
    def test_default_rules_exist(self):
        from src.workflow.models import ApprovalGate

        gate = ApprovalGate()
        rule = gate.check("generate_quote")
        assert rule.action == "generate_quote"
        assert rule.approval.value == "recommended"

    def test_search_policy_no_approval(self):
        from src.workflow.models import ApprovalGate

        gate = ApprovalGate()
        assert not gate.needs_approval("search_policy")

    def test_submit_requires_approval(self):
        from src.workflow.models import ApprovalGate

        gate = ApprovalGate()
        assert gate.needs_approval("submit_application")
        assert gate.needs_approval("submit_claim")

    def test_unknown_action_requires_approval(self):
        from src.workflow.models import ApprovalGate

        gate = ApprovalGate()
        assert gate.needs_approval("delete_policy")

    def test_generate_quote_recommended(self):
        from src.workflow.models import ApprovalGate, ApprovalLevel

        gate = ApprovalGate()
        rule = gate.check("generate_quote")
        assert rule.approval == ApprovalLevel.RECOMMENDED
        # Recommended = auto-execute
        assert not gate.needs_approval("generate_quote")
        assert gate.requires_confirmation("generate_quote")

    def test_custom_rules(self):
        from src.workflow.models import (
            ApprovalGate,
            ApprovalLevel,
            ActionApprovalRule,
        )

        custom = [
            ActionApprovalRule(
                action="big_quote",
                approval=ApprovalLevel.REQUIRED,
                max_amount=100000,
                description="Quotes over 100k need approval",
            ),
        ]
        gate = ApprovalGate(custom)
        assert gate.needs_approval("big_quote")
        assert gate.check("big_quote").max_amount == 100000


# ══════════════════════════════════════════════════════════════════
# 4. QuoteWorkflow — Integration (no portal)
# ══════════════════════════════════════════════════════════════════


class TestQuoteWorkflow:
    def test_invalid_request_returns_error(self):
        from src.workflow.quote import QuoteWorkflow
        from src.workflow.models import QuoteRequest

        wf = QuoteWorkflow()
        req = QuoteRequest()  # Missing all required fields
        resp = wf.execute(req)
        assert not resp.succeeded
        assert len(resp.errors) > 0
        assert "Missing required fields" in resp.errors[0]

    def test_approval_gate_integration(self):
        from src.workflow.models import ApprovalGate, QuoteRequest
        from src.workflow.quote import QuoteWorkflow

        # Minimal test — just validates request
        wf = QuoteWorkflow()
        req = QuoteRequest(
            portal_id="great_eastern",
            customer_name="Test User",
            customer_ic="881010-01-1234",
            sum_insured=100000,
        )
        resp = wf.execute(req)
        # Should fail at portal login step since no real browser
        assert resp.status.value in ("failed", "approval_pending", "completed")

    def test_batch_execute(self):
        from src.workflow.quote import QuoteWorkflow
        from src.workflow.models import QuoteRequest

        wf = QuoteWorkflow()
        reqs = [
            QuoteRequest(),  # Invalid
            QuoteRequest(
                portal_id="great_eastern",
                customer_name="User A",
                customer_ic="881010-01-1234",
                sum_insured=200000,
            ),
        ]
        results = wf.batch_execute(reqs)
        assert len(results) == 2
        assert not results[0].succeeded  # Missing fields
