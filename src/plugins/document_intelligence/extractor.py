"""InsureDesk — Document Intelligence: PDF Extractor.

Extracts text from insurance policy PDFs using PyMuPDF (fitz).
Detects digital vs scanned PDFs. Outputs text for the Parser stage.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from src.plugins.document_intelligence.models import (
    DocumentFormat,
    ExtractionResult,
    ExtractionStatus,
)

logger = logging.getLogger("insuredesk.docintel.extractor")

# Minimum text length per page to consider it "digital" (not scanned)
DIGITAL_TEXT_THRESHOLD = 50


class PDFExtractor:
    """Extract text from insurance policy PDFs.

    Uses PyMuPDF (fitz) for fast, local text extraction.
    Detects whether the PDF is digital (text-extractable) or scanned (image-only).

    Architecture:
        PDF → Extractor → ExtractionResult(raw_text) → Parser → ParsedPolicy

    The extractor does NOT do OCR — that's a separate stage.
    """

    def extract(self, file_path: str) -> ExtractionResult:
        """Extract text from a PDF file.

        Args:
            file_path: Path to the PDF file.

        Returns:
            ExtractionResult with raw_text and per-page text.
        """
        start = time.monotonic()
        result = ExtractionResult(file_path=file_path)

        path = Path(file_path)
        if not path.exists():
            result.error = f"File not found: {file_path}"
            return result

        if path.suffix.lower() != ".pdf":
            result.error = f"Not a PDF: {file_path}"
            return result

        result.metadata["file_size"] = path.stat().st_size
        result.metadata["file_name"] = path.name

        try:
            import fitz  # PyMuPDF
        except ImportError:
            result.error = "PyMuPDF (fitz) not installed. Run: pip install pymupdf"
            return result

        try:
            doc = fitz.open(str(path))
            result.page_count = len(doc)
            result.metadata["pdf_version"] = doc.metadata.get("formatVersion", "")
            result.metadata["title"] = doc.metadata.get("title", "")
            result.metadata["author"] = doc.metadata.get("author", "")

            pages_text = []
            total_text = 0
            digital_pages = 0

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()

                if text and len(text.strip()) > DIGITAL_TEXT_THRESHOLD:
                    digital_pages += 1

                pages_text.append(text.strip())
                total_text += len(text)

            doc.close()

            result.pages = pages_text
            result.raw_text = "\n\n--- PAGE BREAK ---\n\n".join(pages_text)

            # Detect format
            if result.page_count == 0:
                result.format = DocumentFormat.UNKNOWN
            elif digital_pages >= result.page_count * 0.5:
                result.format = DocumentFormat.DIGITAL
            else:
                result.format = DocumentFormat.SCANNED

            result.metadata["total_chars"] = total_text
            result.metadata["digital_pages"] = digital_pages
            result.metadata["scanned_pages"] = result.page_count - digital_pages

            if total_text == 0:
                result.error = "No text extracted from PDF (possibly empty or image-only)"

        except Exception as e:
            result.error = f"PDF extraction error: {e}"
            logger.exception(f"Failed to extract PDF: {file_path}")

        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    def extract_page(self, file_path: str, page_number: int) -> ExtractionResult:
        """Extract text from a single page of a PDF.

        Args:
            file_path: Path to the PDF file.
            page_number: 0-indexed page number.

        Returns:
            Partial ExtractionResult with only that page's text.
        """
        full = self.extract(file_path)
        if full.error or page_number >= len(full.pages):
            return full
        full.raw_text = full.pages[page_number]
        full.pages = [full.pages[page_number]]
        full.page_count = 1
        return full

    def is_digital(self, file_path: str) -> bool:
        """Quick check if a PDF is digital (text-extractable)."""
        result = self.extract(file_path)
        return result.format == DocumentFormat.DIGITAL

    def get_metadata(self, file_path: str) -> dict:
        """Extract only PDF metadata without full text extraction."""
        try:
            import fitz
            doc = fitz.open(file_path)
            meta = {
                "page_count": len(doc),
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "subject": doc.metadata.get("subject", ""),
                "format_version": doc.metadata.get("formatVersion", ""),
                "file_size": Path(file_path).stat().st_size,
            }
            doc.close()
            return meta
        except Exception as e:
            return {"error": str(e)}
