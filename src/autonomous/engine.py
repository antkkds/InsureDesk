"""InsureDesk — PI-20: Autonomous Operations Intelligence.

Module A — Goal Engine (goals, metrics, progress)
Module B — Proactive Opportunity Engine (auto-schedule actions)
Module C — Autonomous Review Cycle (morning briefing)
Module D — Continuous Improvement (track outcomes)
"""

import uuid
from datetime import datetime, timezone, date
from typing import Optional, List, Dict
from dataclasses import dataclass, field


def _now():
    return datetime.now(timezone.utc)


def _today() -> str:
    return date.today().isoformat()


# ── Domain Models ────────────────────────────────────────────────

@dataclass
class OperationalGoalData:
    id: str = ""
    name: str = ""
    description: str = ""
    metric_name: str = ""
    current_value: float = 0.0
    target_value: float = 100.0
    unit: str = "%"
    status: str = "on_track"
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class OpportunityActionData:
    id: str = ""
    customer_id: str = ""
    category: str = ""
    priority: str = "medium"
    title: str = ""
    description: str = ""
    recommended_action: str = ""
    status: str = "pending"
    requires_approval: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class RecommendationOutcomeData:
    id: str = ""
    action_id: str = ""
    customer_id: str = ""
    recommendation_type: str = ""
    was_accepted: bool = False
    was_successful: bool = False
    outcome_notes: str = ""
    recorded_at: str = ""


@dataclass
class MorningReview:
    """The autonomous morning briefing."""
    date: str = ""
    urgent_customers: list = field(default_factory=list)
    renewals_due: list = field(default_factory=list)
    market_alerts: list = field(default_factory=list)
    coverage_gaps: list = field(default_factory=list)
    pending_communications: list = field(default_factory=list)
    goals: list = field(default_factory=list)
    summary: str = ""


# ══════════════════════════════════════════════════════════════════
# Module A: Goal Engine
# ══════════════════════════════════════════════════════════════════

class GoalEngine:
    """Manage operational goals and compute progress."""

    DEFAULT_GOALS = [
        {"name": "Renewal Rate", "metric_name": "renewal_rate",
         "target_value": 95.0, "unit": "%", "description": "Maintain policy renewal rate above 95%"},
        {"name": "Overdue Tasks", "metric_name": "overdue_tasks",
         "target_value": 0, "unit": "tasks", "description": "Clear all overdue tasks"},
        {"name": "High-Risk Customers", "metric_name": "critical_customers",
         "target_value": 0, "unit": "customers", "description": "No unattended high-risk customers"},
    ]

    def __init__(self, session):
        self.session = session

    def initialize_defaults(self):
        """Seed default goals if none exist."""
        from src.database.models import OperationalGoal
        if self.session.query(OperationalGoal).count() > 0:
            return
        for g in self.DEFAULT_GOALS:
            goal = OperationalGoal(
                name=g["name"], description=g["description"],
                metric_name=g["metric_name"],
                current_value=0.0, target_value=g["target_value"],
                unit=g["unit"],
            )
            self.session.add(goal)
        self.session.commit()

    def list_goals(self) -> List[OperationalGoalData]:
        from src.database.models import OperationalGoal
        goals = self.session.query(OperationalGoal).filter(
            OperationalGoal.is_active == True
        ).all()
        return [self._to_data(g) for g in goals]

    def update_goal(self, data: OperationalGoalData) -> Optional[OperationalGoalData]:
        from src.database.models import OperationalGoal
        g = self.session.query(OperationalGoal).filter(
            OperationalGoal.id == data.id
        ).first()
        if not g:
            return None
        g.current_value = data.current_value if data.current_value is not None else g.current_value
        # Auto-determine status
        if g.target_value > 0:
            ratio = g.current_value / g.target_value if g.target_value else 0
            if g.metric_name == "overdue_tasks" or g.metric_name == "critical_customers":
                # Lower is better
                if g.current_value <= g.target_value:
                    g.status = "on_track"
                elif g.current_value <= g.target_value * 2:
                    g.status = "needs_attention"
                else:
                    g.status = "critical"
            else:
                # Higher is better
                if ratio >= 1.0:
                    g.status = "on_track"
                elif ratio >= 0.8:
                    g.status = "needs_attention"
                else:
                    g.status = "critical"
        self.session.commit()
        return self._to_data(g)

    def compute_all(self):
        """Recompute all goal metrics from current data."""
        from src.database.models import OperationalGoal, Policy, TeamTask

        goals = self.session.query(OperationalGoal).filter(
            OperationalGoal.is_active == True
        ).all()

        for g in goals:
            if g.metric_name == "renewal_rate":
                total = self.session.query(Policy).count()
                active = self.session.query(Policy).filter(
                    Policy.status == "active"
                ).count()
                g.current_value = round(active / total * 100, 1) if total > 0 else 0.0

            elif g.metric_name == "overdue_tasks":
                g.current_value = self.session.query(TeamTask).filter(
                    TeamTask.status.in_(["pending", "in_progress"])
                ).count()

            elif g.metric_name == "critical_customers":
                from src.database.models import Customer
                g.current_value = self.session.query(Customer).count()
                # Rough proxy: count customers with lapsed policies
                lapsed = self.session.query(Policy).filter(
                    Policy.status == "lapsed"
                ).count()
                g.current_value = lapsed

            # Auto-status
            if g.metric_name in ("overdue_tasks", "critical_customers"):
                if g.current_value <= g.target_value:
                    g.status = "on_track"
                elif g.current_value <= max(g.target_value * 2, 5):
                    g.status = "needs_attention"
                else:
                    g.status = "critical"
            else:
                ratio = g.current_value / g.target_value if g.target_value else 0
                if ratio >= 1.0:
                    g.status = "on_track"
                elif ratio >= 0.8:
                    g.status = "needs_attention"
                else:
                    g.status = "critical"

        self.session.commit()

    def _to_data(self, g) -> OperationalGoalData:
        return OperationalGoalData(
            id=str(g.id), name=g.name or "",
            description=g.description or "",
            metric_name=g.metric_name or "",
            current_value=float(g.current_value or 0),
            target_value=float(g.target_value or 100),
            unit=g.unit or "%",
            status=g.status or "on_track",
            is_active=bool(g.is_active),
            created_at=g.created_at.isoformat() if g.created_at else "",
            updated_at=g.updated_at.isoformat() if g.updated_at else "",
        )


# ══════════════════════════════════════════════════════════════════
# Module B: Proactive Opportunity Engine
# ══════════════════════════════════════════════════════════════════

class ProactiveEngine:
    """Auto-detect and schedule actions from existing intelligence."""

    def __init__(self, session):
        self.session = session

    def scan_and_schedule(self) -> List[OpportunityActionData]:
        """Scan all data sources and create pending opportunity actions."""
        actions = []

        # Renewal risks from predictive engine signals
        actions.extend(self._scan_renewal_risks())

        # Detected coverage gaps
        actions.extend(self._scan_coverage_gaps())

        # Family events approaching
        actions.extend(self._scan_family_events())

        return actions

    def _scan_renewal_risks(self) -> List[OpportunityActionData]:
        """Find policies expiring within 14 days."""
        from src.database.models import Policy, Customer
        from datetime import timedelta
        today = date.today()
        cutoff = today + timedelta(days=14)
        actions = []

        policies = self.session.query(Policy, Customer).join(
            Customer, Policy.customer_id == Customer.id
        ).filter(
            Policy.status == "active",
        ).all()

        for policy, customer in policies:
            if policy.end_date:
                try:
                    end = date.fromisoformat(policy.end_date)
                    days_left = (end - today).days
                    if 0 <= days_left <= 14:
                        action = OpportunityActionData(
                            customer_id=str(customer.id),
                            category="renewal_risk",
                            priority="critical" if days_left <= 3 else "high",
                            title=f"Renewal due: {customer.name} - {policy.policy_number}",
                            description=f"{policy.company} policy expires in {days_left} days",
                            recommended_action=f"Contact {customer.name} about renewal",
                            requires_approval=False,
                        )
                        saved = self._save_action(action)
                        actions.append(saved)
                except ValueError:
                    pass
        return actions

    def _scan_coverage_gaps(self) -> List[OpportunityActionData]:
        """Find customers with only one policy type."""
        from src.database.models import Customer, Policy
        from sqlalchemy import func

        customer_types = (
            self.session.query(Policy.customer_id, func.count(func.distinct(Policy.policy_type)))
            .filter(Policy.status == "active")
            .group_by(Policy.customer_id)
            .having(func.count(func.distinct(Policy.policy_type)) == 1)
            .all()
        )

        actions = []
        for cid, _ in customer_types:
            customer = self.session.query(Customer).filter(Customer.id == cid).first()
            if customer:
                action = OpportunityActionData(
                    customer_id=str(cid),
                    category="coverage_gap",
                    priority="medium",
                    title=f"Single coverage: {customer.name}",
                    description="Customer only has one policy type",
                    recommended_action="Review cross-sell opportunities",
                )
                saved = self._save_action(action)
                actions.append(saved)
        return actions

    def _scan_family_events(self) -> List[OpportunityActionData]:
        """Find upcoming family life events."""
        from src.database.models import LifeEvent, Customer
        from datetime import timedelta
        today = date.today()
        cutoff = today + timedelta(days=30)

        events = self.session.query(LifeEvent, Customer).join(
            Customer, LifeEvent.customer_id == Customer.id
        ).filter(LifeEvent.is_acknowledged == False).all()

        actions = []
        for ev, customer in events:
            if ev.event_date:
                try:
                    ev_date = date.fromisoformat(ev.event_date)
                    if today <= ev_date <= cutoff:
                        action = OpportunityActionData(
                            customer_id=str(customer.id),
                            category="family_event",
                            priority="medium",
                            title=f"Life event: {customer.name} - {ev.event_type}",
                            description=f"{ev.event_type.replace('_', ' ')} on {ev.event_date}",
                            recommended_action=ev.notes or "Review customer needs",
                        )
                        saved = self._save_action(action)
                        actions.append(saved)
                except ValueError:
                    pass
        return actions

    def _save_action(self, data: OpportunityActionData) -> OpportunityActionData:
        """Persist an opportunity action to database."""
        from src.database.models import OpportunityAction
        a = OpportunityAction(
            customer_id=data.customer_id or None,
            category=data.category,
            priority=data.priority,
            title=data.title,
            description=data.description or "",
            recommended_action=data.recommended_action or "",
            requires_approval=data.requires_approval,
        )
        self.session.add(a)
        self.session.commit()
        return self._action_to_data(a)

    def list_pending(self) -> List[OpportunityActionData]:
        from src.database.models import OpportunityAction
        actions = self.session.query(OpportunityAction).filter(
            OpportunityAction.status == "pending"
        ).order_by(
            # Custom sort: critical first
            OpportunityAction.priority.desc(),
            OpportunityAction.created_at.asc()
        ).all()
        return [self._action_to_data(a) for a in actions]

    def approve(self, action_id: str) -> bool:
        from src.database.models import OpportunityAction
        a = self.session.query(OpportunityAction).filter(
            OpportunityAction.id == action_id
        ).first()
        if not a:
            return False
        a.status = "approved"
        self.session.commit()
        return True

    def complete(self, action_id: str) -> bool:
        from src.database.models import OpportunityAction
        a = self.session.query(OpportunityAction).filter(
            OpportunityAction.id == action_id
        ).first()
        if not a:
            return False
        a.status = "completed"
        self.session.commit()
        return True

    def _action_to_data(self, a) -> OpportunityActionData:
        return OpportunityActionData(
            id=str(a.id),
            customer_id=str(a.customer_id) if a.customer_id else "",
            category=a.category or "",
            priority=a.priority or "medium",
            title=a.title or "",
            description=a.description or "",
            recommended_action=a.recommended_action or "",
            status=a.status or "pending",
            requires_approval=bool(a.requires_approval),
            created_at=a.created_at.isoformat() if a.created_at else "",
            updated_at=a.updated_at.isoformat() if a.updated_at else "",
        )


# ══════════════════════════════════════════════════════════════════
# Module C: Autonomous Review Cycle
# ══════════════════════════════════════════════════════════════════

class ReviewEngine:
    """Generate the autonomous morning review/briefing."""

    def __init__(self, session, goal_engine: GoalEngine = None,
                 proactive: ProactiveEngine = None):
        self.session = session
        self.goal_engine = goal_engine or GoalEngine(session)
        self.proactive = proactive or ProactiveEngine(session)

    def generate_morning_review(self) -> MorningReview:
        """Generate the complete morning briefing."""
        # Update goals
        self.goal_engine.compute_all()
        goals = self.goal_engine.list_goals()

        # Get pending actions
        self.proactive.scan_and_schedule()
        pending = self.proactive.list_pending()

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        pending.sort(key=lambda a: priority_order.get(a.priority, 4))

        urgent = [a for a in pending if a.priority == "critical"]
        renewals = [a for a in pending if a.category == "renewal_risk"]
        gaps = [a for a in pending if a.category == "coverage_gap"]
        events = [a for a in pending if a.category == "family_event"]

        # Summary
        total_actions = len(pending)
        urgent_count = len(urgent)
        goal_alerts = [g for g in goals if g.status == "critical"]
        summary_parts = []
        if urgent_count:
            summary_parts.append(f"{urgent_count} urgent items")
        if goal_alerts:
            summary_parts.append(f"{len(goal_alerts)} goal(s) at critical")
        summary_parts.append(f"{total_actions} total action items")
        summary = " · ".join(summary_parts) if summary_parts else "All clear. No pending actions."

        return MorningReview(
            date=_today(),
            urgent_customers=[{"name": a.title, "action": a.recommended_action}
                              for a in urgent[:5]],
            renewals_due=[{"title": a.title, "priority": a.priority}
                          for a in renewals[:8]],
            market_alerts=[a for a in pending if a.category == "market_alert"],
            coverage_gaps=[{"title": a.title, "customer_id": a.customer_id}
                           for a in gaps[:5]],
            pending_communications=[a for a in pending
                                    if a.category in ("family_event",)],
            goals=[{"name": g.name, "current": g.current_value,
                    "target": g.target_value, "unit": g.unit, "status": g.status}
                   for g in goals],
            summary=summary,
        )


# ══════════════════════════════════════════════════════════════════
# Module D: Continuous Improvement
# ══════════════════════════════════════════════════════════════════

class ImprovementTracker:
    """Track outcomes of recommendations for continuous improvement."""

    def __init__(self, session):
        self.session = session

    def record(self, data: RecommendationOutcomeData) -> RecommendationOutcomeData:
        from src.database.models import RecommendationOutcome
        r = RecommendationOutcome(
            action_id=data.action_id or None,
            customer_id=data.customer_id or None,
            recommendation_type=data.recommendation_type,
            was_accepted=data.was_accepted,
            was_successful=data.was_successful,
            outcome_notes=data.outcome_notes or "",
        )
        self.session.add(r)
        self.session.commit()
        return self._to_data(r)

    def list_outcomes(self, limit: int = 20) -> List[RecommendationOutcomeData]:
        from src.database.models import RecommendationOutcome
        outcomes = self.session.query(RecommendationOutcome).order_by(
            RecommendationOutcome.recorded_at.desc()
        ).limit(limit).all()
        return [self._to_data(o) for o in outcomes]

    def get_success_rate(self, recommendation_type: str = None) -> Dict:
        """Calculate acceptance and success rates."""
        from src.database.models import RecommendationOutcome
        q = self.session.query(RecommendationOutcome)
        if recommendation_type:
            q = q.filter(RecommendationOutcome.recommendation_type == recommendation_type)

        outcomes = q.all()
        total = len(outcomes)
        if total == 0:
            return {"total": 0, "acceptance_rate": 0, "success_rate": 0}

        accepted = sum(1 for o in outcomes if o.was_accepted)
        successful = sum(1 for o in outcomes if o.was_successful)
        return {
            "total": total,
            "accepted": accepted,
            "successful": successful,
            "acceptance_rate": round(accepted / total * 100, 1),
            "success_rate": round(successful / total * 100, 1) if accepted > 0 else 0,
        }

    def _to_data(self, o) -> RecommendationOutcomeData:
        return RecommendationOutcomeData(
            id=str(o.id),
            action_id=str(o.action_id) if o.action_id else "",
            customer_id=str(o.customer_id) if o.customer_id else "",
            recommendation_type=o.recommendation_type or "",
            was_accepted=bool(o.was_accepted),
            was_successful=bool(o.was_successful),
            outcome_notes=o.outcome_notes or "",
            recorded_at=o.recorded_at.isoformat() if o.recorded_at else "",
        )
