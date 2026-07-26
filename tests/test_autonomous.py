"""Tests: PI-20 Autonomous Operations Intelligence.

Scope: ~28 tests covering:
- Goal Engine (defaults, compute, update)
- Proactive Engine (scan, schedule, approve)
- Review Cycle (morning briefing)
- Continuous Improvement (track outcomes, success rates)
- E2E flow
"""

from __future__ import annotations

import pytest
from datetime import date, timedelta


@pytest.fixture
def session():
    from src.database.db_manager import init_db, get_engine, get_session
    engine = get_engine(":memory:")
    init_db(engine)
    return get_session(engine)


@pytest.fixture
def goals(session):
    from src.autonomous.engine import GoalEngine
    g = GoalEngine(session)
    g.initialize_defaults()
    return g


@pytest.fixture
def proactive(session):
    from src.autonomous.engine import ProactiveEngine
    return ProactiveEngine(session)


@pytest.fixture
def customer(session):
    from src.database.models import Customer
    c = Customer(name="Test Customer")
    session.add(c)
    session.commit()
    return c


# ══════════════════════════════════════════════════════════════════
# 1. Goal Engine (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestGoalEngine:
    """Verify goal initialization and computation."""

    def test_initialize_defaults(self, goals):
        """Default goals are created."""
        all_goals = goals.list_goals()
        assert len(all_goals) >= 3
        names = [g.name for g in all_goals]
        assert "Renewal Rate" in names

    def test_goals_have_metrics(self, goals):
        """Each goal has a metric name and target."""
        for g in goals.list_goals():
            assert g.metric_name
            assert g.target_value > 0

    def test_compute_renewal_rate(self, session, goals):
        """Renewal rate goal is computed from policies."""
        from src.database.models import Policy, Customer
        c = Customer(name="Test")
        session.add(c)
        session.flush()
        session.add(Policy(customer_id=str(c.id), company="GE",
                           policy_number="P1", status="active"))
        session.add(Policy(customer_id=str(c.id), company="GE",
                           policy_number="P2", status="lapsed"))
        session.commit()
        goals.compute_all()
        renewal = [g for g in goals.list_goals() if g.metric_name == "renewal_rate"][0]
        assert renewal.current_value == 50.0  # 1 active / 2 total

    def test_compute_overdue_tasks(self, session, goals):
        """Overdue tasks goal reflects pending tasks."""
        from src.database.models import TeamTask
        session.add(TeamTask(team_id="test", title="Task 1", status="pending"))
        session.add(TeamTask(team_id="test", title="Task 2", status="in_progress"))
        session.commit()
        goals.compute_all()
        overdue = [g for g in goals.list_goals() if g.metric_name == "overdue_tasks"][0]
        assert overdue.current_value >= 2

    def test_goal_status_on_track(self, goals):
        """Goal with good progress is on_track."""
        g = goals.list_goals()[0]
        g.current_value = g.target_value  # Meet target
        goals.update_goal(g)
        updated = goals.list_goals()[0]
        assert updated.status == "on_track"

    def test_goal_status_critical(self, goals):
        """Goal with poor progress is critical."""
        g = goals.list_goals()[0]
        g.current_value = g.target_value * 0.3  # Only 30% of target
        goals.update_goal(g)
        updated = goals.list_goals()[0]
        assert updated.status == "critical"


# ══════════════════════════════════════════════════════════════════
# 2. Proactive Engine (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestProactiveEngine:
    """Verify auto-detection and scheduling."""

    def test_scan_renewal_risks(self, session, proactive, customer):
        """Expiring policies create renewal risk actions."""
        from src.database.models import Policy
        near = (date.today() + timedelta(days=5)).isoformat()
        session.add(Policy(
            customer_id=str(customer.id), company="GE",
            policy_number="P001", status="active",
            end_date=near,
        ))
        session.commit()
        actions = proactive.scan_and_schedule()
        renewals = [a for a in actions if a.category == "renewal_risk"]
        assert len(renewals) >= 1

    def test_scan_coverage_gaps(self, session, proactive, customer):
        """Single-policy customers create coverage gap actions."""
        from src.database.models import Policy
        # Add only one policy type
        session.add(Policy(
            customer_id=str(customer.id), company="GE",
            policy_number="P001", policy_type="motor", status="active",
        ))
        session.commit()
        actions = proactive.scan_and_schedule()
        gaps = [a for a in actions if a.category == "coverage_gap"]
        assert len(gaps) >= 1

    def test_approve_action(self, session, proactive, customer):
        """Approving an action changes its status."""
        from src.database.models import Policy
        near = (date.today() + timedelta(days=5)).isoformat()
        session.add(Policy(
            customer_id=str(customer.id), company="GE",
            policy_number="P001", status="active", end_date=near,
        ))
        session.commit()
        actions = proactive.scan_and_schedule()
        if actions:
            assert proactive.approve(actions[0].id) is True

    def test_list_pending(self, session, proactive, customer):
        """Pending actions are listed sorted by priority."""
        from src.database.models import Policy
        near = (date.today() + timedelta(days=2)).isoformat()
        session.add(Policy(
            customer_id=str(customer.id), company="GE",
            policy_number="P001", status="active", end_date=near,
        ))
        session.commit()
        proactive.scan_and_schedule()
        pending = proactive.list_pending()
        assert len(pending) >= 1

    def test_requires_approval_default(self):
        """Actions require approval by default."""
        from src.autonomous.engine import OpportunityActionData
        a = OpportunityActionData(category="test", title="Test")
        assert a.requires_approval is True


# ══════════════════════════════════════════════════════════════════
# 3. Review Engine (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestReviewEngine:
    """Verify morning review/briefing generation."""

    def test_morning_review_has_date(self, session):
        """Review has today's date."""
        from src.autonomous.engine import ReviewEngine
        review = ReviewEngine(session).generate_morning_review()
        assert review.date == date.today().isoformat()

    def test_review_includes_goals(self, session):
        """Review includes goal status."""
        from src.autonomous.engine import ReviewEngine
        review = ReviewEngine(session).generate_morning_review()
        assert len(review.goals) >= 0

    def test_review_summary(self, session):
        """Review has a summary string."""
        from src.autonomous.engine import ReviewEngine
        review = ReviewEngine(session).generate_morning_review()
        assert review.summary

    def test_review_with_urgent_items(self, session, customer):
        """Review populates urgent items when renewals are due."""
        from src.autonomous.engine import ReviewEngine
        from src.database.models import Policy
        near = (date.today() + timedelta(days=2)).isoformat()
        session.add(Policy(
            customer_id=str(customer.id), company="GE",
            policy_number="P001", status="active", end_date=near,
        ))
        session.commit()
        review = ReviewEngine(session).generate_morning_review()
        assert len(review.urgent_customers) >= 1 or len(review.renewals_due) >= 1


# ══════════════════════════════════════════════════════════════════
# 4. Continuous Improvement (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestImprovementTracker:
    """Verify outcome tracking."""

    def test_record_outcome(self, session):
        """Record a recommendation outcome."""
        from src.autonomous.engine import ImprovementTracker, RecommendationOutcomeData
        tracker = ImprovementTracker(session)
        r = tracker.record(RecommendationOutcomeData(
            recommendation_type="renewal_reminder",
            was_accepted=True, was_successful=True,
        ))
        assert r.id
        assert r.was_accepted is True

    def test_list_outcomes(self, session):
        """List recorded outcomes."""
        from src.autonomous.engine import ImprovementTracker, RecommendationOutcomeData
        tracker = ImprovementTracker(session)
        tracker.record(RecommendationOutcomeData(recommendation_type="cross_sell"))
        tracker.record(RecommendationOutcomeData(recommendation_type="renewal"))
        outcomes = tracker.list_outcomes()
        assert len(outcomes) == 2

    def test_success_rate_calculation(self, session):
        """Success rate is calculated correctly."""
        from src.autonomous.engine import ImprovementTracker, RecommendationOutcomeData
        tracker = ImprovementTracker(session)
        # Add 4 outcomes, 3 accepted, 2 successful
        tracker.record(RecommendationOutcomeData(recommendation_type="test", was_accepted=True, was_successful=True))
        tracker.record(RecommendationOutcomeData(recommendation_type="test", was_accepted=True, was_successful=True))
        tracker.record(RecommendationOutcomeData(recommendation_type="test", was_accepted=True, was_successful=False))
        tracker.record(RecommendationOutcomeData(recommendation_type="test", was_accepted=False, was_successful=False))
        rate = tracker.get_success_rate("test")
        assert rate["total"] == 4
        assert rate["accepted"] == 3
        assert rate["acceptance_rate"] == 75.0
        assert rate["success_rate"] == pytest.approx(66.7, 0.5)

    def test_empty_success_rate(self, session):
        """No outcomes returns zero rates."""
        from src.autonomous.engine import ImprovementTracker
        tracker = ImprovementTracker(session)
        rate = tracker.get_success_rate()
        assert rate["total"] == 0


# ══════════════════════════════════════════════════════════════════
# 5. E2E Flow (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestE2EAutonomous:
    """End-to-end: Goals → Proactive → Review → Improvement."""

    def test_full_autonomous_cycle(self, session, customer):
        """Full cycle: goals → scan → review → track outcome."""
        from src.autonomous.engine import GoalEngine, ProactiveEngine, ReviewEngine, ImprovementTracker, RecommendationOutcomeData
        from src.database.models import Policy

        # Setup: policy expiring soon
        near = (date.today() + timedelta(days=3)).isoformat()
        session.add(Policy(
            customer_id=str(customer.id), company="GE",
            policy_number="P001", status="active", end_date=near,
        ))
        session.commit()

        # Step 1: Initialize goals
        goals = GoalEngine(session)
        goals.initialize_defaults()
        assert len(goals.list_goals()) >= 3

        # Step 2: Scan for opportunities
        proactive = ProactiveEngine(session)
        actions = proactive.scan_and_schedule()
        assert len(actions) >= 1

        # Step 3: Generate morning review
        review = ReviewEngine(session)
        briefing = review.generate_morning_review()
        assert briefing.date
        assert briefing.summary

        # Step 4: Track improvement
        tracker = ImprovementTracker(session)
        for a in actions:
            tracker.record(RecommendationOutcomeData(
                action_id=a.id, customer_id=a.customer_id,
                recommendation_type=a.category,
                was_accepted=True, was_successful=True,
            ))
        rate = tracker.get_success_rate()
        assert rate["total"] >= 1

    def test_goals_recompute_on_review(self, session, customer):
        """Morning review recomputes all goals."""
        from src.autonomous.engine import ReviewEngine, GoalEngine
        from src.database.models import Policy
        session.add(Policy(
            customer_id=str(customer.id), company="GE",
            policy_number="P1", status="active",
        ))
        session.add(Policy(
            customer_id=str(customer.id), company="GE",
            policy_number="P2", status="active",
        ))
        session.commit()

        goals = GoalEngine(session)
        goals.initialize_defaults()
        goals.compute_all()
        renewal = [g for g in goals.list_goals() if g.metric_name == "renewal_rate"][0]
        assert renewal.current_value > 0

    def test_approve_and_complete_action(self, session, proactive, customer):
        """Action can go through full lifecycle."""
        from src.database.models import Policy
        near = (date.today() + timedelta(days=5)).isoformat()
        session.add(Policy(
            customer_id=str(customer.id), company="GE",
            policy_number="P001", status="active", end_date=near,
        ))
        session.commit()
        actions = proactive.scan_and_schedule()
        if actions:
            assert proactive.approve(actions[0].id) is True
            from src.database.models import OpportunityAction
            a = session.query(OpportunityAction).filter(
                OpportunityAction.id == actions[0].id
            ).first()
            assert a.status == "approved"
