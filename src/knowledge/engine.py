"""InsureDesk — PI-19: Knowledge & Reasoning Intelligence.

Module A — Unified Knowledge Library (KnowledgeSource CRUD + search)
Module B — Semantic Retrieval (cross-source search with relevance)
Module C — Case Intelligence (CaseRecord CRUD + matching)
Module D — Explainable Reasoning (evidence-based Q&A)
"""

import uuid
import re
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict
from dataclasses import dataclass, field, asdict


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


# ── Domain Models ────────────────────────────────────────────────

@dataclass
class KnowledgeSourceData:
    id: str = ""
    source_type: str = ""
    title: str = ""
    content: str = ""
    tags: list = field(default_factory=list)
    language: str = "en"
    source_url: str = ""
    source_ref: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CaseRecordData:
    id: str = ""
    category: str = ""
    title: str = ""
    summary: str = ""
    outcome: str = ""
    lessons: str = ""
    customer_id: str = ""
    related_documents: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    is_published: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class EvidenceItem:
    """A piece of evidence supporting a reasoning answer."""
    source_id: str = ""
    source_type: str = ""
    title: str = ""
    excerpt: str = ""
    confidence: str = "medium"


@dataclass
class ReasoningResult:
    """Result of a reasoning query with evidence."""
    query: str = ""
    answer: str = ""
    evidence: list = field(default_factory=list)
    confidence: str = "medium"
    processing_time_ms: int = 0


@dataclass
class SearchResult:
    """A search hit from knowledge sources."""
    source_id: str = ""
    source_type: str = ""
    title: str = ""
    excerpt: str = ""
    relevance: float = 0.0
    language: str = "en"


# ══════════════════════════════════════════════════════════════════
# Module A: Knowledge Library Repository
# ══════════════════════════════════════════════════════════════════

class KnowledgeLibrary:
    """Unified repository for all knowledge sources."""

    def __init__(self, session):
        self.session = session

    # ── CRUD ──

    def create_source(self, data: KnowledgeSourceData) -> KnowledgeSourceData:
        from src.database.models import KnowledgeSource
        k = KnowledgeSource(
            source_type=data.source_type,
            title=data.title,
            content=data.content or "",
            tags=data.tags or [],
            language=data.language or "en",
            source_url=data.source_url or "",
            source_ref=data.source_ref or "",
        )
        self.session.add(k)
        self.session.commit()
        return self._to_data(k)

    def get_source(self, source_id: str) -> Optional[KnowledgeSourceData]:
        from src.database.models import KnowledgeSource
        k = self.session.query(KnowledgeSource).filter(
            KnowledgeSource.id == source_id
        ).first()
        return self._to_data(k) if k else None

    def update_source(self, data: KnowledgeSourceData) -> Optional[KnowledgeSourceData]:
        from src.database.models import KnowledgeSource
        k = self.session.query(KnowledgeSource).filter(
            KnowledgeSource.id == data.id
        ).first()
        if not k:
            return None
        if data.title: k.title = data.title
        if data.content is not None: k.content = data.content
        if data.tags is not None: k.tags = data.tags
        if data.source_type: k.source_type = data.source_type
        if data.language: k.language = data.language
        if data.source_url is not None: k.source_url = data.source_url
        if data.source_ref is not None: k.source_ref = data.source_ref
        self.session.commit()
        return self._to_data(k)

    def delete_source(self, source_id: str) -> bool:
        from src.database.models import KnowledgeSource
        k = self.session.query(KnowledgeSource).filter(
            KnowledgeSource.id == source_id
        ).first()
        if not k:
            return False
        k.is_active = False
        self.session.commit()
        return True

    def list_by_type(self, source_type: str = None) -> List[KnowledgeSourceData]:
        from src.database.models import KnowledgeSource
        q = self.session.query(KnowledgeSource).filter(
            KnowledgeSource.is_active == True
        )
        if source_type:
            q = q.filter(KnowledgeSource.source_type == source_type)
        q = q.order_by(KnowledgeSource.updated_at.desc())
        return [self._to_data(k) for k in q.all()]

    def _to_data(self, k) -> KnowledgeSourceData:
        return KnowledgeSourceData(
            id=str(k.id), source_type=k.source_type or "",
            title=k.title or "", content=k.content or "",
            tags=list(k.tags) if k.tags else [],
            language=k.language or "en",
            source_url=k.source_url or "", source_ref=k.source_ref or "",
            is_active=bool(k.is_active),
            created_at=k.created_at.isoformat() if k.created_at else "",
            updated_at=k.updated_at.isoformat() if k.updated_at else "",
        )

    # ── Bulk import ──

    def bulk_create(self, sources: List[KnowledgeSourceData]) -> int:
        """Import multiple sources at once. Returns count imported."""
        count = 0
        for s in sources:
            self.create_source(s)
            count += 1
        return count


# ══════════════════════════════════════════════════════════════════
# Module B: Semantic Retrieval (keyword-based for MVP)
# ══════════════════════════════════════════════════════════════════

class SemanticRetrieval:
    """Search across all knowledge sources with relevance scoring.

    For MVP: keyword-based with TF-style relevance.
    Future: can be upgraded to embeddings/vector search.
    """

    def __init__(self, session, library: KnowledgeLibrary = None):
        self.session = session
        self.library = library or KnowledgeLibrary(session)

    def search(self, query: str, source_type: str = None,
               limit: int = 10) -> List[SearchResult]:
        """Search knowledge sources by query string.

        Uses keyword matching with relevance scoring based on:
        - Title match (weight 3x)
        - Content match (weight 1x)
        - Tag match (weight 2x)
        """
        from src.database.models import KnowledgeSource
        if not query.strip():
            return []

        terms = self._tokenize(query)
        q = self.session.query(KnowledgeSource).filter(
            KnowledgeSource.is_active == True
        )
        if source_type:
            q = q.filter(KnowledgeSource.source_type == source_type)

        sources = q.all()
        results = []

        for source in sources:
            title_lower = (source.title or "").lower()
            content_lower = (source.content or "").lower()
            tags_lower = [t.lower() for t in (source.tags or [])]

            score = 0.0
            for term in terms:
                if term in title_lower:
                    score += 3.0
                if term in content_lower:
                    score += 1.0
                if any(term in t for t in tags_lower):
                    score += 2.0

            if score > 0:
                excerpt = self._extract_excerpt(source.content or "", terms)
                results.append(SearchResult(
                    source_id=str(source.id),
                    source_type=source.source_type or "",
                    title=source.title or "",
                    excerpt=excerpt,
                    relevance=round(score, 1),
                    language=source.language or "en",
                ))

        # Sort by relevance descending
        results.sort(key=lambda r: r.relevance, reverse=True)
        return results[:limit]

    def search_by_tags(self, tags: List[str], source_type: str = None,
                       limit: int = 10) -> List[SearchResult]:
        """Search knowledge sources by tag matching."""
        from src.database.models import KnowledgeSource
        q = self.session.query(KnowledgeSource).filter(
            KnowledgeSource.is_active == True
        )
        if source_type:
            q = q.filter(KnowledgeSource.source_type == source_type)

        sources = q.all()
        results = []

        for source in s:
            source_tags = [t.lower() for t in (source.tags or [])]
            score = sum(1 for t in tags if t.lower() in source_tags)
            if score > 0:
                results.append(SearchResult(
                    source_id=str(source.id),
                    source_type=source.source_type or "",
                    title=source.title or "",
                    excerpt=(source.content or "")[:200],
                    relevance=round(score, 1),
                    language=source.language or "en",
                ))

        results.sort(key=lambda r: r.relevance, reverse=True)
        return results[:limit]

    def _tokenize(self, text: str) -> List[str]:
        """Split text into lowercase terms."""
        text = text.lower()
        # Split on whitespace and common punctuation
        terms = re.findall(r'\w+', text)
        # Filter out very short terms
        return [t for t in terms if len(t) > 1]

    def _extract_excerpt(self, content: str, terms: List[str],
                         context_chars: int = 100) -> str:
        """Extract the most relevant excerpt from content."""
        if not content:
            return ""
        content_lower = content.lower()

        # Find first occurrence of any term
        best_pos = -1
        for term in terms:
            pos = content_lower.find(term)
            if pos >= 0:
                if best_pos == -1 or pos < best_pos:
                    best_pos = pos

        if best_pos < 0:
            return content[:300]

        start = max(0, best_pos - context_chars)
        end = min(len(content), best_pos + context_chars)

        excerpt = content[start:end]
        if start > 0:
            excerpt = "..." + excerpt
        if end < len(content):
            excerpt = excerpt + "..."

        return excerpt


# ══════════════════════════════════════════════════════════════════
# Module C: Case Intelligence
# ══════════════════════════════════════════════════════════════════

class CaseIntelligence:
    """Repository and matching for insurance case records."""

    def __init__(self, session):
        self.session = session

    # ── CRUD ──

    def create_case(self, data: CaseRecordData) -> CaseRecordData:
        from src.database.models import CaseRecord
        c = CaseRecord(
            category=data.category,
            title=data.title,
            summary=data.summary or "",
            outcome=data.outcome or "",
            lessons=data.lessons or "",
            customer_id=data.customer_id or None,
            related_documents=data.related_documents or [],
            tags=data.tags or [],
            is_published=data.is_published if data.is_published is not None else True,
        )
        self.session.add(c)
        self.session.commit()
        return self._to_data(c)

    def get_case(self, case_id: str) -> Optional[CaseRecordData]:
        from src.database.models import CaseRecord
        c = self.session.query(CaseRecord).filter(CaseRecord.id == case_id).first()
        return self._to_data(c) if c else None

    def update_case(self, data: CaseRecordData) -> Optional[CaseRecordData]:
        from src.database.models import CaseRecord
        c = self.session.query(CaseRecord).filter(CaseRecord.id == data.id).first()
        if not c:
            return None
        if data.title: c.title = data.title
        if data.category: c.category = data.category
        if data.summary is not None: c.summary = data.summary
        if data.outcome is not None: c.outcome = data.outcome
        if data.lessons is not None: c.lessons = data.lessons
        if data.tags is not None: c.tags = data.tags
        self.session.commit()
        return self._to_data(c)

    def delete_case(self, case_id: str) -> bool:
        from src.database.models import CaseRecord
        c = self.session.query(CaseRecord).filter(CaseRecord.id == case_id).first()
        if not c:
            return False
        self.session.delete(c)
        self.session.commit()
        return True

    def list_cases(self, category: str = None, limit: int = 20) -> List[CaseRecordData]:
        from src.database.models import CaseRecord
        q = self.session.query(CaseRecord).filter(CaseRecord.is_published == True)
        if category:
            q = q.filter(CaseRecord.category == category)
        q = q.order_by(CaseRecord.updated_at.desc()).limit(limit)
        return [self._to_data(c) for c in q.all()]

    def search_cases(self, query: str, limit: int = 10) -> List[CaseRecordData]:
        """Search case records by keyword."""
        from src.database.models import CaseRecord
        if not query.strip():
            return self.list_cases(limit=limit)
        like = f"%{query}%"
        cases = (
            self.session.query(CaseRecord)
            .filter(CaseRecord.is_published == True)
            .filter(
                (CaseRecord.title.like(like)) |
                (CaseRecord.summary.like(like)) |
                (CaseRecord.lessons.like(like))
            )
            .order_by(CaseRecord.updated_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_data(c) for c in cases]

    def find_similar_cases(self, category: str, tags: List[str] = None,
                           limit: int = 5) -> List[CaseRecordData]:
        """Find cases similar to a given category and tags."""
        from src.database.models import CaseRecord
        q = self.session.query(CaseRecord).filter(
            CaseRecord.category == category,
            CaseRecord.is_published == True,
        )
        cases = q.order_by(CaseRecord.updated_at.desc()).limit(limit).all()
        return [self._to_data(c) for c in cases]

    def _to_data(self, c) -> CaseRecordData:
        return CaseRecordData(
            id=str(c.id), category=c.category or "",
            title=c.title or "", summary=c.summary or "",
            outcome=c.outcome or "", lessons=c.lessons or "",
            customer_id=str(c.customer_id) if c.customer_id else "",
            related_documents=list(c.related_documents) if c.related_documents else [],
            tags=list(c.tags) if c.tags else [],
            is_published=bool(c.is_published),
            created_at=c.created_at.isoformat() if c.created_at else "",
            updated_at=c.updated_at.isoformat() if c.updated_at else "",
        )


# ══════════════════════════════════════════════════════════════════
# Module D: Explainable Reasoning Engine
# ══════════════════════════════════════════════════════════════════

class ReasoningEngine:
    """Answer questions using knowledge sources with evidence.

    Pipeline:
    1. Parse query → extract key terms
    2. Search knowledge sources (Module B)
    3. Search case records (Module C)
    4. Build answer with evidence citations
    5. Log reasoning for audit
    """

    def __init__(self, session, library: KnowledgeLibrary = None,
                 retrieval: SemanticRetrieval = None,
                 cases: CaseIntelligence = None):
        self.session = session
        self.library = library or KnowledgeLibrary(session)
        self.retrieval = retrieval or SemanticRetrieval(session, self.library)
        self.cases = cases or CaseIntelligence(session)

    def answer(self, query: str) -> ReasoningResult:
        """Answer a question using all available knowledge."""
        start_time = time.time()
        evidence = []

        # Step 1: Search knowledge sources
        knowledge_hits = self.retrieval.search(query, limit=5)
        for hit in knowledge_hits:
            evidence.append(EvidenceItem(
                source_id=hit.source_id,
                source_type=hit.source_type,
                title=hit.title,
                excerpt=hit.excerpt,
                confidence="high" if hit.relevance >= 5.0 else "medium",
            ))

        # Step 2: Search case records
        case_hits = self.cases.search_cases(query, limit=3)
        for case in case_hits:
            evidence.append(EvidenceItem(
                source_id=case.id,
                source_type="case_record",
                title=case.title,
                excerpt=case.summary[:300],
                confidence="medium",
            ))

        # Step 3: Build answer
        answer = self._build_answer(query, evidence)

        # Step 4: Determine confidence
        confidence = self._determine_confidence(evidence)

        # Step 5: Log reasoning
        elapsed = int((time.time() - start_time) * 1000)
        self._log_reasoning(query, answer, evidence, confidence, elapsed)

        return ReasoningResult(
            query=query,
            answer=answer,
            evidence=evidence,
            confidence=confidence,
            processing_time_ms=elapsed,
        )

    def _build_answer(self, query: str, evidence: List[EvidenceItem]) -> str:
        """Build a structured answer from evidence."""
        if not evidence:
            return ("I couldn't find specific information about this in "
                    "my knowledge sources. Try rephrasing or adding more details.")

        parts = []
        sources_by_type = {}
        for e in evidence:
            st = e.source_type
            if st not in sources_by_type:
                sources_by_type[st] = []
            sources_by_type[st].append(e)

        # Summarize what was found
        total = len(evidence)
        parts.append(f"📚 Found **{total}** relevant source(s).")

        # Group by source type
        type_labels = {
            "policy_document": "Policy Documents",
            "claim_guide": "Claim Guides",
            "company_circular": "Company Circulars",
            "sop": "SOPs",
            "faq": "FAQs",
            "case_note": "Case Notes",
            "training": "Training Materials",
            "market_notice": "Market Notices",
            "case_record": "Similar Cases",
        }

        for st, items in sources_by_type.items():
            label = type_labels.get(st, st.replace("_", " ").title())
            for item in items[:2]:  # Max 2 per type
                confidence_icon = "🟢" if item.confidence == "high" else "🟡"
                parts.append(f"\n{confidence_icon} **{item.title}** ({label})")
                if item.excerpt:
                    parts.append(f"> {item.excerpt[:200]}")

        if len(evidence) > 5:
            parts.append(f"\n...and {len(evidence) - 5} more references.")

        return "\n".join(parts)

    def _determine_confidence(self, evidence: List[EvidenceItem]) -> str:
        """Determine overall confidence based on evidence quality."""
        if not evidence:
            return "low"
        high_count = sum(1 for e in evidence if e.confidence == "high")
        total = len(evidence)
        if high_count >= 2 or (high_count >= 1 and total >= 3):
            return "high"
        if total >= 2:
            return "medium"
        return "low"

    def _log_reasoning(self, query: str, answer: str,
                       evidence: List[EvidenceItem],
                       confidence: str, elapsed_ms: int):
        """Log the reasoning query for audit."""
        from src.database.models import ReasoningLog
        log = ReasoningLog(
            query=query,
            answer=answer[:1000],
            evidence=[
                {"source_id": e.source_id, "source_type": e.source_type,
                 "title": e.title, "confidence": e.confidence}
                for e in evidence
            ],
            confidence=confidence,
            processing_time_ms=elapsed_ms,
        )
        self.session.add(log)
        self.session.commit()
