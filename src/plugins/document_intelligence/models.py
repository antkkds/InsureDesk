"""InsureDesk — Document Intelligence: Data Models.

Core data structures for PDF extraction, policy parsing,
and structured policy data that UIP-AI can query.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DocumentFormat(Enum):
    """Type of PDF document detected."""

    DIGITAL = "digital"  # Text-extractable PDF
    SCANNED = "scanned"  # Image-based PDF (needs OCR)
    UNKNOWN = "unknown"


class ExtractionStatus(Enum):
    """Status of an extraction job."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class PolicyFieldConfidence(Enum):
    """Confidence level for an extracted field."""

    HIGH = "high"  # Regex-matched with high certainty
    MEDIUM = "medium"  # Pattern-matched but ambiguous
    LOW = "low"  # Best-guess, may be wrong
    UNKNOWN = "unknown"  # Could not extract


@dataclass
class FieldValue:
    """A single extracted field with confidence metadata."""

    value: Any = None
    confidence: PolicyFieldConfidence = PolicyFieldConfidence.UNKNOWN
    source_text: str = ""  # The original text this was extracted from
    page_number: int = 0

    @property
    def is_reliable(self) -> bool:
        return self.confidence in (PolicyFieldConfidence.HIGH, PolicyFieldConfidence.MEDIUM)


@dataclass
class ExtractionResult:
    """Result of the PDF text extraction step."""

    id: str = field(default_factory=lambda: f"ext_{uuid.uuid4().hex[:8]}")
    file_path: str = ""
    format: DocumentFormat = DocumentFormat.UNKNOWN
    page_count: int = 0
    raw_text: str = ""
    pages: List[str] = field(default_factory=list)  # Text per page
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.error is None and len(self.raw_text) > 0


@dataclass
class ParsedCoverage:
    """A single coverage section from a policy."""

    section_name: str = ""
    sum_insured: float = 0.0
    premium: float = 0.0
    description: str = ""
    confidence: PolicyFieldConfidence = PolicyFieldConfidence.UNKNOWN


@dataclass
class ParsedExclusion:
    """A single exclusion clause from a policy."""

    text: str = ""
    section: str = ""
    confidence: PolicyFieldConfidence = PolicyFieldConfidence.UNKNOWN


@dataclass
class ParsedPolicy:
    """Fully parsed, structured policy data.

    This is the output of the Parser stage — text-agnostic.
    The same structure works whether text came from PyMuPDF, OCR, or API.
    """

    id: str = field(default_factory=lambda: f"pol_{uuid.uuid4().hex[:8]}")

    # Policy identifiers
    policy_number: FieldValue = field(default_factory=FieldValue)
    insurer: FieldValue = field(default_factory=FieldValue)
    product_type: FieldValue = field(default_factory=FieldValue)  # fire, motor, life, etc.
    policy_type: FieldValue = field(default_factory=FieldValue)  # new, renewal, endorsement

    # Period
    issue_date: FieldValue = field(default_factory=FieldValue)
    start_date: FieldValue = field(default_factory=FieldValue)
    end_date: FieldValue = field(default_factory=FieldValue)

    # Insured
    insured_name: FieldValue = field(default_factory=FieldValue)
    insured_ic: FieldValue = field(default_factory=FieldValue)
    insured_address: FieldValue = field(default_factory=FieldValue)
    insured_phone: FieldValue = field(default_factory=FieldValue)

    # Premium
    total_premium: FieldValue = field(default_factory=FieldValue)
    annual_premium: FieldValue = field(default_factory=FieldValue)
    currency: FieldValue = field(default_factory=lambda: FieldValue(value="MYR"))
    installment: FieldValue = field(default_factory=FieldValue)

    # Coverage
    total_sum_insured: FieldValue = field(default_factory=FieldValue)
    coverages: List[ParsedCoverage] = field(default_factory=list)
    exclusions: List[ParsedExclusion] = field(default_factory=list)

    # Raw / metadata
    raw_text_snippet: str = ""  # First 500 chars of source text for debugging
    extraction_id: str = ""
    parser_version: str = "1.0.0"
    confidence_overall: PolicyFieldConfidence = PolicyFieldConfidence.UNKNOWN
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    parsed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_json_compatible(self) -> Dict[str, Any]:
        """Convert to a JSON-compatible dict for PolicyParseRecord storage.

        This is the format UIP-AI will query against.
        Nested structure as recommended by ChatGPT.
        """
        return {
            "policy": {
                "number": self._val(self.policy_number),
                "insurer": self._val(self.insurer),
                "type": self._val(self.product_type),
                "policy_type": self._val(self.policy_type),
                "period": {
                    "issue_date": self._val(self.issue_date),
                    "start": self._val(self.start_date),
                    "end": self._val(self.end_date),
                },
            },
            "insured": {
                "name": self._val(self.insured_name),
                "ic_number": self._val(self.insured_ic),
                "address": self._val(self.insured_address),
                "phone": self._val(self.insured_phone),
            },
            "premium": {
                "total": self._num(self.total_premium),
                "annual": self._num(self.annual_premium),
                "currency": self._val(self.currency) or "MYR",
                "installment": self._val(self.installment),
            },
            "coverages": [
                {
                    "name": c.section_name,
                    "sum_insured": c.sum_insured,
                    "premium": c.premium,
                    "description": c.description,
                }
                for c in self.coverages
            ],
            "total_sum_insured": self._num(self.total_sum_insured),
            "exclusions": [e.text for e in self.exclusions],
            "_meta": {
                "parser_version": self.parser_version,
                "confidence": self.confidence_overall.value,
                "warnings": self.warnings,
                "parsed_at": self.parsed_at,
            },
        }

    @staticmethod
    def _val(fv: FieldValue) -> Any:
        return fv.value if fv else None

    @staticmethod
    def _num(fv: FieldValue) -> float:
        try:
            return float(fv.value) if fv and fv.value else 0.0
        except (TypeError, ValueError):
            return 0.0
