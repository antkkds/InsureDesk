"""InsureDesk — Document Intelligence: Converter.

Converts ParsedPolicy data into the database format (PolicyParseRecord)
and provides a query-friendly interface for UIP-AI.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from .models import (
    ParsedPolicy,
    PolicyFieldConfidence,
)

logger = logging.getLogger("insuredesk.docintel.converter")


class PolicyConverter:
    """Converts ParsedPolicy to/from database and UIP-AI query formats.

    Two output formats:
    1. DB storage — matches PolicyParseRecord table schema
    2. UIP-AI query — nested JSON that UIP-AI can easily query
    """

    @staticmethod
    def to_db_record(
        parsed: ParsedPolicy,
        customer_id: str,
        document_id: str,
    ) -> Dict[str, Any]:
        """Convert ParsedPolicy to PolicyParseRecord-compatible dict.

        Args:
            parsed: Parsed policy data.
            customer_id: Customer UUID from the database.
            document_id: Document UUID from the database.

        Returns:
            Dict matching PolicyParseRecord columns.
        """
        json_data = parsed.to_json_compatible()

        return {
            "customer_id": customer_id,
            "document_id": document_id,
            "company": parsed.insurer.value or "",
            "policy_number": parsed.policy_number.value or "",
            "policy_type": parsed.product_type.value or "",
            "status": _infer_status(parsed),
            "premium": str(parsed.total_premium.value) if parsed.total_premium.value else "",
            "start_date": str(parsed.start_date.value) if parsed.start_date.value else "",
            "end_date": str(parsed.end_date.value) if parsed.end_date.value else "",
            "coverages_json": json.dumps(json_data.get("coverages", []), indent=2),
            "exclusions_json": json.dumps(json_data.get("exclusions", []), indent=2),
            "summary": _generate_summary(parsed),
            "raw_json": json.dumps(json_data, indent=2),
            "version": 1,
            "previous_version_id": None,
        }

    @staticmethod
    def to_uipai_format(parsed: ParsedPolicy) -> Dict[str, Any]:
        """Convert to a format optimized for UIP-AI queries.

        This is the format the Bridge Protocol returns when UIP-AI
        asks about policy information.

        Includes:
        - All structured policy data
        - A natural-language summary for easy prompting
        - Searchable coverage/exclusion arrays
        """
        json_data = parsed.to_json_compatible()

        # Add query-friendly fields
        json_data["_query"] = {
            "searchable_text": _build_searchable_text(parsed),
            "summary": _generate_summary(parsed),
            "confidence": parsed.confidence_overall.value,
            "has_coverage": len(parsed.coverages) > 0,
            "has_exclusions": len(parsed.exclusions) > 0,
            "is_active": _is_active(parsed),
        }

        return json_data

    @staticmethod
    def to_natural_language(parsed: ParsedPolicy) -> str:
        """Convert to a human-readable natural language summary.

        UIP-AI can use this directly to answer customer questions.
        """
        lines = []
        lines.append(f"Policy Number: {parsed.policy_number.value or 'N/A'}")
        lines.append(f"Insurer: {parsed.insurer.value or 'N/A'}")
        lines.append(f"Type: {parsed.product_type.value or 'N/A'}")

        if parsed.insured_name.value:
            lines.append(f"Insured: {parsed.insured_name.value}")

        if parsed.start_date.value or parsed.end_date.value:
            period = f"{parsed.start_date.value or '?'} to {parsed.end_date.value or '?'}"
            lines.append(f"Period: {period}")

        if parsed.total_premium.value:
            curr = parsed.currency.value or "MYR"
            lines.append(f"Premium: {curr} {parsed.total_premium.value:,.2f}")

        if parsed.total_sum_insured.value:
            lines.append(
                f"Total Sum Insured: {parsed.total_sum_insured.value:,.2f}"
            )

        if parsed.coverages:
            lines.append("\nCoverages:")
            for c in parsed.coverages:
                si = f"RM {c.sum_insured:,.2f}" if c.sum_insured else "N/A"
                pm = f"RM {c.premium:,.2f}" if c.premium else ""
                desc = f" - {c.description}" if c.description else ""
                lines.append(f"  • {c.section_name}: {si}{pm}{desc}")

        if parsed.exclusions:
            lines.append("\nExclusions:")
            for e in parsed.exclusions[:5]:
                lines.append(f"  • {e.text[:200]}")

        return "\n".join(lines)


# ── Private helpers ──────────────────────────────────────────


def _infer_status(parsed: ParsedPolicy) -> str:
    """Infer policy status from dates."""
    if not parsed.end_date.value:
        return "active"
    # Simple heuristic: if end date is in the past, it's expired
    try:
        end_str = str(parsed.end_date.value)
        # Try parsing common date formats
        for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d %B %Y", "%Y-%m-%d"]:
            try:
                from datetime import datetime as dt

                end_date = dt.strptime(end_str, fmt)
                if end_date < datetime.now():
                    return "expired"
                return "active"
            except ValueError:
                continue
    except Exception:
        pass
    return "active"


def _is_active(parsed: ParsedPolicy) -> bool:
    return _infer_status(parsed) == "active"


def _build_searchable_text(parsed: ParsedPolicy) -> str:
    """Build a flat searchable text blob for full-text search."""
    parts = [
        str(parsed.policy_number.value or ""),
        str(parsed.insurer.value or ""),
        str(parsed.insured_name.value or ""),
        str(parsed.product_type.value or ""),
    ]
    for c in parsed.coverages:
        parts.append(f"{c.section_name} {c.sum_insured}")
    for e in parsed.exclusions:
        parts.append(e.text[:200])
    return " ".join(p for p in parts if p)


def _generate_summary(parsed: ParsedPolicy) -> str:
    """Generate a one-line summary of the policy."""
    parts = []
    if parsed.insurer.value:
        parts.append(str(parsed.insurer.value))
    if parsed.product_type.value:
        parts.append(str(parsed.product_type.value))
    if parsed.total_sum_insured.value:
        parts.append(f"SI: {parsed.total_sum_insured.value:,.0f}")
    if parsed.total_premium.value:
        parts.append(f"Premium: {parsed.total_premium.value:,.2f}")
    if parsed.insured_name.value:
        parts.append(str(parsed.insured_name.value))
    return " | ".join(parts) if parts else "Policy (no structured data)"
