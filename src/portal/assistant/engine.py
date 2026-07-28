"""InsureDesk — AI Portal Operations Assistant: Engine.

Main orchestrator that takes natural language queries,
routes them to the appropriate analyzer, and returns
structured responses.
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from src.portal.assistant.models import (
    AssistantQuery, AnalysisResult, AnalysisFinding,
    QueryIntent, AnalysisSource,
)
from src.portal.assistant.analyzers import (
    DriftAnalyzer, ExecutionAnalyzer, HealthAnalyzer,
)
from src.portal.drift.detector import DriftDetector
from src.portal.drift.storage import BaselineStorage
from src.portal.profile.registry import ProfileManager
from src.portal.profile.versioning import VersionManager

logger = logging.getLogger("insuredesk.assistant.engine")


class AssistantEngine:
    """Main orchestrator for the AI Portal Operations Assistant.

    Takes natural language queries and returns structured analysis
    by leveraging drift detection, execution analysis, and health monitoring.

    Usage:
        engine = AssistantEngine()
        result = engine.analyze("Why did GE quote fail?")
        print(result.to_response())
    """

    def __init__(self, drift_analyzer: Optional[DriftAnalyzer] = None,
                 execution_analyzer: Optional[ExecutionAnalyzer] = None,
                 health_analyzer: Optional[HealthAnalyzer] = None):
        self._drift = drift_analyzer or DriftAnalyzer()
        self._execution = execution_analyzer or ExecutionAnalyzer()
        self._health = health_analyzer or HealthAnalyzer()

    def analyze(self, query_text: str) -> AnalysisResult:
        """Analyze a natural language query.

        Args:
            query_text: Natural language question (e.g. "Why did GE quote fail?")

        Returns:
            Structured AnalysisResult with findings and suggestions.
        """
        query = AssistantQuery.from_text(query_text)
        return self._route_query(query)

    def analyze_query(self, query: AssistantQuery) -> AnalysisResult:
        """Analyze a pre-parsed query."""
        return self._route_query(query)

    def _route_query(self, query: AssistantQuery) -> AnalysisResult:
        """Route query to the appropriate analyzer based on intent."""
        start = time.monotonic()
        portal_id = query.portal_id or "great_eastern"

        result = AnalysisResult(
            query_id=query.id,
            portal_id=portal_id,
            intent=query.intent,
        )

        try:
            if query.intent == QueryIntent.WHY_FAILED:
                result = self._handle_why_failed(query, portal_id)
            elif query.intent == QueryIntent.CHECK_HEALTH:
                result = self._handle_health(query, portal_id)
            elif query.intent == QueryIntent.HOW_FIX:
                result = self._handle_how_fix(query, portal_id)
            elif query.intent == QueryIntent.SUMMARIZE:
                result = self._handle_summarize(query)
            elif query.intent == QueryIntent.LIST_ISSUES:
                result = self._handle_list_issues(query, portal_id)
            elif query.intent == QueryIntent.COMPARE:
                result = self._handle_compare(query, portal_id)
            else:
                result = self._handle_general(query, portal_id)

        except Exception as e:
            logger.error(f"Query failed: {e}")
            result.error = str(e)
            result.summary = f"Analysis failed: {e}"

        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    def _handle_why_failed(self, query: AssistantQuery,
                            portal_id: str) -> AnalysisResult:
        """Handle 'why did X fail?' queries."""
        wf = query.workflow_name or "workflow"
        result = AnalysisResult(
            query_id=query.id, portal_id=portal_id,
            intent=QueryIntent.WHY_FAILED,
            summary=f"Analysis: Why '{wf}' failed for {portal_id}",
        )

        # Check drift (UI changes that could break workflow)
        drift_findings = self._drift.analyze_portal(portal_id, wf)
        result.findings.extend(drift_findings)
        if drift_findings:
            result.data_sources.append(AnalysisSource.DRIFT)

        # Check execution patterns if we have error context
        if query.context.get("error"):
            exec_findings = self._execution.analyze_failure(
                portal_id, wf, query.context.get("error")
            )
            result.findings.extend(exec_findings)
            result.data_sources.append(AnalysisSource.EXECUTION)

        result.confidence = 0.85 if any(f.severity == "critical" for f in result.findings) else 0.7

        # Generate suggestions
        for f in result.findings:
            if f.suggestion and f.severity in ("critical", "major"):
                result.suggestions.append({
                    "type": f.category,
                    "description": f.suggestion,
                })

        return result

    def _handle_health(self, query: AssistantQuery,
                        portal_id: str) -> AnalysisResult:
        """Handle health check queries."""
        result = AnalysisResult(
            query_id=query.id, portal_id=portal_id,
            intent=QueryIntent.CHECK_HEALTH,
            summary=f"Health Status: {portal_id}",
        )
        findings = self._health.check_health(portal_id)
        result.findings.extend(findings)
        result.data_sources = [AnalysisSource.HEALTH, AnalysisSource.DRIFT, AnalysisSource.VERSION]
        result.confidence = 0.9
        return result

    def _handle_how_fix(self, query: AssistantQuery,
                         portal_id: str) -> AnalysisResult:
        """Handle 'how to fix' queries."""
        wf = query.workflow_name or ""
        result = AnalysisResult(
            query_id=query.id, portal_id=portal_id,
            intent=QueryIntent.HOW_FIX,
            summary=f"Suggested Fixes for {portal_id}"
                     + (f" ({wf})" if wf else ""),
        )

        # Find all actionable drift
        drift_findings = self._drift.analyze_portal(portal_id, wf)
        for f in drift_findings:
            if f.severity in ("critical", "major"):
                result.findings.append(f)
                if f.suggestion:
                    result.suggestions.append({
                        "type": "fix",
                        "description": f.suggestion,
                    })

        result.data_sources.append(AnalysisSource.DRIFT)
        result.confidence = 0.8
        return result

    def _handle_summarize(self, query: AssistantQuery) -> AnalysisResult:
        """Handle summarize/overview queries."""
        result = AnalysisResult(
            query_id=query.id, portal_id="all",
            intent=QueryIntent.SUMMARIZE,
            summary="Portal Operations Summary",
        )
        summary_text = self._health.summarize_all()
        result.findings.append(AnalysisFinding(
            severity="info",
            category="summary",
            message=summary_text,
            source=AnalysisSource.HEALTH,
            confidence=0.9,
        ))
        result.data_sources = [AnalysisSource.HEALTH, AnalysisSource.DRIFT]
        return result

    def _handle_list_issues(self, query: AssistantQuery,
                              portal_id: str) -> AnalysisResult:
        """Handle 'list issues/problems' queries."""
        result = AnalysisResult(
            query_id=query.id, portal_id=portal_id,
            intent=QueryIntent.LIST_ISSUES,
            summary=f"Current Issues: {portal_id}",
        )
        drift_findings = self._drift.analyze_portal(portal_id)
        critical = [f for f in drift_findings if f.severity == "critical"]
        major = [f for f in drift_findings if f.severity == "major"]

        if critical:
            result.findings.append(AnalysisFinding(
                severity="critical",
                category="summary",
                message=f"{len(critical)} critical issues found",
                source=AnalysisSource.DRIFT,
                confidence=0.9,
            ))
        if major:
            result.findings.append(AnalysisFinding(
                severity="major",
                category="summary",
                message=f"{len(major)} non-critical issues found",
                source=AnalysisSource.DRIFT,
                confidence=0.9,
            ))

        result.findings.extend(critical + major)
        result.data_sources.append(AnalysisSource.DRIFT)
        result.confidence = 0.85
        return result

    def _handle_compare(self, query: AssistantQuery,
                         portal_id: str) -> AnalysisResult:
        """Handle comparison queries."""
        result = AnalysisResult(
            query_id=query.id, portal_id=portal_id,
            intent=QueryIntent.COMPARE,
            summary=f"Comparison not yet implemented for {portal_id}",
        )
        result.confidence = 0.5
        return result

    def _handle_general(self, query: AssistantQuery,
                         portal_id: str) -> AnalysisResult:
        """Handle general/generic queries."""
        result = AnalysisResult(
            query_id=query.id, portal_id=portal_id,
            intent=QueryIntent.UNKNOWN,
            summary=f"General inquiry about {portal_id}",
        )
        # Provide health info as default
        findings = self._health.check_health(portal_id)
        result.findings.extend(findings)
        result.data_sources = [AnalysisSource.HEALTH]
        result.confidence = 0.7
        return result
