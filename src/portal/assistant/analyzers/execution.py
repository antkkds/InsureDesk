"""Assistant — Execution Analyzer.

Analyzes execution results to explain why
specific workflows or steps failed.
"""
from __future__ import annotations

from typing import List, Optional

from src.portal.assistant.models import (
    AnalysisFinding, AnalysisSource, AnalysisResult,
)


class ExecutionAnalyzer:
    """Analyzes execution data to find failure causes."""

    def analyze_failure(self, portal_id: str,
                         workflow_name: str,
                         error_message: Optional[str] = None,
                         step_name: Optional[str] = None) -> List[AnalysisFinding]:
        """Analyze a workflow failure and produce findings.

        Args:
            portal_id: Portal where failure occurred.
            workflow_name: Which workflow failed.
            error_message: Error text from execution.
            step_name: Which step failed.

        Returns:
            List of findings.
        """
        findings: List[AnalysisFinding] = []
        error_lower = (error_message or "").lower()

        # Check for common failure patterns
        patterns = [
            ("timeout", "Timeout", "critical",
             "Workflow timed out — network or portal may be slow",
             "Increase timeout or check portal availability"),
            ("selector", "Selector Not Found", "critical",
             "Portal UI element no longer matches expected selector",
             "Run drift detection to find new selector"),
            ("login", "Login Failed", "critical",
             "Authentication failed — session may be expired",
             "Re-login or check credentials"),
            ("session", "Session Expired", "major",
             "Session expired during workflow execution",
             "Implement recover_session() before retry"),
            ("not found", "Element Not Found", "critical",
             "Required page element is missing",
             "Check if portal UI changed"),
            ("network", "Network Error", "major",
             "Network connectivity issue",
             "Check portal availability and retry"),
            ("crash", "Browser Crash", "critical",
             "Browser engine disconnected unexpectedly",
             "Reconnect and restore session"),
        ]

        for keyword, title, severity, desc, suggestion in patterns:
            if keyword in error_lower:
                findings.append(AnalysisFinding(
                    severity=severity,
                    category="execution",
                    message=f"{title}: {workflow_name}",
                    detail=desc,
                    source=AnalysisSource.EXECUTION,
                    confidence=0.85,
                    suggestion=suggestion,
                    affected_items=[workflow_name],
                ))

        if not findings:
            # Generic failure finding
            findings.append(AnalysisFinding(
                severity="major",
                category="execution",
                message=f"Workflow '{workflow_name}' failed",
                detail=error_message or "Unknown error",
                source=AnalysisSource.EXECUTION,
                confidence=0.7,
                affected_items=[workflow_name],
            ))

        return findings

    def summarize_executions(self, portal_id: str,
                               recent_results: Optional[List[dict]] = None) -> str:
        """Summarize recent execution results."""
        if not recent_results:
            return f"ℹ️ {portal_id}: No recent execution data available"
        passed = sum(1 for r in recent_results if r.get("status") == "passed")
        failed = sum(1 for r in recent_results if r.get("status") == "failed")
        total = len(recent_results)
        if total == 0:
            return f"ℹ️ {portal_id}: No executions recorded"
        return (
            f"{'✅' if failed == 0 else '❌'} "
            f"{portal_id}: {passed}/{total} passed"
            f"{f', {failed} failed' if failed else ', all passing'}"
        )
