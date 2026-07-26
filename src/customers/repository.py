"""InsureDesk — Customer workspace (models, repository, service)."""

import uuid
from datetime import datetime, timezone
from typing import Optional, List
from dataclasses import dataclass, field, asdict


def _now():
    return datetime.now(timezone.utc).isoformat()


# ── Domain Models ────────────────────────────────────────────────

@dataclass
class CustomerData:
    """Customer domain model."""
    id: str = ""
    name: str = ""
    phone: str = ""
    ic_number: str = ""
    email: str = ""
    language: str = "en"
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class PolicyData:
    """Policy domain model."""
    id: str = ""
    customer_id: str = ""
    company: str = ""
    policy_number: str = ""
    policy_type: str = ""
    status: str = "active"
    start_date: str = ""
    end_date: str = ""
    premium: str = ""
    coverage_summary: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class DocumentData:
    """Document domain model."""
    id: str = ""
    customer_id: str = ""
    doc_type: str = "other"
    filename: str = ""
    filepath: str = ""
    tags: list = field(default_factory=list)
    notes: str = ""
    file_size: float = 0
    created_at: str = ""


# ── Repository ───────────────────────────────────────────────────

class CustomerRepository:
    """Repository for customer data (wraps SQLAlchemy)."""

    def __init__(self, session):
        self.session = session

    def list_all(self) -> List[CustomerData]:
        from src.database.models import Customer
        customers = self.session.query(Customer).order_by(Customer.name).all()
        return [self._to_data(c) for c in customers]

    def get_by_id(self, customer_id: str) -> Optional[CustomerData]:
        from src.database.models import Customer
        c = self.session.query(Customer).filter(Customer.id == customer_id).first()
        return self._to_data(c) if c else None

    def search(self, query: str) -> List[CustomerData]:
        from src.database.models import Customer
        q = f"%{query}%"
        customers = self.session.query(Customer).filter(
            (Customer.name.like(q)) | (Customer.phone.like(q)) |
            (Customer.ic_number.like(q))
        ).order_by(Customer.name).all()
        return [self._to_data(c) for c in customers]

    def create(self, data: CustomerData) -> CustomerData:
        from src.database.models import Customer
        c = Customer(
            name=data.name,
            phone=data.phone,
            ic_number=data.ic_number,
            email=data.email,
            language=data.language or "en",
            notes=data.notes or "",
        )
        self.session.add(c)
        self.session.commit()
        return self._to_data(c)

    def update(self, data: CustomerData) -> Optional[CustomerData]:
        from src.database.models import Customer
        c = self.session.query(Customer).filter(Customer.id == data.id).first()
        if not c:
            return None
        if data.name: c.name = data.name
        if data.phone: c.phone = data.phone
        if data.ic_number: c.ic_number = data.ic_number
        if data.email: c.email = data.email
        c.language = data.language or c.language
        c.notes = data.notes if data.notes is not None else c.notes
        self.session.commit()
        return self._to_data(c)

    def delete(self, customer_id: str) -> bool:
        from src.database.models import Customer
        c = self.session.query(Customer).filter(Customer.id == customer_id).first()
        if not c:
            return False
        self.session.delete(c)
        self.session.commit()
        return True

    def get_policies(self, customer_id: str) -> List[PolicyData]:
        from src.database.models import Policy
        policies = self.session.query(Policy).filter(
            Policy.customer_id == customer_id
        ).order_by(Policy.created_at.desc()).all()
        return [self._policy_to_data(p) for p in policies]

    def get_documents(self, customer_id: str) -> List[DocumentData]:
        from src.database.models import Document
        docs = self.session.query(Document).filter(
            Document.customer_id == customer_id
        ).order_by(Document.created_at.desc()).all()
        return [self._doc_to_data(d) for d in docs]

    def _to_data(self, c) -> CustomerData:
        return CustomerData(
            id=str(c.id),
            name=c.name or "",
            phone=c.phone or "",
            ic_number=c.ic_number or "",
            email=c.email or "",
            language=c.language or "en",
            notes=c.notes or "",
            created_at=c.created_at.isoformat() if c.created_at else "",
            updated_at=c.updated_at.isoformat() if c.updated_at else "",
        )

    def _policy_to_data(self, p) -> PolicyData:
        return PolicyData(
            id=str(p.id),
            customer_id=str(p.customer_id),
            company=p.company or "",
            policy_number=p.policy_number or "",
            policy_type=p.policy_type or "",
            status=p.status or "active",
            start_date=p.start_date or "",
            end_date=p.end_date or "",
            premium=p.premium or "",
            coverage_summary=p.coverage_summary or "",
            notes=p.notes or "",
        )

    def _doc_to_data(self, d) -> DocumentData:
        return DocumentData(
            id=str(d.id),
            customer_id=str(d.customer_id),
            doc_type=d.doc_type or "other",
            filename=d.filename or "",
            filepath=d.filepath or "",
            tags=d.tags or [],
            notes=d.notes or "",
            file_size=d.file_size or 0,
            created_at=d.created_at.isoformat() if d.created_at else "",
        )


class PolicyRepository:
    """Repository for policy data."""

    def __init__(self, session):
        self.session = session

    def create(self, data: PolicyData) -> PolicyData:
        from src.database.models import Policy
        p = Policy(
            customer_id=data.customer_id,
            company=data.company,
            policy_number=data.policy_number,
            policy_type=data.policy_type,
            status=data.status or "active",
            start_date=data.start_date,
            end_date=data.end_date,
            premium=data.premium,
            coverage_summary=data.coverage_summary,
            notes=data.notes,
        )
        self.session.add(p)
        self.session.commit()
        return data

    def list_by_customer(self, customer_id: str) -> List[PolicyData]:
        from src.database.models import Policy
        policies = self.session.query(Policy).filter(
            Policy.customer_id == customer_id
        ).all()
        return [PolicyData(
            id=str(p.id), customer_id=str(p.customer_id),
            company=p.company, policy_number=p.policy_number,
            policy_type=p.policy_type, status=p.status,
            start_date=p.start_date, end_date=p.end_date,
            premium=p.premium, coverage_summary=p.coverage_summary,
            notes=p.notes,
        ) for p in policies]


class DocumentRepository:
    """Repository for document data."""

    def __init__(self, session):
        self.session = session

    def create(self, data: DocumentData) -> DocumentData:
        from src.database.models import Document
        d = Document(
            customer_id=data.customer_id,
            doc_type=data.doc_type,
            filename=data.filename,
            filepath=data.filepath,
            tags=data.tags,
            notes=data.notes,
            file_size=data.file_size,
        )
        self.session.add(d)
        self.session.commit()
        return data

    def list_by_customer(self, customer_id: str) -> List[DocumentData]:
        from src.database.models import Document
        docs = self.session.query(Document).filter(
            Document.customer_id == customer_id
        ).all()
        return [DocumentData(
            id=str(d.id), customer_id=str(d.customer_id),
            doc_type=d.doc_type, filename=d.filename,
            filepath=d.filepath, tags=d.tags,
            notes=d.notes, file_size=d.file_size,
            created_at=d.created_at.isoformat() if d.created_at else "",
        ) for d in docs]
