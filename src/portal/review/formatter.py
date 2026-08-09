"""Portal Review Engine — Formatter.

Formats ReviewResult for Bridge Protocol communication.
Provides structured JSON output suitable for sending back to UIP-AI.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.review.models import ReviewResult

logger = logging.getLogger("insuredesk.review.formatter")


class ReviewFormatter:
    """Formats ReviewResult for different output targets.

    Usage:
        formatter = ReviewFormatter()
        bridge_payload = formatter.to_bridge_protocol(result)
        human_summary = formatter.to_human_readable(result)
    """

    def to_bridge_protocol(self, result: ReviewResult) -> Dict[str, Any]:
        """Format for Bridge Protocol (UIP-AI ←→ InsureDesk).

        Returns a compact, structured dict suitable for serialization.
        """
        return {
            "type": "review",
            "execution_id": result.execution_id,
            "status": result.status,
            "summary": result.summary,
            "requires_human_review": result.requires_human_review,
            "changes": [c.to_dict() for c in result.changes],
            "errors": [e.to_dict() for e in result.errors],
            "warnings": [w.to_dict() for w in result.warnings],
            "suggestions": [s.to_dict() for s in result.suggestions],
            "stats": {
                "change_count": len(result.changes),
                "error_count": len(result.errors),
                "warning_count": len(result.warnings),
                "suggestion_count": len(result.suggestions),
            },
        }

    def to_human_readable(self, result: ReviewResult) -> str:
        """Format as human-readable text summary."""
        lines: List[str] = []

        # Status line
        status_icon = {
            "approved": "✅",
            "warning": "⚠️",
            "failed": "❌",
            "needs_review": "👁️",
        }.get(result.status, "❓")
        lines.append(f"{status_icon} Review: {result.status.upper()}")
        if result.summary:
            lines.append(f"  {result.summary}")

        # Changes
        if result.changes:
            lines.append(f"\n📋 Changes ({len(result.changes)}):")
            for c in result.changes[:10]:  # Limit to 10
                icon = {"created": "➕", "updated": "✏️", "removed": "➖",
                        "normalized": "🔄", "auto_fixed": "🔧"}.get(
                    c.change_type, "•"
                )
                before_str = str(c.before) if c.before is not None else "(empty)"
                after_str = str(c.after) if c.after is not None else "(empty)"
                lines.append(f"  {icon} {c.field}: {before_str} → {after_str}")
                if c.reason:
                    lines.append(f"     ({c.reason})")

        # Errors
        if result.errors:
            lines.append(f"\n❌ Errors ({len(result.errors)}):")
            for e in result.errors[:5]:
                lines.append(f"  • {e.message}")
                if e.suggested_action:
                    lines.append(f"    → {e.suggested_action}")

        # Warnings
        if result.warnings:
            lines.append(f"\n⚠️ Warnings ({len(result.warnings)}):")
            for w in result.warnings[:5]:
                lines.append(f"  • {w.message}")

        # Suggestions
        if result.suggestions:
            lines.append(f"\n💡 Suggestions ({len(result.suggestions)}):")
            for s in result.suggestions[:5]:
                fixable = "🔧" if s.auto_fixable else "💭"
                lines.append(f"  {fixable} {s.message}")
                if s.suggested_value is not None:
                    lines.append(f"     Suggested: {s.suggested_value}")

        return "\n".join(lines)

    def to_telegram(self, result: ReviewResult) -> str:
        """Compact format for Telegram message."""
        status_emoji = {
            "approved": "✅",
            "warning": "⚠️",
            "failed": "❌",
            "needs_review": "👁️",
        }.get(result.status, "❓")

        parts = [
            f"{status_emoji} *Review: {result.status.upper()}*",
        ]
        if result.summary:
            parts.append(result.summary)

        stats = []
        if result.changes:
            stats.append(f"📋 {len(result.changes)} changes")
        if result.errors:
            stats.append(f"❌ {len(result.errors)} errors")
        if result.warnings:
            stats.append(f"⚠️ {len(result.warnings)} warnings")
        if result.suggestions:
            stats.append(f"💡 {len(result.suggestions)} suggestions")
        if stats:
            parts.append(" · ".join(stats))

        return "\n".join(parts)
