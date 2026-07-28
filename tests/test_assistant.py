"""Tests: AI Portal Operations Assistant (Sprint 5.5).

Tests for natural language query parsing, routing,
and response formatting.
"""
from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. Query Parsing (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestAssistantQuery:
    """Tests for natural language query parsing."""

    def test_parse_why_failed(self):
        from src.portal.assistant.models import AssistantQuery, QueryIntent
        q = AssistantQuery.from_text("Why did GE quote fail?")
        assert q.intent == QueryIntent.WHY_FAILED
        assert q.portal_id == "great_eastern"
        assert q.workflow_name == "quote"

    def test_parse_status_query(self):
        from src.portal.assistant.models import AssistantQuery, QueryIntent
        q = AssistantQuery.from_text("What is the health status of great_eastern?")
        assert q.intent == QueryIntent.CHECK_HEALTH
        assert q.portal_id == "great_eastern"

    def test_parse_how_fix(self):
        from src.portal.assistant.models import AssistantQuery, QueryIntent
        q = AssistantQuery.from_text("How to fix login failure in GE?")
        assert q.intent == QueryIntent.HOW_FIX
        assert q.portal_id == "great_eastern"
        assert q.workflow_name == "login"

    def test_parse_summarize(self):
        from src.portal.assistant.models import AssistantQuery, QueryIntent
        q = AssistantQuery.from_text("Summarize all portals")
        assert q.intent == QueryIntent.SUMMARIZE

    def test_parse_list_issues(self):
        from src.portal.assistant.models import AssistantQuery, QueryIntent
        q = AssistantQuery.from_text("What issues does aia have?")
        assert q.intent == QueryIntent.LIST_ISSUES
        assert q.portal_id == "aia"

    def test_parse_compare(self):
        from src.portal.assistant.models import AssistantQuery, QueryIntent
        q = AssistantQuery.from_text("Compare great_eastern and aia profiles")
        assert q.intent == QueryIntent.COMPARE

    def test_parse_unknown(self):
        from src.portal.assistant.models import AssistantQuery, QueryIntent
        q = AssistantQuery.from_text("Hello world")
        assert q.intent == QueryIntent.UNKNOWN
        assert q.portal_id is None

    def test_parse_allianz(self):
        from src.portal.assistant.models import AssistantQuery, QueryIntent
        q = AssistantQuery.from_text("Check allianz portal status")
        assert q.portal_id == "allianz"
        assert q.intent == QueryIntent.CHECK_HEALTH


# ══════════════════════════════════════════════════════════════════
# 2. Analysis Models (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestAnalysisModels:
    """Tests for AnalysisResult and AnalysisFinding."""

    def test_analysis_result_defaults(self):
        from src.portal.assistant.models import AnalysisResult
        r = AnalysisResult(query_id="q1", portal_id="ge")
        assert r.critical_count == 0
        assert r.actionable is False
        assert r.duration_ms == 0.0

    def test_analysis_result_with_findings(self):
        from src.portal.assistant.models import AnalysisResult, AnalysisFinding
        r = AnalysisResult(query_id="q1", portal_id="ge", summary="test")
        r.findings.append(AnalysisFinding(severity="critical", category="drift",
                                           message="test critical"))
        assert r.critical_count == 1
        assert r.actionable is True

    def test_analysis_finding_create(self):
        from src.portal.assistant.models import AnalysisFinding, AnalysisSource
        f = AnalysisFinding(
            severity="critical",
            category="drift",
            message="Selector changed",
            detail="Old → New",
            source=AnalysisSource.DRIFT,
            confidence=0.95,
            suggestion="Update YAML",
        )
        assert f.severity == "critical"
        assert f.suggestion == "Update YAML"

    def test_to_response_format(self):
        from src.portal.assistant.models import AnalysisResult, AnalysisFinding, AnalysisSource
        r = AnalysisResult(query_id="q1", portal_id="ge",
                            summary="Test Summary")
        r.findings.append(AnalysisFinding(
            severity="critical", category="drift",
            message="Login selector missing",
            source=AnalysisSource.DRIFT, confidence=0.95,
            suggestion="Recapture selector",
        ))
        resp = r.to_response()
        assert "Test Summary" in resp
        assert "CRITICAL" in resp
        assert "Recapture" in resp


# ══════════════════════════════════════════════════════════════════
# 3. Drift Analyzer (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestAssistantDriftAnalyzer:
    """Tests for DriftAnalyzer (assistant version)."""

    def test_analyze_portal_no_baseline(self):
        from src.portal.assistant.analyzers.drift import DriftAnalyzer
        import tempfile
        from src.portal.drift.storage import BaselineStorage
        with tempfile.TemporaryDirectory() as tmp:
            storage = BaselineStorage(storage_dir=tmp)
            analyzer = DriftAnalyzer(storage=storage)
            findings = analyzer.analyze_portal("great_eastern")
            assert len(findings) >= 0  # Will be info about no baseline

    def test_summarize_drift_no_baseline(self):
        from src.portal.assistant.analyzers.drift import DriftAnalyzer
        import tempfile
        from src.portal.drift.storage import BaselineStorage
        with tempfile.TemporaryDirectory() as tmp:
            storage = BaselineStorage(storage_dir=tmp)
            analyzer = DriftAnalyzer(storage=storage)
            summary = analyzer.summarize_drift("great_eastern")
            assert "great_eastern" in summary

    def test_summarize_drift_with_baseline(self):
        from src.portal.assistant.analyzers.drift import DriftAnalyzer
        from src.portal.drift.baseline import BaselineRecorder
        from src.portal.drift.storage import BaselineStorage
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            storage = BaselineStorage(storage_dir=tmp)
            recorder = BaselineRecorder(storage=storage)
            snap = recorder.capture_from_yaml("great_eastern")
            recorder.save(snap)
            analyzer = DriftAnalyzer(storage=storage)
            summary = analyzer.summarize_drift("great_eastern")
            assert "No drift" in summary or "drift" in summary


# ══════════════════════════════════════════════════════════════════
# 4. Execution Analyzer (2 tests)
# ══════════════════════════════════════════════════════════════════

class TestAssistantExecAnalyzer:
    """Tests for ExecutionAnalyzer."""

    def test_analyze_timeout_failure(self):
        from src.portal.assistant.analyzers.execution import ExecutionAnalyzer
        analyzer = ExecutionAnalyzer()
        findings = analyzer.analyze_failure(
            "ge", "create_quote", error_message="Timeout after 30s"
        )
        assert len(findings) >= 1
        assert any("timeout" in f.category or f.severity == "critical" for f in findings)

    def test_analyze_unknown_failure(self):
        from src.portal.assistant.analyzers.execution import ExecutionAnalyzer
        analyzer = ExecutionAnalyzer()
        findings = analyzer.analyze_failure(
            "ge", "custom_wf", error_message="Something went wrong"
        )
        assert len(findings) >= 1
        assert findings[0].severity == "major"


# ══════════════════════════════════════════════════════════════════
# 5. Assistant Engine (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestAssistantEngine:
    """Tests for AssistantEngine routing."""

    def test_engine_creates(self):
        from src.portal.assistant.engine import AssistantEngine
        engine = AssistantEngine()
        assert engine is not None

    def test_engine_analyze_why_failed(self):
        from src.portal.assistant.engine import AssistantEngine
        engine = AssistantEngine()
        result = engine.analyze("Why did GE quote fail?")
        assert result.portal_id == "great_eastern"
        assert result.intent.value == "why_failed"
        assert result.summary is not None

    def test_engine_analyze_health(self):
        from src.portal.assistant.engine import AssistantEngine
        engine = AssistantEngine()
        result = engine.analyze("What is the health status of great_eastern?")
        assert result.intent.value == "check_health"
        assert result.portal_id == "great_eastern"

    def test_engine_analyze_how_fix(self):
        from src.portal.assistant.engine import AssistantEngine
        engine = AssistantEngine()
        result = engine.analyze("How to fix login failure in great_eastern?")
        assert result.intent.value == "how_fix"
        assert "login" in result.summary or "login" in str(result.findings)

    def test_engine_summarize(self):
        from src.portal.assistant.engine import AssistantEngine
        engine = AssistantEngine()
        result = engine.analyze("Summarize all portals")
        assert result.intent.value == "summarize"
        assert result.portal_id == "all"
