"""Tests: Audit Module — ExecutionAudit, SensitiveDataProtector, CredentialAccessLogger."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ══════════════════════════════════════════════════════════════════
# 1. Audit Models
# ══════════════════════════════════════════════════════════════════


class TestAuditModels:
    def test_audit_entry_creation(self):
        from src.audit.models import AuditEntry, AuditLevel, AuditCategory

        entry = AuditEntry(
            level=AuditLevel.INFO,
            category=AuditCategory.WORKFLOW,
            action="workflow_started",
            actor="system",
            portal_id="great_eastern",
            workflow_id="wf_001",
            message="Test entry",
        )
        assert entry.id.startswith("audit_")
        assert entry.level == AuditLevel.INFO
        assert entry.category == AuditCategory.WORKFLOW
        assert entry.portal_id == "great_eastern"

    def test_audit_entry_summary(self):
        from src.audit.models import AuditEntry, AuditLevel, AuditCategory

        entry = AuditEntry(
            level=AuditLevel.ERROR,
            category=AuditCategory.WORKFLOW,
            action="workflow_failed",
            actor="system",
            message="Something broke",
            error="Connection timeout",
        )
        assert "ERROR" in entry.summary
        assert "Connection timeout" in entry.summary

    def test_approval_decision(self):
        from src.audit.models import ApprovalDecision

        decision = ApprovalDecision(
            action="submit_application",
            workflow_id="wf_001",
            portal_id="great_eastern",
            requested_by="system",
            approved_by="agent_001",
            decision="approved",
            amount=50000,
        )
        assert decision.id.startswith("aprv_")
        assert decision.decision == "approved"
        assert decision.approved_by == "agent_001"

    def test_audit_query(self):
        from src.audit.models import AuditQuery, AuditLevel, AuditCategory

        q = AuditQuery(
            level=AuditLevel.ERROR,
            category=AuditCategory.WORKFLOW,
            limit=50,
        )
        assert q.level == AuditLevel.ERROR
        assert q.category == AuditCategory.WORKFLOW
        assert q.limit == 50


# ══════════════════════════════════════════════════════════════════
# 2. SensitiveDataProtector
# ══════════════════════════════════════════════════════════════════


class TestSensitiveDataProtector:
    def test_redact_password(self):
        from src.audit.protector import SensitiveDataProtector

        p = SensitiveDataProtector()
        assert p.mask_value("password", "supersecret") == "[REDACTED]"
        assert p.mask_value("api_key", "abc123") == "[REDACTED]"

    def test_partial_mask_ic(self):
        from src.audit.protector import SensitiveDataProtector

        p = SensitiveDataProtector()
        result = p.mask_value("customer_ic", "881010-01-1234")
        assert result == "**********1234"
        assert "881010" not in result

    def test_partial_mask_phone(self):
        from src.audit.protector import SensitiveDataProtector

        p = SensitiveDataProtector()
        result = p.mask_value("customer_phone", "012-3456789")
        assert result.endswith("6789")
        assert "012" not in result

    def test_short_value_partial_mask(self):
        from src.audit.protector import SensitiveDataProtector

        p = SensitiveDataProtector()
        assert p.mask_value("ic_number", "ab") == "****"

    def test_non_sensitive_field_passes(self):
        from src.audit.protector import SensitiveDataProtector

        p = SensitiveDataProtector()
        assert p.mask_value("premium_amount", 1234.50) == 1234.50
        assert p.mask_value("coverage_type", "fire") == "fire"

    def test_mask_dict_nested(self):
        from src.audit.protector import SensitiveDataProtector

        p = SensitiveDataProtector()
        data = {
            "customer_name": "John Tan",
            "customer_ic": "881010-01-1234",
            "premium": 500.00,
            "address": {
                "street": "123 Jalan",
                "postcode": "50000",
            },
            "credentials": {
                "password": "secret123",
            },
        }
        masked = p.mask_dict(data)
        assert masked["customer_name"] == "John Tan"
        assert masked["customer_ic"] == "**********1234"
        assert masked["premium"] == 500.00
        assert masked["credentials"]["password"] == "[REDACTED]"
        # Original unchanged
        assert data["customer_ic"] == "881010-01-1234"

    def test_redact_entry(self):
        from src.audit.protector import SensitiveDataProtector
        from src.audit.models import AuditEntry, AuditLevel, AuditCategory

        p = SensitiveDataProtector()
        entry = AuditEntry(
            level=AuditLevel.INFO,
            category=AuditCategory.WORKFLOW,
            action="test",
            actor="system",
            details={"customer_ic": "881010-01-1234", "premium": 500},
        )
        redacted = p.redact_entry(entry)
        assert redacted.sensitive
        assert redacted.details["customer_ic"] == "**********1234"
        assert redacted.details["premium"] == 500

    def test_is_sensitive_field(self):
        from src.audit.protector import SensitiveDataProtector

        p = SensitiveDataProtector()
        assert p.is_sensitive_field("password")
        assert p.is_sensitive_field("customer_ic")
        assert p.is_sensitive_field("api_key")
        assert not p.is_sensitive_field("premium_amount")
        assert not p.is_sensitive_field("coverage_type")


# ══════════════════════════════════════════════════════════════════
# 3. CredentialAccessLogger
# ══════════════════════════════════════════════════════════════════


class TestCredentialAccessLogger:
    def test_log_access(self):
        from src.audit.protector import CredentialAccessLogger

        logger = CredentialAccessLogger()
        entry = logger.log_access(
            portal_id="great_eastern",
            actor="system",
            credential_type="vault",
            workflow_id="wf_001",
        )
        assert entry.category.value == "credential"
        assert "Credential accessed" in entry.message
        assert "vault" in entry.message

    def test_log_failure(self):
        from src.audit.protector import CredentialAccessLogger

        logger = CredentialAccessLogger()
        entry = logger.log_access_failure(
            portal_id="aia",
            actor="system",
            credential_type="vault",
            error="Invalid credentials",
        )
        assert entry.level.value == "error"
        assert "failed" in entry.action

    def test_recent_accesses(self):
        from src.audit.protector import CredentialAccessLogger

        logger = CredentialAccessLogger()
        logger.log_access(portal_id="ge", actor="sys", credential_type="vault")
        logger.log_access(portal_id="aia", actor="sys", credential_type="vault")
        recent = logger.get_recent_accesses(limit=1)
        assert len(recent) == 1
        assert recent[0].portal_id == "aia"


# ══════════════════════════════════════════════════════════════════
# 4. ExecutionAudit (in-memory)
# ══════════════════════════════════════════════════════════════════


class TestExecutionAudit:
    def test_workflow_lifecycle(self, tmp_path):
        from src.audit.trail import AuditStore, ExecutionAudit

        store = AuditStore(storage_path=str(tmp_path / "test_audit.json"))
        audit = ExecutionAudit(store=store)

        audit.log_workflow_start("wf_001", "great_eastern")
        audit.log_step("wf_001", "great_eastern", "validate_input", "success")
        audit.log_step("wf_001", "great_eastern", "create_quote", "success")
        audit.log_workflow_complete("wf_001", "great_eastern", "completed")

        recent = audit.recent(limit=10)
        assert len(recent) == 4

    def test_recent_returns_latest_first(self, tmp_path):
        from src.audit.trail import AuditStore, ExecutionAudit

        store = AuditStore(storage_path=str(tmp_path / "recent_test.json"))
        audit = ExecutionAudit(store=store)

        audit.log_workflow_start("wf_001", "ge")
        audit.log_workflow_start("wf_002", "aia")
        audit.log_workflow_start("wf_003", "allianz")

        recent = audit.recent(limit=2)
        assert len(recent) == 2
        assert recent[0].workflow_id == "wf_003"
        assert recent[1].workflow_id == "wf_002"

    def test_query_by_level(self, tmp_path):
        from src.audit.models import AuditLevel, AuditQuery
        from src.audit.trail import AuditStore, ExecutionAudit

        store = AuditStore(storage_path=str(tmp_path / "query_test.json"))
        audit = ExecutionAudit(store=store)

        audit.log_workflow_start("wf_001", "ge")
        audit.log_workflow_failed("wf_002", "ge", "error", "login")

        q = AuditQuery(level=AuditLevel.ERROR)
        results = audit.query(q)
        assert len(results) == 1
        assert results[0].action == "workflow_failed"

    def test_query_by_portal(self, tmp_path):
        from src.audit.models import AuditQuery
        from src.audit.trail import AuditStore, ExecutionAudit

        store = AuditStore(storage_path=str(tmp_path / "portal_test.json"))
        audit = ExecutionAudit(store=store)

        audit.log_workflow_start("wf_001", "great_eastern")
        audit.log_workflow_start("wf_002", "aia")
        audit.log_workflow_start("wf_003", "great_eastern")

        q = AuditQuery(portal_id="great_eastern")
        results = audit.query(q)
        assert len(results) == 2

    def test_validation_log(self, tmp_path):
        from src.audit.models import AuditQuery
        from src.audit.trail import AuditStore, ExecutionAudit

        store = AuditStore(storage_path=str(tmp_path / "val_test.json"))
        audit = ExecutionAudit(store=store)

        audit.log_validation("wf_001", "ge", True, [])
        audit.log_validation("wf_002", "ge", False, ["Sum insured too high"])

        q = AuditQuery(portal_id="ge")
        entries = audit.query(q)
        validation_entries = [e for e in entries if e.action == "validation_completed"]
        assert len(validation_entries) == 2
        assert validation_entries[0].level.value == "warning"

    def test_review_log(self, tmp_path):
        from src.audit.trail import AuditStore, ExecutionAudit

        store = AuditStore(storage_path=str(tmp_path / "review_test.json"))
        audit = ExecutionAudit(store=store)

        audit.log_review("wf_001", "ge", "All fields verified")
        entries = store.recent()
        assert any("review_completed" in e.action for e in entries)

    def test_approval_log(self, tmp_path):
        from src.audit.models import ApprovalDecision
        from src.audit.trail import AuditStore, ExecutionAudit

        store = AuditStore(storage_path=str(tmp_path / "approval_test.json"))
        audit = ExecutionAudit(store=store)

        decision = ApprovalDecision(
            action="submit_application",
            workflow_id="wf_001",
            portal_id="ge",
            requested_by="system",
            approved_by="agent_001",
            decision="approved",
        )
        audit.log_approval("wf_001", "ge", decision)

        entries = store.recent()
        assert len(entries) == 1
        assert "approval_approved" in entries[0].action

    def test_approval_rejected_log(self, tmp_path):
        from src.audit.models import ApprovalDecision
        from src.audit.trail import AuditStore, ExecutionAudit

        store = AuditStore(storage_path=str(tmp_path / "reject_test.json"))
        audit = ExecutionAudit(store=store)

        decision = ApprovalDecision(
            action="submit_application",
            workflow_id="wf_002",
            portal_id="ge",
            requested_by="system",
            approved_by="agent_001",
            decision="rejected",
            reason="Customer info incomplete",
        )
        audit.log_approval("wf_002", "ge", decision)

        entries = audit.recent()
        assert "approval_rejected" in entries[0].action
        assert entries[0].details.get("reason") == "Customer info incomplete"

    def test_audit_entry_is_logged_in_workflow(self, tmp_path):
        """Integration: QuoteWorkflow with audit trail."""
        from src.audit.trail import AuditStore, ExecutionAudit
        from src.workflow.quote import QuoteWorkflow
        from src.workflow.models import QuoteRequest

        store = AuditStore(storage_path=str(tmp_path / "wf_audit.json"))
        audit = ExecutionAudit(store=store)
        wf = QuoteWorkflow(audit_trail=audit)

        # Invalid request → should log failure
        req = QuoteRequest()
        wf.execute(req)

        entries = store.recent()
        assert len(entries) >= 2  # workflow_started + workflow_failed
        assert any(e.action == "workflow_failed" for e in entries)
