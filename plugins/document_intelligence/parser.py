"""InsureDesk — Document Intelligence: Policy Text Parser.

Parses insurance policy text into structured ParsedPolicy data.
Completely text-agnostic — works whether text came from PyMuPDF, OCR, or API.

Handles Malaysian insurance policy formats:
- Fire insurance (Houseowner/Householder)
- Motor insurance
- Life insurance
- General insurance
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Pattern, Tuple

from .models import (
    FieldValue,
    ParsedCoverage,
    ParsedExclusion,
    ParsedPolicy,
    PolicyFieldConfidence,
)

logger = logging.getLogger("insuredesk.docintel.parser")

# ── Regex Patterns for Malaysian insurance policies ─────────────

# Policy number formats: GEG123456789 / A1234567 / 1234-567890-01
RE_POLICY_NUMBER = re.compile(
    r"(?:policy\s*(?:no|number|#)[:\s]*([A-Z0-9\-]{4,20}))|"
    r"([A-Z]{2,4}\d{6,12})|"
    r"(\d{4}-\d{6,10}-\d{2,4})",
    re.IGNORECASE,
)

# Insurer names (Malaysian market)
RE_INSURER = re.compile(
    r"(great\s*eastern|aia\s*bhd?|allianz\s*general|etiqa|"
    r"tokio\s*marine|zurich|liberty\s*general|"
    r"berjaya\s*sompo|msig|takaful|prudential|"
    r"hong\s*leong|rhb\s*insurance)",
    re.IGNORECASE,
)

# Dates: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, or "01 January 2024"
RE_DATE = re.compile(
    r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})|"
    r"(\d{1,2}\s+(?:january|february|march|april|may|june|july|"
    r"august|september|october|november|december)\s+\d{4})",
    re.IGNORECASE,
)

# Premium: RM 1,234.56 / RM1,234.56 / 1,234.56
RE_PREMIUM = re.compile(
    r"(?:total\s*)?(?:premium|annual\s*premium|monthly\s*premium)"
    r"(?:\s*:)?\s*(?:rm)?[\s]*([\d,]+\.?\d*)",
    re.IGNORECASE,
)

# Sum insured: RM 500,000 / RM500,000 / Sum Insured: 500,000
RE_SUM_INSURED = re.compile(
    r"(?:(?:total\s+)?(?:sum\s+insured|amount\s+insured|si)"
    r"|(?:death\s+)?benefit)"
    r"(?:\s*:)?\s*(?:rm)?[\s]*([\d,]+\.?\d*)",
    re.IGNORECASE,
)

# Coverage sections: "Section I - Buildings", "Section II - Contents"
RE_SECTION = re.compile(
    r"(?:section|cover|coverage)\s+([A-Z0-9]+)"
    r"(?:\s*[-–—:]+\s*(.+))?",
    re.IGNORECASE,
)

# Insured name: "Insured: John Tan" or "Name of Insured: John Tan"
RE_INSURED_NAME = re.compile(
    r"(?:name\s*(?:of\s*)?insured|insured\s*name|insured)[:\s]+(.+)",
    re.IGNORECASE,
)

# IC / NRIC: 881010-01-1234 or 881010011234
RE_IC = re.compile(r"(\d{6}[-]?\d{2}[-]?\d{4})")

# Product type matching
RE_PRODUCT = re.compile(
    r"(?:product|policy\s*type|plan)[:\s]*(.+)",
    re.IGNORECASE,
)

# Policy period markers
RE_PERIOD_START = re.compile(
    r"(?:period\s*(?:of\s*)?insurance|commencement|effective|"
    r"cover\s*from|from\s*date|issue\s*date)[:\s]*(.+)",
    re.IGNORECASE,
)
RE_PERIOD_END = re.compile(
    r"(?:expiry|expiration|expires|to\s*date|valid\s*until|"
    r"cover\s*to|renewal\s*date)[:\s]*(.+)",
    re.IGNORECASE,
)

# Currency
RE_CURRENCY = re.compile(r"(MYR|RM|USD|SGD)", re.IGNORECASE)


class PolicyTextParser:
    """Parses raw insurance policy text into structured data.

    Architecture principle: text-agnostic.
    The same parser handles text from PyMuPDF, OCR, or any other source.

    Usage:
        parser = PolicyTextParser()
        parsed = parser.parse("POLICY NUMBER: GEG123456...")
    """

    def parse(self, text: str) -> ParsedPolicy:
        """Parse policy text into structured data.

        Args:
            text: Raw text from PDF extraction (or OCR or any source).

        Returns:
            ParsedPolicy with extracted fields and confidence levels.
        """
        parsed = ParsedPolicy()
        parsed.raw_text_snippet = text[:500]

        if not text or not text.strip():
            parsed.errors.append("Empty text provided")
            return parsed

        text_clean = self._clean_text(text)

        # Extract each field using regex patterns
        parsed.policy_number = self._extract_policy_number(text_clean)
        parsed.insurer = self._extract_insurer(text_clean)
        parsed.product_type = self._extract_product_type(text_clean)
        parsed.insured_name = self._extract_insured_name(text_clean)
        parsed.insured_ic = self._extract_insured_ic(text_clean)
        parsed.issue_date = self._extract_date(text_clean, "issue")
        parsed.start_date = self._extract_date(text_clean, "start")
        parsed.end_date = self._extract_date(text_clean, "end")
        parsed.total_premium = self._extract_premium(text_clean)
        parsed.total_sum_insured = self._extract_sum_insured(text_clean)
        parsed.currency = self._extract_currency(text_clean)
        parsed.coverages = self._extract_coverages(text_clean)
        parsed.exclusions = self._extract_exclusions(text_clean)

        # Calculate overall confidence
        parsed.confidence_overall = self._calculate_confidence(parsed)

        # Collect warnings
        if parsed.coverages and not parsed.total_sum_insured.value:
            parsed.warnings.append(
                "Coverages found but total sum insured not extracted"
            )
        if parsed.start_date.value and not parsed.end_date.value:
            parsed.warnings.append("Start date found but end date missing")
        if parsed.confidence_overall == PolicyFieldConfidence.LOW:
            parsed.warnings.append("Low overall extraction confidence — review required")

        return parsed

    # ── Field extractors ──────────────────────────────────────

    @staticmethod
    def _extract_policy_number(text: str) -> FieldValue:
        match = RE_POLICY_NUMBER.search(text)
        if match:
            return FieldValue(
                value=match.group(1).strip(),
                confidence=PolicyFieldConfidence.HIGH,
                source_text=match.group(0),
            )
        return FieldValue(confidence=PolicyFieldConfidence.UNKNOWN)

    @staticmethod
    def _extract_insurer(text: str) -> FieldValue:
        match = RE_INSURER.search(text)
        if match:
            name = match.group(1).strip().title()
            return FieldValue(
                value=name,
                confidence=PolicyFieldConfidence.HIGH,
                source_text=match.group(0),
            )
        return FieldValue(confidence=PolicyFieldConfidence.UNKNOWN)

    @staticmethod
    def _extract_product_type(text: str) -> FieldValue:
        # Detect from keywords first (more reliable)
        text_lower = text.lower()
        product_map = [
            ("fire", "fire"),
            ("houseowner", "fire"),
            ("householder", "fire"),
            ("comprehensive motor", "motor"),
            ("motor", "motor"),
            ("car", "motor"),
            ("life", "life"),
            ("whole life", "life"),
            ("health", "health"),
            ("medical", "health"),
            ("personal accident", "personal_accident"),
            ("travel", "travel"),
        ]
        for keyword, product_type in product_map:
            if keyword in text_lower:
                return FieldValue(
                    value=product_type,
                    confidence=PolicyFieldConfidence.HIGH,
                )

        # Try explicit product field
        match = RE_PRODUCT.search(text)
        if match:
            product = match.group(1).strip()
            return FieldValue(
                value=product,
                confidence=PolicyFieldConfidence.MEDIUM,
                source_text=match.group(0),
            )
        return FieldValue(confidence=PolicyFieldConfidence.UNKNOWN)

    @staticmethod
    def _extract_insured_name(text: str) -> FieldValue:
        match = RE_INSURED_NAME.search(text)
        if match:
            name = match.group(1).strip()
            # Clean up trailing noise
            name = re.sub(r"\s{2,}", " ", name)
            name = re.split(r"[,\n]", name)[0].strip()
            if name and len(name) > 2:
                return FieldValue(
                    value=name,
                    confidence=PolicyFieldConfidence.HIGH,
                    source_text=match.group(0),
                )
        return FieldValue(confidence=PolicyFieldConfidence.UNKNOWN)

    @staticmethod
    def _extract_insured_ic(text: str) -> FieldValue:
        match = RE_IC.search(text)
        if match:
            ic = match.group(1)
            return FieldValue(
                value=ic,
                confidence=PolicyFieldConfidence.HIGH,
                source_text=match.group(0),
            )
        return FieldValue(confidence=PolicyFieldConfidence.UNKNOWN)

    @staticmethod
    def _extract_date(text: str, date_type: str) -> FieldValue:
        """Extract a date, optionally matching context keywords."""
        if date_type == "start":
            # Try "From DD/MM/YYYY" format
            from_match = re.search(
                r"(?:from|effective|commencement|start)\s*"
                r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
                text, re.IGNORECASE,
            )
            if from_match:
                return FieldValue(
                    value=from_match.group(1),
                    confidence=PolicyFieldConfidence.HIGH,
                    source_text=from_match.group(0),
                )
            match = RE_PERIOD_START.search(text)
        elif date_type == "end":
            # Try "to DD/MM/YYYY" format
            to_match = re.search(
                r"(?:to|expiry|expires|until)\s*"
                r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
                text, re.IGNORECASE,
            )
            if to_match:
                return FieldValue(
                    value=to_match.group(1),
                    confidence=PolicyFieldConfidence.HIGH,
                    source_text=to_match.group(0),
                )
            match = RE_PERIOD_END.search(text)
        else:
            # Generic date extraction
            match = RE_DATE.search(text)

        if match:
            date_str = match.group(0).strip()
            return FieldValue(
                value=date_str,
                confidence=PolicyFieldConfidence.HIGH
                if date_type != "unknown"
                else PolicyFieldConfidence.MEDIUM,
                source_text=match.group(0),
            )
        return FieldValue(confidence=PolicyFieldConfidence.UNKNOWN)

    @staticmethod
    def _extract_premium(text: str) -> FieldValue:
        match = RE_PREMIUM.search(text)
        if match:
            try:
                amount = float(match.group(1).replace(",", ""))
                return FieldValue(
                    value=amount,
                    confidence=PolicyFieldConfidence.HIGH,
                    source_text=match.group(0),
                )
            except ValueError:
                pass

        # Fallback: find amount near "premium" keyword only
        fallback = re.search(
            r"premium[:\s]*rm[\s]*([\d,]+\.?\d*)", text, re.IGNORECASE
        )
        if fallback:
            try:
                amount = float(fallback.group(1).replace(",", ""))
                return FieldValue(
                    value=amount,
                    confidence=PolicyFieldConfidence.MEDIUM,
                    source_text=fallback.group(0),
                )
            except ValueError:
                pass

        # Final fallback: any premium-adjacent number
        fallback2 = re.search(
            r"(?:annual|monthly|total)\s+premium[:\s]*([\d,]+\.?\d*)",
            text, re.IGNORECASE,
        )
        if fallback2:
            try:
                amount = float(fallback2.group(1).replace(",", ""))
                return FieldValue(
                    value=amount,
                    confidence=PolicyFieldConfidence.MEDIUM,
                    source_text=fallback2.group(0),
                )
            except ValueError:
                pass

        return FieldValue(confidence=PolicyFieldConfidence.UNKNOWN)

    @staticmethod
    def _extract_sum_insured(text: str) -> FieldValue:
        match = RE_SUM_INSURED.search(text)
        if match:
            try:
                amount = float(match.group(1).replace(",", ""))
                return FieldValue(
                    value=amount,
                    confidence=PolicyFieldConfidence.HIGH,
                    source_text=match.group(0),
                )
            except ValueError:
                pass
        return FieldValue(confidence=PolicyFieldConfidence.UNKNOWN)

    @staticmethod
    def _extract_currency(text: str) -> FieldValue:
        match = RE_CURRENCY.search(text)
        if match:
            curr = match.group(1).upper()
            if curr == "RM":
                curr = "MYR"
            return FieldValue(
                value=curr,
                confidence=PolicyFieldConfidence.HIGH,
            )
        return FieldValue(value="MYR", confidence=PolicyFieldConfidence.MEDIUM)

    @staticmethod
    def _extract_coverages(text: str) -> List[ParsedCoverage]:
        """Extract coverage sections from policy text."""
        coverages: List[ParsedCoverage] = []
        lines = text.split("\n")

        current_section: Optional[str] = None
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Match section headers
            section_match = RE_SECTION.search(line)
            if section_match:
                current_section = section_match.group(1).strip()
                title = (section_match.group(2) or "").strip()
                coverage = ParsedCoverage(
                    section_name=f"Section {current_section}"
                    + (f" - {title}" if title else ""),
                    confidence=PolicyFieldConfidence.MEDIUM,
                )
                coverages.append(coverage)
                continue

            # Try to extract sum insured from the line
            si_match = re.search(
                r"(?:rm)?[\s]*([\d,]+\.?\d*)\s*(?:si|sum\s*insured)?",
                line,
                re.IGNORECASE,
            )
            if si_match and coverages:
                try:
                    amount = float(si_match.group(1).replace(",", ""))
                    if amount > 100:  # Sanity check: sum insured > 100
                        coverages[-1].sum_insured = amount
                        coverages[-1].confidence = PolicyFieldConfidence.HIGH
                except ValueError:
                    pass

        # If no sections found, try to find sum insured amounts generically
        if not coverages:
            amounts = re.findall(
                r"(?:rm)?[\s]*([\d,]+\.?\d*)\s*(?:sum\s*insured|si)",
                text,
                re.IGNORECASE,
            )
            for i, amt_str in enumerate(amounts[:10]):
                try:
                    amount = float(amt_str.replace(",", ""))
                    if amount > 100:
                        coverages.append(
                            ParsedCoverage(
                                section_name=f"Coverage {i + 1}",
                                sum_insured=amount,
                                confidence=PolicyFieldConfidence.LOW,
                            )
                        )
                except ValueError:
                    pass

        return coverages

    @staticmethod
    def _extract_exclusions(text: str) -> List[ParsedExclusion]:
        """Extract exclusion clauses from policy text."""
        exclusions: List[ParsedExclusion] = []
        text_lower = text.lower()

        # Find the exclusions section
        excl_start = None
        for marker in [
            "exclusions",
            "general exclusions",
            "what is not covered",
            "not insured",
        ]:
            idx = text_lower.find(marker)
            if idx != -1:
                excl_start = idx
                break

        if excl_start is not None:
            excl_section = text[excl_start : excl_start + 3000]
            # Split by numbered/bullet points
            items = re.split(r"(?:^|\n)\s*(?:\d+[\.\)]|\([a-z]\)|[-•*])\s*", excl_section)
            for item in items[1:]:  # Skip the header
                item = item.strip()
                if item and len(item) > 10:  # Meaningful exclusion text
                    exclusions.append(
                        ParsedExclusion(
                            text=item[:500],  # Truncate long clauses
                            section="general",
                            confidence=PolicyFieldConfidence.MEDIUM,
                        )
                    )

        return exclusions

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _clean_text(text: str) -> str:
        """Normalize whitespace and fix common OCR issues."""
        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Remove excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Normalize spaces
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    @staticmethod
    def _calculate_confidence(parsed: ParsedPolicy) -> PolicyFieldConfidence:
        """Calculate overall confidence based on extracted fields."""
        high_count = 0
        total_fields = 0

        # Count reliable fields (HIGH or MEDIUM confidence)
        for field in [
            parsed.policy_number,
            parsed.insurer,
            parsed.insured_name,
            parsed.total_premium,
            parsed.total_sum_insured,
            parsed.start_date,
            parsed.end_date,
        ]:
            if field and field.is_reliable:
                high_count += 1
            total_fields += 1

        if total_fields == 0:
            return PolicyFieldConfidence.UNKNOWN

        ratio = high_count / total_fields
        if ratio >= 0.7:
            return PolicyFieldConfidence.HIGH
        elif ratio >= 0.3:
            return PolicyFieldConfidence.MEDIUM
        elif high_count > 0:
            return PolicyFieldConfidence.LOW
        return PolicyFieldConfidence.UNKNOWN
