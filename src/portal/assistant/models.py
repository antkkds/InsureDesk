"""InsureDesk — AI Portal Operations Assistant: Data Models.

Models for natural language queries, structured analysis results,
and formatted responses for the AI assistant.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class QueryIntent(Enum):
    """Types of queries the assistant can handle."""
    WHY_FAILED = "why_failed"
    WHAT_STATUS = "what_status"
    HOW_FIX = "how_fix"
    SUMMARIZE = "summarize"
    LIST_ISSUES = "list_issues"
    CHECK_HEALTH = "check_health"
    COMPARE = "compare"
    UNKNOWN = "unknown"


class AnalysisSource(Enum):
    """Data sources used in an analysis."""
    DRIFT = "drift"
    EXECUTION = "execution"
    HEALTH = "health"
    PROFILE = "profile"
    E2E = "e2e"
    VERSION = "version"


class SuggestionType(Enum):
    """Types of suggestions the assistant can provide."""
    UPDATE_YAML = "update_yaml"
    RECAPTURE = "recapture"
    ROLLBACK = "rollback"
    UPGRADE = "upgrade"
    ACTIVATE = "activate"
    REVIEW = "review"
    MONITOR = "monitor"
    MANUAL = "manual"


@dataclass
class AssistantQuery:
    """A natural language query to the assistant."""
    id: str = field(default_factory=lambda: f"q_{uuid.uuid4().hex[:6]}")
    text: str = ""
    intent: QueryIntent = QueryIntent.UNKNOWN
    portal_id: Optional[str] = None
    workflow_name: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_text(cls, text: str) -> AssistantQuery:
        """Parse a natural language query and infer intent."""
        text_lower = text.lower()
        query = cls(text=text)

        # Infer portal
        for pid in ["great_eastern", "ge", "aia", "allianz"]:
            if pid in text_lower:
                if pid == "ge":
                    query.portal_id = "great_eastern"
                else:
                    query.portal_id = pid
                break

        # Infer intent — order matters (more specific first)
        if any(w in text_lower for w in ["how to fix", "how to", "how fix",
                                          "suggest", "fix this", "repair"]):
            query.intent = QueryIntent.HOW_FIX
        elif any(w in text_lower for w in ["why", "fail", "error", "broken", "not working"]):
            query.intent = QueryIntent.WHY_FAILED
        elif any(w in text_lower for w in ["status", "health", "how is", "state"]):
            query.intent = QueryIntent.CHECK_HEALTH
        elif any(w in text_lower for w in ["summarize", "summary", "overview", "all portals"]):
            query.intent = QueryIntent.SUMMARIZE
        elif any(w in text_lower for w in ["issues", "problems", "what wrong"]):
            query.intent = QueryIntent.LIST_ISSUES
        elif any(w in text_lower for w in ["compare", "diff", "different"]):
            query.intent = QueryIntent.COMPARE

        # Extract workflow name if mentioned
        for wf in ["quote", "claim", "policy", "renewal", "login", "search"]:
            if wf in text_lower:
                query.workflow_name = wf
                break

        return query


@dataclass
class AnalysisFinding:
    """A single finding from an analysis."""
    severity: str = "info"  # critical, major, minor, info
    category: str = ""
    message: str = ""
    detail: str = ""
    source: AnalysisSource = AnalysisSource.HEALTH
    confidence: float = 0.0
    suggestion: Optional[str] = None
    affected_items: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """Structured result from a portal analysis."""
    query_id: str = ""
    portal_id: str = ""
    intent: QueryIntent = QueryIntent.UNKNOWN
    summary: str = ""
    findings: List[AnalysisFinding] = field(default_factory=list)
    suggestions: List[Dict[str, str]] = field(default_factory=list)
    data_sources: List[AnalysisSource] = field(default_factory=list)
    confidence: float = 0.0
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def actionable(self) -> bool:
        return len(self.suggestions) > 0 or self.critical_count > 0

    def to_response(self) -> str:
        """Format as a structured text response (AI-friendly)."""
        lines = [f"## {self.summary}", ""]
        if self.findings:
            lines.append("### Findings")
            for f in self.findings:
                icon = {"critical": "🔴", "major": "🟡", "minor": "🟢", "info": "ℹ️"}.get(f.severity, "❓")
                lines.append(f"- {icon} **{f.severity.upper()}**: {f.message}")
                if f.detail:
                    lines.append(f"  - {f.detail}")
                if f.suggestion:
                    lines.append(f"  - 💡 {f.suggestion}")
            lines.append("")
        if self.suggestions:
            lines.append("### Suggested Actions")
            for s in self.suggestions:
                lines.append(f"- **{s.get('type', 'action')}**: {s.get('description', '')}")
            lines.append("")
        if self.data_sources:
            sources = ", ".join(s.value for s in self.data_sources)
            lines.append(f"*Sources: {sources} | Confidence: {self.confidence:.0%}*")
        return "\n".join(lines)
