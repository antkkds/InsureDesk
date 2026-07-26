"""Tests: PI-18 Predictive & Family Intelligence.

Scope: ~35 tests covering:
- Family Members CRUD (create, read, update, delete)
- Household management
- Life Events CRUD
- Health Score calculation
- Predictive Opportunity detection
- Daily Planner generation
- E2E flow
"""

from __future__ import annotations

import pytest
from datetime import date, timedelta


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def session():
    from src.database.db_manager import init_db, get_engine, get_session
    engine = get_engine(":memory:")
    init_db(engine)
    return get_session(engine)


@pytest.fixture
def family_repo(session):
    from src.predictive.engine import FamilyRepository
    return FamilyRepository(session)


@pytest.fixture
def customer(session):
    """Create a test customer."""
    from src.database.models import Customer
    c = Customer(name="Test Customer", phone="0123456789")
    session.add(c)
    session.commit()
    return c


@pytest.fixture
def customer_with_family(session, family_repo, customer):
    """Create a customer with spouse and 2 children."""
    from src.predictive.engine import FamilyMemberData
    family_repo.create_member(FamilyMemberData(
        customer_id=str(customer.id), relationship="spouse",
        full_name="Spouse Tan", date_of_birth="1985-06-15",
    ))
    family_repo.create_member(FamilyMemberData(
        customer_id=str(customer.id), relationship="child",
        full_name="Child A", date_of_birth="2010-03-20", is_dependent=True,
    ))
    family_repo.create_member(FamilyMemberData(
        customer_id=str(customer.id), relationship="child",
        full_name="Child B", date_of_birth="2015-08-10", is_dependent=True,
    ))
    return customer


# ══════════════════════════════════════════════════════════════════
# 1. Family Members CRUD (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestFamilyMembers:
    """Verify FamilyMember CRUD."""

    def test_create_member(self, family_repo, customer):
        """Create a family member."""
        from src.predictive.engine import FamilyMemberData
        m = family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="spouse",
            full_name="Alice Tan", date_of_birth="1990-01-01",
        ))
        assert m.id
        assert m.relationship == "spouse"
        assert m.full_name == "Alice Tan"

    def test_list_members(self, family_repo, customer):
        """List all family members for a customer."""
        from src.predictive.engine import FamilyMemberData
        family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="spouse", full_name="A"))
        family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="child", full_name="B"))
        members = family_repo.list_members(str(customer.id))
        assert len(members) == 2

    def test_get_member(self, family_repo, customer):
        """Get a family member by ID."""
        from src.predictive.engine import FamilyMemberData
        m = family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="child", full_name="Test Child"))
        fetched = family_repo.get_member(m.id)
        assert fetched.full_name == "Test Child"

    def test_update_member(self, family_repo, customer):
        """Update a family member."""
        from src.predictive.engine import FamilyMemberData
        m = family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="child", full_name="Old Name"))
        m.full_name = "New Name"
        m.is_dependent = True
        updated = family_repo.update_member(m)
        assert updated.full_name == "New Name"
        assert updated.is_dependent is True

    def test_delete_member(self, family_repo, customer):
        """Delete a family member."""
        from src.predictive.engine import FamilyMemberData
        m = family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="spouse", full_name="Delete Me"))
        assert family_repo.delete_member(m.id) is True
        assert family_repo.get_member(m.id) is None

    def test_multiple_relationships(self, family_repo, customer):
        """Support all relationship types."""
        from src.predictive.engine import FamilyMemberData
        for rel in ["spouse", "child", "parent", "sibling", "other"]:
            m = family_repo.create_member(FamilyMemberData(
                customer_id=str(customer.id), relationship=rel, full_name=f"Test {rel}"))
            assert m.relationship == rel


# ══════════════════════════════════════════════════════════════════
# 2. Household Management (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestHouseholds:
    """Verify household grouping."""

    def test_create_household(self, family_repo, customer):
        """Create a household."""
        from src.predictive.engine import HouseholdData
        h = family_repo.create_household(HouseholdData(
            primary_customer_id=str(customer.id), name="Tan Family"))
        assert h.id
        assert h.name == "Tan Family"

    def test_add_to_household(self, family_repo, session, customer):
        """Add a customer to a household."""
        from src.predictive.engine import HouseholdData
        from src.database.models import Customer
        c2 = Customer(name="Second Member")
        session.add(c2)
        session.commit()
        h = family_repo.create_household(HouseholdData(
            primary_customer_id=str(customer.id)))
        # Add primary customer + new member
        family_repo.add_to_household(h.id, str(customer.id), "primary")
        assert family_repo.add_to_household(h.id, str(c2.id)) is True
        members = family_repo.get_household_members(h.id)
        assert len(members) == 2

    def test_get_household_members(self, family_repo, customer):
        """Get all members of a household."""
        from src.predictive.engine import HouseholdData
        h = family_repo.create_household(HouseholdData(
            primary_customer_id=str(customer.id)))
        family_repo.add_to_household(h.id, str(customer.id), "primary")
        members = family_repo.get_household_members(h.id)
        assert len(members) >= 1


# ══════════════════════════════════════════════════════════════════
# 3. Life Events (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestLifeEvents:
    """Verify life event tracking."""

    def test_create_life_event(self, family_repo, customer):
        """Create a life event."""
        from src.predictive.engine import LifeEventData
        e = family_repo.create_life_event(LifeEventData(
            customer_id=str(customer.id), event_type="child_university",
            event_date="2028-09-01", reminder_offset_days=90,
            notes="Eldest child starting university",
        ))
        assert e.id
        assert e.event_type == "child_university"
        assert e.is_acknowledged is False

    def test_list_life_events(self, family_repo, customer):
        """List life events for a customer."""
        from src.predictive.engine import LifeEventData
        family_repo.create_life_event(LifeEventData(
            customer_id=str(customer.id), event_type="child_turns_18"))
        family_repo.create_life_event(LifeEventData(
            customer_id=str(customer.id), event_type="retirement"))
        events = family_repo.list_life_events(customer_id=str(customer.id))
        assert len(events) == 2

    def test_acknowledge_life_event(self, family_repo, customer):
        """Acknowledge a life event."""
        from src.predictive.engine import LifeEventData
        e = family_repo.create_life_event(LifeEventData(
            customer_id=str(customer.id), event_type="newborn"))
        acknowledged = family_repo.acknowledge_life_event(e.id)
        assert acknowledged.is_acknowledged is True

    def test_filter_by_type(self, family_repo, customer):
        """Filter life events by type."""
        from src.predictive.engine import LifeEventData
        family_repo.create_life_event(LifeEventData(
            customer_id=str(customer.id), event_type="child_turns_18"))
        family_repo.create_life_event(LifeEventData(
            customer_id=str(customer.id), event_type="retirement"))
        events = family_repo.list_life_events(event_type="child_turns_18")
        assert len(events) == 1


# ══════════════════════════════════════════════════════════════════
# 4. Health Score (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestHealthScore:
    """Verify customer health score calculation."""

    def test_baseline_score(self, session, customer):
        """Customer with no policies gets baseline score."""
        from src.predictive.engine import HealthScoreService
        svc = HealthScoreService(session)
        score = svc.calculate(str(customer.id))
        assert 0 <= score.score <= 100
        # No policies, no family = deductions
        assert score.score < 50

    def test_score_with_policies(self, session, customer):
        """Customer with multiple active policies gets higher score."""
        from src.predictive.engine import HealthScoreService
        from src.database.models import Policy
        for ptype in ["life", "medical", "motor"]:
            session.add(Policy(
                customer_id=str(customer.id), company="Test",
                policy_number=f"P{ptype}", policy_type=ptype,
                status="active",
            ))
        session.commit()
        svc = HealthScoreService(session)
        score = svc.calculate(str(customer.id))
        assert score.score >= 50  # Multiple policies boost score

    def test_score_with_family(self, session, customer_with_family):
        """Family information boosts score."""
        from src.predictive.engine import HealthScoreService
        svc = HealthScoreService(session)
        score = svc.calculate(str(customer_with_family.id))
        # Having family info should increase from baseline
        assert score.score > 30

    def test_score_with_lapsed_policies(self, session, customer):
        """Lapsed policies reduce score."""
        from src.predictive.engine import HealthScoreService
        from src.database.models import Policy
        for i in range(3):
            session.add(Policy(
                customer_id=str(customer.id), company="Test",
                policy_number=f"L{i}", status="lapsed",
            ))
        session.commit()
        svc = HealthScoreService(session)
        score = svc.calculate(str(customer.id))
        assert score.score < 50  # Lapsed policies reduce

    def test_score_drivers_are_present(self, session, customer_with_family):
        """Health score includes driver explanations."""
        from src.predictive.engine import HealthScoreService
        from src.database.models import Policy
        c = customer_with_family
        for ptype in ["life", "medical"]:
            session.add(Policy(
                customer_id=str(c.id), company="Test",
                policy_number=f"P{ptype}", policy_type=ptype,
                status="active",
            ))
        session.commit()
        svc = HealthScoreService(session)
        score = svc.calculate(str(c.id))
        assert len(score.drivers) >= 1  # Has at least one driver


# ══════════════════════════════════════════════════════════════════
# 5. Predictive Opportunities (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestPredictiveOpportunities:
    """Verify opportunity detection rules."""

    def test_child_approaching_18(self, session, family_repo, customer):
        """Child aged 16-18 triggers education opportunity."""
        from src.predictive.engine import PredictiveService, FamilyMemberData
        # Child born 2008 = 18 years old (in 2026)
        family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="child",
            full_name="Teen Child", date_of_birth="2008-06-15",
        ))
        svc = PredictiveService(session)
        opps = svc.detect_opportunities(str(customer.id))
        education = [o for o in opps if o.type == "education"]
        assert len(education) >= 1

    def test_elderly_parent_triggers_medical(self, session, family_repo, customer):
        """Parent aged 65+ triggers medical review."""
        from src.predictive.engine import PredictiveService, FamilyMemberData
        family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="parent",
            full_name="Elder Parent", date_of_birth="1955-01-01",  # 71 years old
        ))
        svc = PredictiveService(session)
        opps = svc.detect_opportunities(str(customer.id))
        medical = [o for o in opps if o.type == "medical"]
        assert len(medical) >= 1

    def test_single_policy_triggers_cross_sell(self, session, customer):
        """Single policy type triggers upgrade opportunity."""
        from src.predictive.engine import PredictiveService
        from src.database.models import Policy
        session.add(Policy(
            customer_id=str(customer.id), company="Test",
            policy_number="P001", policy_type="motor", status="active",
        ))
        session.commit()
        svc = PredictiveService(session)
        opps = svc.detect_opportunities(str(customer.id))
        upgrade = [o for o in opps if o.type == "upgrade"]
        assert len(upgrade) >= 1

    def test_new_baby_triggers_protection(self, session, family_repo, customer):
        """New baby (age <1) triggers protection opportunity."""
        from src.predictive.engine import PredictiveService, FamilyMemberData
        family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="child",
            full_name="New Baby", date_of_birth="2026-06-01",  # <1 year
        ))
        svc = PredictiveService(session)
        opps = svc.detect_opportunities(str(customer.id))
        protection = [o for o in opps if o.type == "protection"]
        assert len(protection) >= 1

    def test_no_family_info_triggers_gap(self, session, customer):
        """No family info triggers information gap."""
        from src.predictive.engine import PredictiveService
        svc = PredictiveService(session)
        opps = svc.detect_opportunities(str(customer.id))
        info_gap = [o for o in opps if o.type == "information_gap"]
        assert len(info_gap) >= 1


# ══════════════════════════════════════════════════════════════════
# 6. Daily Planner (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestDailyPlanner:
    """Verify AI Daily Planner generation."""

    def test_plan_has_date(self, session):
        """Daily plan has today's date."""
        from src.predictive.engine import DailyPlannerService
        svc = DailyPlannerService(session)
        plan = svc.generate_plan()
        assert plan.date == date.today().isoformat()

    def test_plan_with_urgent_renewals(self, session, customer):
        """Renewals due within 7 days become critical items."""
        from src.predictive.engine import DailyPlannerService
        from src.database.models import Policy
        near_future = (date.today() + timedelta(days=3)).isoformat()
        session.add(Policy(
            customer_id=str(customer.id), company="GE",
            policy_number="P001", status="active",
            end_date=near_future,
        ))
        session.commit()
        svc = DailyPlannerService(session)
        plan = svc.generate_plan()
        critical = [i for i in plan.items if i.priority == "critical"]
        assert len(critical) >= 1
        assert "Renewal" in critical[0].action

    def test_plan_with_health_concerns(self, session, customer):
        """Low health scores trigger medium/high items."""
        from src.predictive.engine import DailyPlannerService
        svc = DailyPlannerService(session)
        plan = svc.generate_plan()
        # Customer has no policies, no family = low score
        health_items = [i for i in plan.items if i.category == "health"]
        assert len(health_items) >= 1

    def test_plan_estimate_time(self, session):
        """Plan estimates total time."""
        from src.predictive.engine import DailyPlannerService
        svc = DailyPlannerService(session)
        plan = svc.generate_plan()
        assert plan.total_estimated_minutes >= 0


# ══════════════════════════════════════════════════════════════════
# 7. E2E Flow (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestE2EFamilyPredictive:
    """End-to-end: Family → Health → Opportunities → Planner."""

    def test_full_family_health_plan_flow(self, session, family_repo, customer):
        """E2E: Record family → Calculate health → Detect opps → Daily plan."""
        from src.predictive.engine import (
            FamilyMemberData, HealthScoreService, PredictiveService, DailyPlannerService
        )
        from src.database.models import Policy

        # Step 1: Add family
        family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="spouse",
            full_name="Spouse", date_of_birth="1988-03-15",
        ))
        family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="child",
            full_name="Child", date_of_birth="2008-07-20",
        ))

        # Step 2: Add single policy
        session.add(Policy(
            customer_id=str(customer.id), company="Test",
            policy_number="P001", policy_type="motor", status="active",
        ))
        session.commit()

        # Step 3: Calculate health score
        health = HealthScoreService(session)
        score = health.calculate(str(customer.id))
        assert score.score > 0

        # Step 4: Detect opportunities
        pred = PredictiveService(session)
        opps = pred.detect_opportunities(str(customer.id))
        # Should have education (child 18), upgrade (single motor), info gap(no - has family)
        types = set(o.type for o in opps)
        assert "education" in types or "upgrade" in types

        # Step 5: Generate daily plan
        planner = DailyPlannerService(session)
        plan = planner.generate_plan()
        assert plan.date == date.today().isoformat()

    def test_life_event_creates_planner_item(self, session, family_repo, customer):
        """Life events within 30 days appear in daily plan."""
        from src.predictive.engine import (
            LifeEventData, DailyPlannerService, FamilyMemberData
        )
        family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="child",
            full_name="Child", date_of_birth="2010-01-01",
        ))
        near_event = (date.today() + timedelta(days=14)).isoformat()
        family_repo.create_life_event(LifeEventData(
            customer_id=str(customer.id), event_type="child_turns_18",
            event_date=near_event, notes="Child turning 18",
        ))
        planner = DailyPlannerService(session)
        plan = planner.generate_plan()
        life_events = [i for i in plan.items if i.category == "life_event"]
        assert any("child_turns_18" in i.action.lower() or "turns 18" in i.action.lower()
                   for i in life_events)

    def test_score_improves_with_more_data(self, session, family_repo, customer):
        """Adding more data improves health score."""
        from src.predictive.engine import (
            FamilyMemberData, HealthScoreService
        )
        from src.database.models import Policy

        health = HealthScoreService(session)
        baseline = health.calculate(str(customer.id))

        # Add policies + family
        for ptype in ["life", "medical", "motor"]:
            session.add(Policy(
                customer_id=str(customer.id), company="Test",
                policy_number=f"P{ptype}", policy_type=ptype, status="active",
            ))
        family_repo.create_member(FamilyMemberData(
            customer_id=str(customer.id), relationship="spouse",
            full_name="Spouse", date_of_birth="1990-01-01",
        ))
        session.commit()

        improved = health.calculate(str(customer.id))
        assert improved.score > baseline.score

    def test_opportunities_sorted_by_probability(self, session, customer):
        """Opportunities are sorted high → medium → low."""
        from src.predictive.engine import PredictiveService
        svc = PredictiveService(session)
        opps = svc.detect_opportunities(str(customer.id))
        if len(opps) >= 2:
            prob_order = {"high": 0, "medium": 1, "low": 2}
            for i in range(len(opps) - 1):
                assert prob_order.get(opps[i].probability, 3) <= prob_order.get(opps[i + 1].probability, 3)

    def test_plan_capped_at_15_items(self, session, customer):
        """Daily plan is capped at 15 items."""
        from src.predictive.engine import DailyPlannerService
        from src.database.models import Policy
        # Create many customers with urgent renewals
        for i in range(20):
            from src.database.models import Customer
            c = Customer(name=f"Bulk {i}")
            session.add(c)
            session.flush()
            session.add(Policy(
                customer_id=str(c.id), company="Test",
                policy_number=f"B{i}", status="active",
                end_date=(date.today() + timedelta(days=2)).isoformat(),
            ))
        session.commit()
        svc = DailyPlannerService(session)
        plan = svc.generate_plan()
        assert len(plan.items) <= 15
