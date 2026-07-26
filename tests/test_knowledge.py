"""Tests: PI-19 Knowledge & Reasoning Intelligence.

Scope: ~32 tests covering:
- KnowledgeSource CRUD
- Semantic search
- CaseRecord CRUD
- Case search
- Reasoning engine (answer with evidence)
- E2E flow
"""

from __future__ import annotations

import pytest


@pytest.fixture
def session():
    from src.database.db_manager import init_db, get_engine, get_session
    engine = get_engine(":memory:")
    init_db(engine)
    return get_session(engine)


@pytest.fixture
def library(session):
    from src.knowledge.engine import KnowledgeLibrary
    return KnowledgeLibrary(session)


@pytest.fixture
def retrieval(session, library):
    from src.knowledge.engine import SemanticRetrieval
    return SemanticRetrieval(session, library)


@pytest.fixture
def cases(session):
    from src.knowledge.engine import CaseIntelligence
    return CaseIntelligence(session)


@pytest.fixture
def seeded_library(session, library):
    """Seed knowledge sources for search tests."""
    from src.knowledge.engine import KnowledgeSourceData
    sources = [
        KnowledgeSourceData(
            source_type="policy_document", title="Great Eastern Medical Shield",
            content="This policy covers hospital room and board up to RM400 per day. "
                    "Cancer treatment is covered under Section 4. "
                    "Exclusions include pre-existing conditions and cosmetic surgery.",
            tags=["great_eastern", "medical", "cancer"],
        ),
        KnowledgeSourceData(
            source_type="faq", title="How to file a motor claim",
            content="Step 1: Report the accident within 24 hours. "
                    "Step 2: Gather documents (police report, photos, IC). "
                    "Step 3: Submit to insurer portal.",
            tags=["motor", "claim", "procedure"],
        ),
        KnowledgeSourceData(
            source_type="company_circular", title="BNM New Guidelines 2026",
            content="Bank Negara Malaysia has issued new guidelines for insurance "
                    "agents regarding replacement policies. Effective June 2026.",
            tags=["bnm", "regulation", "replacement"],
        ),
    ]
    for s in sources:
        library.create_source(s)
    return library


# ══════════════════════════════════════════════════════════════════
# 1. KnowledgeSource CRUD (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestKnowledgeSource:
    """Verify KnowledgeSource CRUD."""

    def test_create_source(self, library):
        """Create a knowledge source."""
        from src.knowledge.engine import KnowledgeSourceData
        k = library.create_source(KnowledgeSourceData(
            source_type="sop", title="Motor Claim SOP",
            content="Step by step guide...", tags=["motor", "claim"],
        ))
        assert k.id
        assert k.source_type == "sop"
        assert "motor" in k.tags

    def test_get_source(self, library):
        """Get a knowledge source by ID."""
        from src.knowledge.engine import KnowledgeSourceData
        k = library.create_source(KnowledgeSourceData(
            source_type="faq", title="Test FAQ"))
        fetched = library.get_source(k.id)
        assert fetched.title == "Test FAQ"

    def test_update_source(self, library):
        """Update a knowledge source."""
        from src.knowledge.engine import KnowledgeSourceData
        k = library.create_source(KnowledgeSourceData(
            source_type="faq", title="Original Title"))
        k.title = "Updated Title"
        k.content = "New content"
        updated = library.update_source(k)
        assert updated.title == "Updated Title"
        assert updated.content == "New content"

    def test_delete_source(self, library):
        """Soft-delete a knowledge source."""
        from src.knowledge.engine import KnowledgeSourceData
        k = library.create_source(KnowledgeSourceData(
            source_type="faq", title="Delete Me"))
        assert library.delete_source(k.id) is True
        # Should no longer appear in list
        sources = library.list_by_type()
        titles = [s.title for s in sources]
        assert "Delete Me" not in titles

    def test_list_by_type(self, library):
        """List sources filtered by type."""
        from src.knowledge.engine import KnowledgeSourceData
        library.create_source(KnowledgeSourceData(source_type="faq", title="FAQ 1"))
        library.create_source(KnowledgeSourceData(source_type="sop", title="SOP 1"))
        library.create_source(KnowledgeSourceData(source_type="faq", title="FAQ 2"))
        faqs = library.list_by_type("faq")
        assert len(faqs) == 2

    def test_all_source_types(self, library):
        """Support all knowledge source types."""
        from src.knowledge.engine import KnowledgeSourceData
        types = ["policy_document", "claim_guide", "company_circular",
                 "sop", "faq", "case_note", "training", "market_notice"]
        for st in types:
            k = library.create_source(KnowledgeSourceData(source_type=st, title=f"Test {st}"))
            assert k.source_type == st


# ══════════════════════════════════════════════════════════════════
# 2. Semantic Retrieval (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestSemanticRetrieval:
    """Verify search across knowledge sources."""

    def test_search_finds_relevant(self, retrieval, seeded_library):
        """Search finds relevant sources."""
        results = retrieval.search("cancer treatment")
        assert len(results) >= 1
        # Content has cancer mention, not necessarily title
        assert any("cancer" in r.excerpt.lower() for r in results)

    def test_search_by_motor_claim(self, retrieval, seeded_library):
        """Search for motor claim finds FAQ."""
        results = retrieval.search("motor claim procedure")
        assert len(results) >= 1
        assert any("motor" in r.title.lower() for r in results)

    def test_search_returns_excerpt(self, retrieval, seeded_library):
        """Search returns relevant excerpt."""
        results = retrieval.search("BNM guidelines")
        if results:
            assert len(results[0].excerpt) > 0

    def test_search_empty_query(self, retrieval):
        """Empty query returns empty results."""
        results = retrieval.search("")
        assert len(results) == 0

    def test_search_filter_by_type(self, retrieval, seeded_library):
        """Search filtered by source type."""
        results = retrieval.search("claim", source_type="faq")
        for r in results:
            assert r.source_type == "faq"


# ══════════════════════════════════════════════════════════════════
# 3. CaseRecord CRUD (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestCaseRecord:
    """Verify CaseRecord CRUD."""

    def test_create_case(self, cases):
        """Create a case record."""
        from src.knowledge.engine import CaseRecordData
        c = cases.create_case(CaseRecordData(
            category="claim_rejected", title="Cancer claim rejected",
            summary="Claim rejected due to pre-existing exclusion",
            outcome="Client appealed, eventually approved",
            lessons="Always verify waiting period before submitting",
            tags=["cancer", "waiting_period"],
        ))
        assert c.id
        assert c.category == "claim_rejected"
        assert c.is_published is True

    def test_get_case(self, cases):
        """Get a case record by ID."""
        from src.knowledge.engine import CaseRecordData
        c = cases.create_case(CaseRecordData(
            category="successful_appeal", title="Appeal success"))
        fetched = cases.get_case(c.id)
        assert fetched.title == "Appeal success"

    def test_update_case(self, cases):
        """Update a case record."""
        from src.knowledge.engine import CaseRecordData
        c = cases.create_case(CaseRecordData(
            category="claim_rejected", title="Original"))
        c.title = "Updated"
        c.outcome = "Resolved"
        updated = cases.update_case(c)
        assert updated.title == "Updated"
        assert updated.outcome == "Resolved"

    def test_delete_case(self, cases):
        """Delete a case record."""
        from src.knowledge.engine import CaseRecordData
        c = cases.create_case(CaseRecordData(
            category="complaint", title="Delete"))
        assert cases.delete_case(c.id) is True
        assert cases.get_case(c.id) is None

    def test_list_cases_by_category(self, cases):
        """List cases filtered by category."""
        from src.knowledge.engine import CaseRecordData
        cases.create_case(CaseRecordData(category="claim_rejected", title="A"))
        cases.create_case(CaseRecordData(category="claim_rejected", title="B"))
        cases.create_case(CaseRecordData(category="successful_appeal", title="C"))
        rejected = cases.list_cases(category="claim_rejected")
        assert len(rejected) == 2


# ══════════════════════════════════════════════════════════════════
# 4. Case Search (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestCaseSearch:
    """Verify case search and matching."""

    def test_search_cases_by_keyword(self, cases):
        """Search cases by keyword."""
        from src.knowledge.engine import CaseRecordData
        cases.create_case(CaseRecordData(
            category="claim_rejected", title="Cancer claim",
            summary="Pre-existing condition exclusion"))
        cases.create_case(CaseRecordData(
            category="successful_appeal", title="Motor appeal",
            summary="Damage assessment dispute"))
        results = cases.search_cases("cancer")
        assert len(results) == 1

    def test_search_cases_empty_query(self, cases):
        """Empty query returns recent cases."""
        from src.knowledge.engine import CaseRecordData
        cases.create_case(CaseRecordData(category="complaint", title="A"))
        results = cases.search_cases("")
        assert len(results) >= 1

    def test_find_similar_cases(self, cases):
        """Find cases similar by category."""
        from src.knowledge.engine import CaseRecordData
        cases.create_case(CaseRecordData(
            category="claim_rejected", title="Similar 1",
            tags=["cancer"]))
        cases.create_case(CaseRecordData(
            category="claim_rejected", title="Similar 2",
            tags=["motor"]))
        similar = cases.find_similar_cases("claim_rejected")
        assert len(similar) == 2


# ══════════════════════════════════════════════════════════════════
# 5. Reasoning Engine (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestReasoningEngine:
    """Verify explainable reasoning with evidence."""

    def test_answer_with_evidence(self, session, seeded_library):
        """Reasoning returns answer with evidence."""
        from src.knowledge.engine import ReasoningEngine
        engine = ReasoningEngine(session)
        result = engine.answer("What does the policy say about cancer treatment?")
        assert result.answer
        assert len(result.evidence) >= 1
        assert len(result.query) > 0

    def test_answer_no_results(self, session):
        """Query with no matches returns graceful answer."""
        from src.knowledge.engine import ReasoningEngine
        engine = ReasoningEngine(session)
        result = engine.answer("xyznonexistent12345")
        assert result.answer
        # No evidence = low confidence
        assert result.confidence == "low"

    def test_answer_logged(self, session, seeded_library):
        """Reasoning is logged for audit."""
        from src.knowledge.engine import ReasoningEngine
        engine = ReasoningEngine(session)
        engine.answer("How to file a claim?")
        from src.database.models import ReasoningLog
        log_count = session.query(ReasoningLog).count()
        assert log_count >= 1

    def test_high_confidence_with_good_evidence(self, session, seeded_library):
        """Multiple high-confidence sources give high confidence."""
        from src.knowledge.engine import ReasoningEngine
        engine = ReasoningEngine(session)
        result = engine.answer("motor claim procedure")
        # Should find the FAQ
        if len(result.evidence) >= 2:
            assert result.confidence in ("high", "medium")

    def test_structure_includes_confidence(self, session, seeded_library):
        """Result includes confidence level."""
        from src.knowledge.engine import ReasoningEngine
        engine = ReasoningEngine(session)
        result = engine.answer("cancer")
        assert result.confidence in ("high", "medium", "low")


# ══════════════════════════════════════════════════════════════════
# 6. E2E Flow (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestE2EKnowledge:
    """End-to-end: Knowledge → Search → Cases → Reasoning."""

    def test_knowledge_to_search_to_reasoning(self, session, seeded_library):
        """Full flow: seed knowledge → search → reason with evidence."""
        from src.knowledge.engine import ReasoningEngine

        # Answer a complex question
        engine = ReasoningEngine(session)
        result = engine.answer("What are the new BNM guidelines for replacement policies?")

        # Should have found the circular
        assert result.answer
        has_circular = any(
            e.source_type == "company_circular" for e in result.evidence
        )
        assert has_circular

    def test_case_record_lifecycle(self, session):
        """Create → search → update → delete a case record."""
        from src.knowledge.engine import CaseIntelligence, CaseRecordData
        cases = CaseIntelligence(session)

        # Create
        c = cases.create_case(CaseRecordData(
            category="renewal_negotiation", title="Premium increase negotiation",
            summary="Client negotiated 15% discount on renewal",
            outcome="Success", lessons="Start early, provide competitor quotes",
        ))
        assert c.id

        # Search
        found = cases.search_cases("negotiation")
        assert len(found) >= 1

        # Update
        c.outcome = "Partial success"
        updated = cases.update_case(c)
        assert updated.outcome == "Partial success"

        # Delete
        assert cases.delete_case(c.id) is True

    def test_multiple_knowledge_types(self, library):
        """All source types can be created and listed."""
        from src.knowledge.engine import KnowledgeSourceData
        types = ["policy_document", "faq", "sop", "training"]
        for st in types:
            library.create_source(KnowledgeSourceData(source_type=st, title=f"Doc-{st}"))
        all_sources = library.list_by_type()
        db_types = set(s.source_type for s in all_sources)
        for st in types:
            assert st in db_types

    def test_reasoning_with_cases(self, session, cases):
        """Reasoning includes case records when relevant."""
        from src.knowledge.engine import ReasoningEngine, CaseRecordData
        from src.knowledge.engine import KnowledgeSourceData, KnowledgeLibrary

        library = KnowledgeLibrary(session)
        library.create_source(KnowledgeSourceData(
            source_type="policy_document", title="Medical policy",
            content="Cancer treatment covered up to RM200k",
            tags=["cancer", "medical"],
        ))

        cases.create_case(CaseRecordData(
            category="claim_rejected", title="Cancer claim appeal",
            summary="Client successfully appealed cancer claim denial",
            outcome="Approved after appeal", lessons="Document everything",
        ))

        engine = ReasoningEngine(session)
        result = engine.answer("cancer claim appeal")
        has_case = any(e.source_type == "case_record" for e in result.evidence)
        assert has_case
