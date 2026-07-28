"""InsureDesk — Document Intelligence Plugin.

Thin integration layer between the standalone document-intelligence SDK
(https://github.com/antkkds/document-intelligence) and InsureDesk's
insurance domain models.

Architecture:
  PDF → [document-intelligence SDK] → Document (markdown/text/sections)
       → [PolicyTextParser] → ParsedPolicy (insurance domain)
       → [PolicyConverter] → PolicyParseRecord / UIP-AI JSON

The plugin does NOT reimplement PDF extraction or text normalization.
It delegates that entirely to the standalone SDK via pip install.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set

from src.plugins.base import Plugin, PluginContext
from src.plugins.document_intelligence.models import (
    ParsedPolicy,
    PolicyFieldConfidence,
)
from src.plugins.document_intelligence.parser import PolicyTextParser
from src.plugins.document_intelligence.converter import PolicyConverter

logger = logging.getLogger("insuredesk.plugins.document_intelligence")


class DocumentIntelligencePlugin(Plugin):
    """Plugin that integrates the standalone document-intelligence SDK.

    Capabilities:
      - document.parse: Parse any supported document into structured markdown
      - document.extract_policy: Extract insurance-specific policy data
      - document.index: Index a document for full-text search
    """

    @property
    def id(self) -> str:
        return "document_intelligence"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def capabilities(self) -> Set[str]:
        return {"document.parse", "document.extract_policy", "document.index"}

    def __init__(self) -> None:
        self._ctx: Optional[PluginContext] = None
        self._parser = PolicyTextParser()
        self._converter = PolicyConverter()
        # SDK components, lazy-initialized on first use
        self._pipeline = None
        self._indexer = None

    def initialize(self, context: PluginContext) -> None:
        """Initialize the plugin with injected services."""
        self._ctx = context
        logger.info("DocumentIntelligencePlugin initialized")

    def shutdown(self) -> None:
        """Clean up resources."""
        self._pipeline = None
        self._indexer = None
        logger.info("DocumentIntelligencePlugin shut down")

    # ── Public API ─────────────────────────────────────────────

    def parse_policy(
        self,
        pdf_path: str,
        use_sdk: bool = True,
    ) -> ParsedPolicy:
        """Parse an insurance policy PDF into structured data.

        Args:
            pdf_path: Path to the insurance policy PDF.
            use_sdk: If True (default), uses the document-intelligence SDK
                     for PDF extraction and text normalization.
                     If False, falls back to raw PyMuPDF extraction only
                     (when SDK is unavailable).

        Returns:
            ParsedPolicy with extracted fields and confidence levels.
        """
        text, warnings = self._extract_text(pdf_path, use_sdk)

        parsed = self._parser.parse(text)
        parsed.extraction_id = Path(pdf_path).stem

        for w in warnings:
            parsed.warnings.append(w)

        return parsed

    def parse_to_db(
        self,
        pdf_path: str,
        customer_id: str,
        document_id: str,
        use_sdk: bool = True,
    ) -> Dict[str, Any]:
        """Parse a PDF and return a PolicyParseRecord-compatible dict.

        Args:
            pdf_path: Path to the PDF file.
            customer_id: Customer UUID.
            document_id: Document UUID.
            use_sdk: Use the document-intelligence SDK pipeline.

        Returns:
            Dict matching the PolicyParseRecord table schema.
        """
        parsed = self.parse_policy(pdf_path, use_sdk=use_sdk)
        return self._converter.to_db_record(parsed, customer_id, document_id)

    def parse_to_uipai(
        self,
        pdf_path: str,
        use_sdk: bool = True,
    ) -> Dict[str, Any]:
        """Parse a PDF and return UIP-AI query-friendly JSON.

        Args:
            pdf_path: Path to the PDF file.
            use_sdk: Use the document-intelligence SDK pipeline.

        Returns:
            Nested JSON dict optimized for UIP-AI queries.
        """
        parsed = self.parse_policy(pdf_path, use_sdk=use_sdk)
        return self._converter.to_uipai_format(parsed)

    def parse_to_natural_language(
        self,
        pdf_path: str,
        use_sdk: bool = True,
    ) -> str:
        """Parse a PDF and return a human-readable summary.

        Args:
            pdf_path: Path to the PDF file.
            use_sdk: Use the document-intelligence SDK pipeline.

        Returns:
            Natural language description of the policy.
        """
        parsed = self.parse_policy(pdf_path, use_sdk=use_sdk)
        return self._converter.to_natural_language(parsed)

    def index_document(
        self,
        pdf_path: str,
        db_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parse a PDF and index it for full-text search.

        Uses the document-intelligence SDK's SQLite FTS5 indexer.

        Args:
            pdf_path: Path to the PDF file.
            db_path: Path to the SQLite index database.
                     Defaults to './knowledge/search.db'.

        Returns:
            Dict with index results and metadata.
        """
        doc = self._run_sdk_pipeline(pdf_path)
        if doc is None:
            return {"error": "SDK pipeline failed", "indexed": False}

        from document_intelligence.index.sqlite import SQLiteIndexer

        indexer = SQLiteIndexer(db_path or "./knowledge/search.db")
        import asyncio

        asyncio.run(indexer.index(doc))

        return {
            "source": pdf_path,
            "indexed": True,
            "sections": len(doc.sections),
            "tables": len(doc.tables),
            "characters": len(doc.markdown) if doc.markdown else 0,
        }

    # ── Internal helpers ───────────────────────────────────────

    def _extract_text(
        self,
        pdf_path: str,
        use_sdk: bool = True,
    ) -> tuple[str, list[str]]:
        """Extract text from a PDF, returning (text, warnings)."""
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        warnings: list[str] = []

        if use_sdk:
            try:
                doc = self._run_sdk_pipeline(str(path))
                if doc is not None:
                    # Prefer markdown output (richest), fall back to raw pages
                    text = doc.markdown if doc.markdown else "\n\n".join(doc.raw_pages)
                    logger.info(
                        "SDK pipeline processed %s (%d sections, %d chars)",
                        path.name,
                        len(doc.sections),
                        len(text),
                    )
                    return text, warnings
                else:
                    warnings.append("SDK pipeline returned no output")
            except Exception as e:
                warnings.append(f"SDK pipeline failed: {e}")
                logger.warning("SDK pipeline failed for %s: %s", path.name, e)

        # Fallback: direct PyMuPDF extraction (no SDK)
        if self._ctx and self._ctx.logger:
            self._ctx.logger.info(
                "Falling back to direct PyMuPDF extraction for %s", path.name
            )

        return self._extract_pymupdf(str(path)), warnings

    def _run_sdk_pipeline(self, pdf_path: str):
        """Run the document-intelligence SDK pipeline on a PDF.

        Returns a Document object or None on failure.
        """
        try:
            from document_intelligence import DocumentPipeline
            from document_intelligence.importer.pdf import PDFImporter
            from document_intelligence.normalize.textlayer import (
                TextLayerNormalizer,
            )
            from document_intelligence.normalize.layout import (
                LayoutAnalyzer,
            )
            from document_intelligence.normalize.heading import (
                HeadingDetector,
            )
            from document_intelligence.normalize.markdown import (
                MarkdownBuilder,
            )

            pipeline = DocumentPipeline()
            pipeline.add_importer(PDFImporter())
            pipeline.add_normalizer(TextLayerNormalizer())
            pipeline.add_normalizer(LayoutAnalyzer())
            pipeline.add_normalizer(HeadingDetector())
            pipeline.add_normalizer(MarkdownBuilder())

            return asyncio.run(pipeline.run(pdf_path))

        except ImportError:
            logger.warning(
                "document-intelligence SDK not installed. "
                "Run: pip install git+https://github.com/antkkds/document-intelligence"
            )
            return None
        except Exception as e:
            logger.exception("SDK pipeline error: %s", e)
            return None

    @staticmethod
    def _extract_pymupdf(pdf_path: str) -> str:
        """Direct PyMuPDF extraction fallback — no SDK."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError(
                "PyMuPDF (fitz) not installed. Run: pip install pymupdf"
            )

        doc = fitz.open(pdf_path)
        pages: list[str] = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text().strip()
            if text:
                pages.append(text)
        doc.close()

        return "\n\n--- PAGE BREAK ---\n\n".join(pages)
