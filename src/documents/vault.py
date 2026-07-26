"""InsureDesk — Document Vault.

Local file storage with metadata management.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone

from src.customers.repository import DocumentRepository, DocumentData


DOCUMENTS_DIR = Path.home() / "InsureDesk" / "documents"


class DocumentVault:
    """Document storage and management.

    Files are stored locally at ~/InsureDesk/documents/{customer_id}/{filename}.
    Metadata is stored in SQLite via DocumentRepository.
    """

    def __init__(self, session):
        self.repository = DocumentRepository(session)
        DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── File Operations ──

    def import_file(self, source_path: str, customer_id: str, doc_type: str = "other",
                    tags: list = None, notes: str = "") -> Optional[DocumentData]:
        """Import a file into the document vault."""
        source = Path(source_path)
        if not source.exists():
            return None

        # Create customer directory
        cust_dir = DOCUMENTS_DIR / customer_id
        cust_dir.mkdir(parents=True, exist_ok=True)

        # Copy file
        dest_path = cust_dir / source.name
        shutil.copy2(str(source), str(dest_path))

        # Create document record
        data = DocumentData(
            customer_id=customer_id,
            doc_type=doc_type,
            filename=source.name,
            filepath=str(dest_path),
            tags=tags or [],
            notes=notes,
            file_size=source.stat().st_size,
        )
        return self.repository.create(data)

    def delete_file(self, document_id: str) -> bool:
        """Delete a document (file + record)."""
        # Find the document
        docs = []  # We need to search by ID
        # For now, let's query directly
        from src.database.models import Document as DocModel
        from sqlalchemy.orm import Session
        doc = self.repository.session.query(DocModel).filter(
            DocModel.id == document_id
        ).first()
        if not doc:
            return False

        # Delete file
        if doc.filepath and Path(doc.filepath).exists():
            Path(doc.filepath).unlink()

        # Delete record
        self.repository.session.delete(doc)
        self.repository.session.commit()
        return True

    def list_by_customer(self, customer_id: str) -> List[DocumentData]:
        """List all documents for a customer."""
        return self.repository.list_by_customer(customer_id)

    def get_file_path(self, document_id: str) -> Optional[str]:
        """Get the local file path for a document."""
        from src.database.models import Document as DocModel
        doc = self.repository.session.query(DocModel).filter(
            DocModel.id == document_id
        ).first()
        if doc and doc.filepath and Path(doc.filepath).exists():
            return doc.filepath
        return None

    def get_customer_docs_dir(self, customer_id: str) -> Path:
        """Get the document directory for a customer."""
        cust_dir = DOCUMENTS_DIR / customer_id
        cust_dir.mkdir(parents=True, exist_ok=True)
        return cust_dir

    # ── Search ──

    def search_by_tag(self, tag: str) -> List[DocumentData]:
        """Search documents by tag."""
        from src.database.models import Document as DocModel
        docs = self.repository.session.query(DocModel).all()
        # Simple tag search (SQLite JSON)
        result = []
        for d in docs:
            if d.tags and tag in d.tags:
                from .repository import DocumentData
                result.append(DocumentData(
                    id=str(d.id), customer_id=str(d.customer_id),
                    doc_type=d.doc_type, filename=d.filename,
                    filepath=d.filepath, tags=d.tags,
                    notes=d.notes, file_size=d.file_size,
                ))
        return result

    def search_by_type(self, doc_type: str) -> List[DocumentData]:
        """Search documents by type."""
        from src.database.models import Document as DocModel
        docs = self.repository.session.query(DocModel).filter(
            DocModel.doc_type == doc_type
        ).all()
        return [DocumentData(
            id=str(d.id), customer_id=str(d.customer_id),
            doc_type=d.doc_type, filename=d.filename,
            filepath=d.filepath, tags=d.tags,
            notes=d.notes, file_size=d.file_size,
        ) for d in docs]
