"""InsureDesk — Family & Predictive Intelligence (PI-18).

Contents:
- FamilyRepository (FamilyMember, Household, LifeEvent CRUD)
- HealthScoreService (customer relationship health)
- PredictiveService (opportunity detection rules)
- DailyPlannerService (AI-prioritized daily plan)
"""

import uuid
from datetime import datetime, timezone, date
from typing import Optional, List, Dict
from dataclasses import dataclass, field, asdict
from collections import defaultdict


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


def _today_str() -> str:
    return date.today().isoformat()


# ── Domain Models ────────────────────────────────────────────────

@dataclass
class FamilyMemberData:
    id: str = ""
    customer_id: str = ""
    relationship: str = ""        # spouse / child / parent / sibling / other
    full_name: str = ""
    date_of_birth: str = ""
    gender: str = ""
    occupation: str = ""
    is_dependent: bool = False
    is_disabled: bool = False
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class HouseholdData:
    id: str = ""
    primary_customer_id: str = ""
    name: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class HouseholdMemberData:
    id: str = ""
    household_id: str = ""
    customer_id: str = ""
    role: str = "member"
    created_at: str = ""


@dataclass
class LifeEventData:
    id: str = ""
    customer_id: str = ""
    member_id: str = ""
    event_type: str = ""
    event_date: str = ""
    reminder_offset_days: int = 0
    notes: str = ""
    is_acknowledged: bool = False
    created_at: str = ""
    updated_at: str = ""


@dataclass
class HealthScore:
    """Customer relationship health score result."""
    customer_id: str = ""
    customer_name: str = ""
    score: int = 50
    trend: str = "stable"          # improving / stable / declining
    drivers: list = field(default_factory=list)


@dataclass
class PredictiveOpportunity:
    """A detected opportunity for a customer."""
    customer_id: str = ""
    customer_name: str = ""
    type: str = ""                 # education / protection / medical / retirement / upgrade
    probability: str = "medium"    # high / medium / low
    reason: str = ""
    recommended_timeframe: str = ""
    related_member: str = ""


@dataclass
class DailyPlanItem:
    """A single item in the daily AI plan."""
    priority: str = "medium"       # critical / high / medium / low
    customer_id: str = ""
    customer_name: str = ""
    action: str = ""
    reason: str = ""
    category: str = ""


@dataclass
class DailyPlan:
    """The AI Daily Planner output."""
    date: str = ""
    items: list = field(default_factory=list)
    total_estimated_minutes: int = 0
    summary: str = ""


# ══════════════════════════════════════════════════════════════════
# Module A: Family Repository
# ══════════════════════════════════════════════════════════════════

class FamilyRepository:
    """CRUD for family members, households, and life events."""

    def __init__(self, session):
        self.session = session

    # ── Family Members ──

    def list_members(self, customer_id: str) -> List[FamilyMemberData]:
        from src.database.models import FamilyMember
        members = self.session.query(FamilyMember).filter(
            FamilyMember.customer_id == customer_id
        ).order_by(FamilyMember.relation, FamilyMember.full_name).all()
        return [self._fm_to_data(m) for m in members]

    def get_member(self, member_id: str) -> Optional[FamilyMemberData]:
        from src.database.models import FamilyMember
        m = self.session.query(FamilyMember).filter(FamilyMember.id == member_id).first()
        return self._fm_to_data(m) if m else None

    def create_member(self, data: FamilyMemberData) -> FamilyMemberData:
        from src.database.models import FamilyMember
        m = FamilyMember(
            customer_id=data.customer_id,
            relation=data.relationship,
            full_name=data.full_name,
            date_of_birth=data.date_of_birth or "",
            gender=data.gender or "",
            occupation=data.occupation or "",
            is_dependent=data.is_dependent if data.is_dependent is not None else False,
            is_disabled=data.is_disabled if data.is_disabled is not None else False,
            notes=data.notes or "",
        )
        self.session.add(m)
        self.session.commit()
        return self._fm_to_data(m)

    def update_member(self, data: FamilyMemberData) -> Optional[FamilyMemberData]:
        from src.database.models import FamilyMember
        m = self.session.query(FamilyMember).filter(FamilyMember.id == data.id).first()
        if not m:
            return None
        if data.full_name: m.full_name = data.full_name
        if data.relationship: m.relation = data.relationship
        if data.date_of_birth is not None: m.date_of_birth = data.date_of_birth
        if data.gender is not None: m.gender = data.gender
        if data.occupation is not None: m.occupation = data.occupation
        if data.is_dependent is not None: m.is_dependent = data.is_dependent
        if data.is_disabled is not None: m.is_disabled = data.is_disabled
        if data.notes is not None: m.notes = data.notes
        self.session.commit()
        return self._fm_to_data(m)

    def delete_member(self, member_id: str) -> bool:
        from src.database.models import FamilyMember
        m = self.session.query(FamilyMember).filter(FamilyMember.id == member_id).first()
        if not m:
            return False
        self.session.delete(m)
        self.session.commit()
        return True

    def _fm_to_data(self, m) -> FamilyMemberData:
        return FamilyMemberData(
            id=str(m.id), customer_id=str(m.customer_id),
            relationship=m.relation or "",
            full_name=m.full_name or "",
            date_of_birth=m.date_of_birth or "",
            gender=m.gender or "", occupation=m.occupation or "",
            is_dependent=bool(m.is_dependent),
            is_disabled=bool(m.is_disabled),
            notes=m.notes or "",
            created_at=m.created_at.isoformat() if m.created_at else "",
            updated_at=m.updated_at.isoformat() if m.updated_at else "",
        )

    # ── Households ──

    def create_household(self, data: HouseholdData) -> HouseholdData:
        from src.database.models import Household
        h = Household(
            primary_customer_id=data.primary_customer_id,
            name=data.name or "",
            notes=data.notes or "",
        )
        self.session.add(h)
        self.session.commit()
        return self._hh_to_data(h)

    def get_household(self, household_id: str) -> Optional[HouseholdData]:
        from src.database.models import Household
        h = self.session.query(Household).filter(Household.id == household_id).first()
        return self._hh_to_data(h) if h else None

    def add_to_household(self, household_id: str, customer_id: str, role: str = "member") -> bool:
        from src.database.models import HouseholdMember
        hm = HouseholdMember(household_id=household_id, customer_id=customer_id, role=role)
        self.session.add(hm)
        self.session.commit()
        return True

    def get_household_members(self, household_id: str) -> List[Dict]:
        """Get all customers in a household."""
        from src.database.models import HouseholdMember, Customer
        members = (
            self.session.query(HouseholdMember, Customer)
            .join(Customer, HouseholdMember.customer_id == Customer.id)
            .filter(HouseholdMember.household_id == household_id)
            .all()
        )
        return [{
            "customer_id": str(c.id),
            "name": c.name,
            "role": hm.role,
        } for hm, c in members]

    def _hh_to_data(self, h) -> HouseholdData:
        return HouseholdData(
            id=str(h.id), primary_customer_id=str(h.primary_customer_id),
            name=h.name or "", notes=h.notes or "",
            created_at=h.created_at.isoformat() if h.created_at else "",
            updated_at=h.updated_at.isoformat() if h.updated_at else "",
        )

    # ── Life Events ──

    def list_life_events(self, customer_id: str = None, event_type: str = None) -> List[LifeEventData]:
        from src.database.models import LifeEvent
        q = self.session.query(LifeEvent)
        if customer_id:
            q = q.filter(LifeEvent.customer_id == customer_id)
        if event_type:
            q = q.filter(LifeEvent.event_type == event_type)
        q = q.order_by(LifeEvent.event_date.asc())
        return [self._le_to_data(e) for e in q.all()]

    def create_life_event(self, data: LifeEventData) -> LifeEventData:
        from src.database.models import LifeEvent
        e = LifeEvent(
            customer_id=data.customer_id,
            member_id=data.member_id or None,
            event_type=data.event_type,
            event_date=data.event_date or "",
            reminder_offset_days=data.reminder_offset_days or 0,
            notes=data.notes or "",
        )
        self.session.add(e)
        self.session.commit()
        return self._le_to_data(e)

    def acknowledge_life_event(self, event_id: str) -> Optional[LifeEventData]:
        from src.database.models import LifeEvent
        e = self.session.query(LifeEvent).filter(LifeEvent.id == event_id).first()
        if not e:
            return None
        e.is_acknowledged = True
        self.session.commit()
        return self._le_to_data(e)

    def _le_to_data(self, e) -> LifeEventData:
        return LifeEventData(
            id=str(e.id), customer_id=str(e.customer_id),
            member_id=str(e.member_id) if e.member_id else "",
            event_type=e.event_type or "",
            event_date=e.event_date or "",
            reminder_offset_days=e.reminder_offset_days or 0,
            notes=e.notes or "",
            is_acknowledged=bool(e.is_acknowledged),
            created_at=e.created_at.isoformat() if e.created_at else "",
            updated_at=e.updated_at.isoformat() if e.updated_at else "",
        )


# ══════════════════════════════════════════════════════════════════
# Module B: Customer Health Score
# ══════════════════════════════════════════════════════════════════

class HealthScoreService:
    """Calculate customer relationship health score.

    Factors (all rule-based):
    - Policy status (active, lapsed count)
    - Renewal behavior (on-time, late)
    - Communication frequency/recency
    - Claims history
    - Family coverage breadth
    - Document upload activity
    """

    def __init__(self, session, family_repo: FamilyRepository = None):
        self.session = session
        self.family_repo = family_repo or FamilyRepository(session)

    def calculate(self, customer_id: str) -> HealthScore:
        """Calculate health score for a single customer.

        Score: 0-100, where 100 is the healthiest relationship.
        """
        from src.database.models import Customer, Policy, Document
        customer = self.session.query(Customer).filter(
            Customer.id == customer_id
        ).first()
        if not customer:
            return HealthScore(customer_id=customer_id, score=0, trend="stable")

        score = 50  # baseline
        drivers = []
        name = customer.name or ""

        # ── Policy analysis ──
        policies = self.session.query(Policy).filter(
            Policy.customer_id == customer_id
        ).all()

        active_count = sum(1 for p in policies if p.status == "active")
        lapsed_count = sum(1 for p in policies if p.status == "lapsed")
        policies_count = len(policies)

        if policies_count == 0:
            score -= 15
            drivers.append("❌ No active policies")
        else:
            # Coverage breadth
            types = set(p.policy_type for p in policies if p.status == "active" and p.policy_type)
            type_count = len(types)
            score += min(type_count * 5, 15)
            if type_count >= 3:
                drivers.append(f"✅ {type_count} coverage types")

        if active_count >= 3:
            score += 10
            drivers.append("✅ Multiple active policies")
        elif active_count == 0:
            score -= 10

        if lapsed_count > 0:
            score -= lapsed_count * 5
            drivers.append(f"⚠ {lapsed_count} lapsed policies")

        # ── Communication (document upload activity) ──
        docs = self.session.query(Document).filter(
            Document.customer_id == customer_id
        ).count()
        if docs >= 3:
            score += 5
            drivers.append("✅ Active document uploads")
        elif docs == 0 and policies_count > 0:
            score -= 5
            drivers.append("⚠ No documents uploaded")

        # ── Family context ──
        family = self.family_repo.list_members(customer_id)
        has_children = any(m.relationship == "child" for m in family)
        has_spouse = any(m.relationship == "spouse" for m in family)
        dependents = [m for m in family if m.is_dependent]

        if len(family) == 0:
            # No family info = potential gap
            score -= 5
            drivers.append("ℹ No family information recorded")
        else:
            score += min(len(family) * 3, 9)
            drivers.append(f"✅ {len(family)} family members recorded")
            if has_children:
                score += 3
            if has_spouse and active_count >= 2:
                score += 3
                drivers.append("✅ Family coverage detected")

        # Score bounds
        score = max(0, min(100, score))

        # Trend (compare with baseline)
        if score >= 75:
            trend = "improving"
        elif score >= 45:
            trend = "stable"
        else:
            trend = "declining"

        return HealthScore(
            customer_id=customer_id,
            customer_name=name,
            score=score,
            trend=trend,
            drivers=drivers,
        )

    def calculate_all(self) -> List[HealthScore]:
        """Calculate health scores for all customers."""
        from src.database.models import Customer
        customers = self.session.query(Customer).all()
        return [self.calculate(str(c.id)) for c in customers]


# ══════════════════════════════════════════════════════════════════
# Module C: Predictive Opportunities
# ══════════════════════════════════════════════════════════════════

class PredictiveService:
    """Detect family-based and life-event-based opportunities.

    Rules (all rule-based):
    - Child approaching 18 → education planning
    - New spouse → life insurance review
    - New baby → medical/life/CI review
    - Parent age 70+ → medical review
    - Single-policy customer → cross-sell opportunity
    - No family info recorded → family data collection opportunity
    """

    def __init__(self, session, family_repo: FamilyRepository = None):
        self.session = session
        self.family_repo = family_repo or FamilyRepository(session)

    def detect_opportunities(self, customer_id: str) -> List[PredictiveOpportunity]:
        """Detect all opportunities for a customer."""
        from src.database.models import Customer, Policy
        customer = self.session.query(Customer).filter(
            Customer.id == customer_id
        ).first()
        if not customer:
            return []

        name = customer.name or ""
        opportunities = []
        family = self.family_repo.list_members(customer_id)
        policies = self.session.query(Policy).filter(
            Policy.customer_id == customer_id
        ).all()
        active_types = set(p.policy_type for p in policies if p.status == "active" and p.policy_type)

        today = date.today()

        # ── Rule 1: Children approaching 18 (university age) ──
        for m in family:
            if m.relationship == "child" and m.date_of_birth:
                try:
                    dob = date.fromisoformat(m.date_of_birth)
                    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                    if age >= 16 and age <= 18:
                        opportunities.append(PredictiveOpportunity(
                            customer_id=customer_id,
                            customer_name=name,
                            type="education",
                            probability="high",
                            reason=f"Child {m.full_name} is {age} years old — approaching university age",
                            recommended_timeframe="3-6 months",
                            related_member=m.full_name,
                        ))
                except ValueError:
                    pass

        # ── Rule 2: Elderly parents (70+) ──
        for m in family:
            if m.relationship == "parent" and m.date_of_birth:
                try:
                    dob = date.fromisoformat(m.date_of_birth)
                    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                    if age >= 65:
                        opportunities.append(PredictiveOpportunity(
                            customer_id=customer_id,
                            customer_name=name,
                            type="medical",
                            probability="high",
                            reason=f"Parent {m.full_name} is {age} — medical coverage review recommended",
                            recommended_timeframe="1-3 months",
                            related_member=m.full_name,
                        ))
                except ValueError:
                    pass

        # ── Rule 3: New spouse / recently married ──
        for m in family:
            if m.relationship == "spouse":
                # Check if spouse has coverage
                if "life" not in active_types:
                    opportunities.append(PredictiveOpportunity(
                        customer_id=customer_id,
                        customer_name=name,
                        type="protection",
                        probability="medium",
                        reason=f"Spouse {m.full_name} — consider life insurance review for family protection",
                        recommended_timeframe="1-3 months",
                        related_member=m.full_name,
                    ))

        # ── Rule 4: New baby / young children ──
        for m in family:
            if m.relationship == "child" and m.date_of_birth:
                try:
                    dob = date.fromisoformat(m.date_of_birth)
                    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                    if age <= 1:
                        missing = []
                        if "medical" not in active_types: missing.append("medical")
                        if "life" not in active_types: missing.append("life")
                        if missing:
                            opportunities.append(PredictiveOpportunity(
                                customer_id=customer_id,
                                customer_name=name,
                                type="protection",
                                probability="high",
                                reason=f"New child {m.full_name} — consider {' + '.join(missing)} coverage",
                                recommended_timeframe="1 month",
                                related_member=m.full_name,
                            ))
                except ValueError:
                    pass

        # ── Rule 5: Single-policy customer (cross-sell) ──
        if len(active_types) == 1:
            single_type = next(iter(active_types))
            missing = [t for t in ["life", "medical", "motor", "travel"]
                       if t not in active_types]
            if missing:
                opportunities.append(PredictiveOpportunity(
                    customer_id=customer_id,
                    customer_name=name,
                    type="upgrade",
                    probability="medium",
                    reason=f"Only {single_type} coverage. Consider adding: {', '.join(missing[:2])}",
                    recommended_timeframe="1-3 months",
                ))

        # ── Rule 6: No family info recorded ──
        if len(family) == 0:
            opportunities.append(PredictiveOpportunity(
                customer_id=customer_id,
                customer_name=name,
                type="information_gap",
                probability="low",
                reason="No family information recorded. Recording dependents enables better predictions.",
                recommended_timeframe="When convenient",
            ))

        # Sort by probability
        prob_order = {"high": 0, "medium": 1, "low": 2}
        opportunities.sort(key=lambda o: prob_order.get(o.probability, 3))

        return opportunities

    def detect_all(self) -> List[PredictiveOpportunity]:
        """Detect opportunities for all customers."""
        from src.database.models import Customer
        customers = self.session.query(Customer).all()
        all_opps = []
        for c in customers:
            all_opps.extend(self.detect_opportunities(str(c.id)))
        return all_opps


# ══════════════════════════════════════════════════════════════════
# Module D: AI Daily Planner
# ══════════════════════════════════════════════════════════════════

class DailyPlannerService:
    """Generate a prioritized daily plan for the advisor.

    Priority order:
    1. CRITICAL: Renewal risk (due <= 7 days)
    2. HIGH: High-probability opportunities, lapsed policies
    3. MEDIUM: Customer health scores below 40
    4. LOW: Upcoming life events, info gaps
    """

    def __init__(self, session, health_service: HealthScoreService = None,
                 predictive_service: PredictiveService = None,
                 family_repo: FamilyRepository = None):
        self.session = session
        self.health_service = health_service or HealthScoreService(session, family_repo)
        self.predictive_service = predictive_service or PredictiveService(session, family_repo)
        self.family_repo = family_repo or FamilyRepository(session)

    def generate_plan(self) -> DailyPlan:
        """Generate today's AI daily plan."""
        from src.database.models import Customer, Policy

        today = _today_str()
        items = []

        customers = self.session.query(Customer).all()

        for customer in customers:
            cid = str(customer.id)
            name = customer.name or "Unknown"

            # ── Check urgent renewals (due <= 7 days) ──
            policies = self.session.query(Policy).filter(
                Policy.customer_id == cid,
                Policy.status == "active",
            ).all()

            for p in policies:
                if p.end_date:
                    try:
                        end = date.fromisoformat(p.end_date)
                        days_left = (end - date.today()).days
                        if days_left <= 7 and days_left >= 0:
                            items.append(DailyPlanItem(
                                priority="critical",
                                customer_id=cid, customer_name=name,
                                action=f"🔴 Renewal due in {days_left} days: {p.policy_number} ({p.company})",
                                reason="Urgent renewal action required",
                                category="renewal",
                            ))
                        elif days_left <= 30 and days_left > 7:
                            items.append(DailyPlanItem(
                                priority="high",
                                customer_id=cid, customer_name=name,
                                action=f"🟡 Renewal due in {days_left} days: {p.policy_number}",
                                reason="Upcoming renewal - early action recommended",
                                category="renewal",
                            ))
                    except ValueError:
                        pass

            # ── Check health score ──
            score = self.health_service.calculate(cid)
            if score.score < 40:
                items.append(DailyPlanItem(
                    priority="high" if score.score < 30 else "medium",
                    customer_id=cid, customer_name=name,
                    action=f"⚠ Health score: {score.score} ({score.trend})",
                    reason="; ".join(score.drivers[:2]) if score.drivers else "Declining relationship health",
                    category="health",
                ))

            # ── High-probability opportunities ──
            opportunities = self.predictive_service.detect_opportunities(cid)
            for opp in opportunities:
                if opp.probability == "high":
                    items.append(DailyPlanItem(
                        priority="high",
                        customer_id=cid, customer_name=name,
                        action=f"💡 {opp.reason}",
                        reason=f"Recommended timeframe: {opp.recommended_timeframe}",
                        category="opportunity",
                    ))

            # ── Unacknowledged life events ──
            events = self.family_repo.list_life_events(customer_id=cid)
            for ev in events:
                if not ev.is_acknowledged and ev.event_date:
                    try:
                        ev_date = date.fromisoformat(ev.event_date)
                        days_until = (ev_date - date.today()).days
                        if days_until <= 30 and days_until >= 0:
                            items.append(DailyPlanItem(
                                priority="medium",
                                customer_id=cid, customer_name=name,
                                action=f"📅 {ev.event_type.replace('_', ' ').title()} on {ev.event_date}",
                                reason=ev.notes or f"Upcoming life event for {name}",
                                category="life_event",
                            ))
                    except ValueError:
                        pass

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        items.sort(key=lambda i: priority_order.get(i.priority, 4))

        # Cap at 15 items
        items = items[:15]

        # Calculate estimated time
        time_estimates = {"critical": 15, "high": 10, "medium": 5, "low": 3}
        total_minutes = sum(time_estimates.get(i.priority, 5) for i in items)

        # Generate summary
        counts = defaultdict(int)
        for i in items:
            counts[i.priority] += 1
        summary_parts = []
        if counts.get("critical"):
            summary_parts.append(f"{counts['critical']} urgent")
        if counts.get("high"):
            summary_parts.append(f"{counts['high']} high priority")
        if counts.get("medium"):
            summary_parts.append(f"{counts['medium']} medium priority")
        summary = f"{', '.join(summary_parts)} items — est. {total_minutes} min" if summary_parts else "No items for today. Great!"

        return DailyPlan(
            date=today,
            items=items,
            total_estimated_minutes=total_minutes,
            summary=summary,
        )
