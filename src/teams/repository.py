"""InsureDesk — Team and Agency Collaboration (PI-16).

Provides:
- TeamRepository (team CRUD + member management)
- AssignmentService (customer/task assignment + workload balancing)
- KnowledgeRepository (internal knowledge sharing)
- TeamDashboardService (manager metrics + team overview)
"""

import uuid
from datetime import datetime, timezone, date
from typing import Optional, List, Dict
from dataclasses import dataclass, field, asdict


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


# ── Domain Models ────────────────────────────────────────────────

@dataclass
class TeamData:
    id: str = ""
    name: str = ""
    description: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class TeamMemberData:
    id: str = ""
    team_id: str = ""
    name: str = ""
    role: str = "agent"          # agent / manager / admin
    email: str = ""
    phone: str = ""
    specialties: list = field(default_factory=list)  # ["life", "medical", "motor", "travel"]
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class TeamTaskData:
    id: str = ""
    team_id: str = ""
    assignee_id: str = ""
    customer_id: str = ""
    task_type: str = "general"   # renewal / followup / claim / general
    title: str = ""
    description: str = ""
    priority: str = "medium"     # high / medium / low
    status: str = "pending"      # pending / in_progress / done / cancelled
    due_date: str = ""
    completed_at: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class KnowledgeEntryData:
    id: str = ""
    team_id: str = ""
    title: str = ""
    content: str = ""
    tags: list = field(default_factory=list)
    visibility: str = "team"     # team / public
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class AssignmentData:
    id: str = ""
    team_id: str = ""
    customer_id: str = ""
    agent_id: str = ""
    task_id: str = ""
    assigned_by: str = ""
    assigned_at: str = ""
    status: str = "active"       # active / completed / reassigned
    note: str = ""
    created_at: str = ""
    updated_at: str = ""


# ── Team Repository ──────────────────────────────────────────────

class TeamRepository:
    """CRUD operations for teams and members."""

    def __init__(self, session):
        self.session = session

    # ── Team ──

    def list_all(self) -> List[TeamData]:
        from src.database.models import Team
        teams = self.session.query(Team).order_by(Team.name).all()
        return [self._team_to_data(t) for t in teams]

    def get_by_id(self, team_id: str) -> Optional[TeamData]:
        from src.database.models import Team
        t = self.session.query(Team).filter(Team.id == team_id).first()
        return self._team_to_data(t) if t else None

    def create(self, data: TeamData) -> TeamData:
        from src.database.models import Team
        t = Team(name=data.name, description=data.description or "")
        self.session.add(t)
        self.session.commit()
        return self._team_to_data(t)

    def update(self, data: TeamData) -> Optional[TeamData]:
        from src.database.models import Team
        t = self.session.query(Team).filter(Team.id == data.id).first()
        if not t:
            return None
        if data.name: t.name = data.name
        if data.description is not None: t.description = data.description
        t.is_active = data.is_active if data.is_active is not None else t.is_active
        self.session.commit()
        return self._team_to_data(t)

    def delete(self, team_id: str) -> bool:
        from src.database.models import Team
        t = self.session.query(Team).filter(Team.id == team_id).first()
        if not t:
            return False
        self.session.delete(t)
        self.session.commit()
        return True

    def _team_to_data(self, t) -> TeamData:
        return TeamData(
            id=str(t.id), name=t.name or "",
            description=t.description or "",
            is_active=t.is_active if t.is_active is not None else True,
            created_at=t.created_at.isoformat() if t.created_at else "",
            updated_at=t.updated_at.isoformat() if t.updated_at else "",
        )

    # ── Members ──

    def list_members(self, team_id: str) -> List[TeamMemberData]:
        from src.database.models import TeamMember
        members = (
            self.session.query(TeamMember)
            .filter(TeamMember.team_id == team_id)
            .order_by(TeamMember.name)
            .all()
        )
        return [self._member_to_data(m) for m in members]

    def get_member(self, member_id: str) -> Optional[TeamMemberData]:
        from src.database.models import TeamMember
        m = self.session.query(TeamMember).filter(TeamMember.id == member_id).first()
        return self._member_to_data(m) if m else None

    def add_member(self, data: TeamMemberData) -> TeamMemberData:
        from src.database.models import TeamMember
        m = TeamMember(
            team_id=data.team_id,
            name=data.name,
            role=data.role or "agent",
            email=data.email or "",
            phone=data.phone or "",
            specialties=data.specialties or [],
            is_active=True,
        )
        self.session.add(m)
        self.session.commit()
        return self._member_to_data(m)

    def update_member(self, data: TeamMemberData) -> Optional[TeamMemberData]:
        from src.database.models import TeamMember
        m = self.session.query(TeamMember).filter(TeamMember.id == data.id).first()
        if not m:
            return None
        if data.name: m.name = data.name
        if data.role: m.role = data.role
        if data.email is not None: m.email = data.email
        if data.phone is not None: m.phone = data.phone
        if data.specialties is not None: m.specialties = data.specialties
        if data.is_active is not None: m.is_active = data.is_active
        self.session.commit()
        return self._member_to_data(m)

    def remove_member(self, member_id: str) -> bool:
        from src.database.models import TeamMember
        m = self.session.query(TeamMember).filter(TeamMember.id == member_id).first()
        if not m:
            return False
        self.session.delete(m)
        self.session.commit()
        return True

    def _member_to_data(self, m) -> TeamMemberData:
        return TeamMemberData(
            id=str(m.id), team_id=str(m.team_id),
            name=m.name or "", role=m.role or "agent",
            email=m.email or "", phone=m.phone or "",
            specialties=list(m.specialties) if m.specialties else [],
            is_active=m.is_active if m.is_active is not None else True,
            created_at=m.created_at.isoformat() if m.created_at else "",
            updated_at=m.updated_at.isoformat() if m.updated_at else "",
        )

    # ── Tasks ──

    def list_tasks(self, team_id: str, status: str = None) -> List[TeamTaskData]:
        from src.database.models import TeamTask
        q = self.session.query(TeamTask).filter(TeamTask.team_id == team_id)
        if status:
            q = q.filter(TeamTask.status == status)
        q = q.order_by(TeamTask.created_at.desc())
        return [self._task_to_data(t) for t in q.all()]

    def list_tasks_by_assignee(self, member_id: str) -> List[TeamTaskData]:
        from src.database.models import TeamTask
        tasks = (
            self.session.query(TeamTask)
            .filter(TeamTask.assignee_id == member_id)
            .order_by(TeamTask.created_at.desc())
            .all()
        )
        return [self._task_to_data(t) for t in tasks]

    def create_task(self, data: TeamTaskData) -> TeamTaskData:
        from src.database.models import TeamTask
        t = TeamTask(
            team_id=data.team_id,
            assignee_id=data.assignee_id or None,
            customer_id=data.customer_id or None,
            task_type=data.task_type or "general",
            title=data.title,
            description=data.description or "",
            priority=data.priority or "medium",
            status="pending",
            due_date=datetime.fromisoformat(data.due_date) if data.due_date else None,
        )
        self.session.add(t)
        self.session.commit()
        return self._task_to_data(t)

    def update_task_status(self, task_id: str, status: str) -> Optional[TeamTaskData]:
        from src.database.models import TeamTask
        t = self.session.query(TeamTask).filter(TeamTask.id == task_id).first()
        if not t:
            return None
        t.status = status
        if status == "done":
            t.completed_at = _now()
        self.session.commit()
        return self._task_to_data(t)

    def assign_task(self, task_id: str, assignee_id: str) -> Optional[TeamTaskData]:
        from src.database.models import TeamTask
        t = self.session.query(TeamTask).filter(TeamTask.id == task_id).first()
        if not t:
            return None
        t.assignee_id = assignee_id
        t.status = "in_progress"
        self.session.commit()
        return self._task_to_data(t)

    def _task_to_data(self, t) -> TeamTaskData:
        return TeamTaskData(
            id=str(t.id), team_id=str(t.team_id),
            assignee_id=str(t.assignee_id) if t.assignee_id else "",
            customer_id=str(t.customer_id) if t.customer_id else "",
            task_type=t.task_type or "general",
            title=t.title or "",
            description=t.description or "",
            priority=t.priority or "medium",
            status=t.status or "pending",
            due_date=t.due_date.isoformat() if t.due_date else "",
            completed_at=t.completed_at.isoformat() if t.completed_at else "",
            created_at=t.created_at.isoformat() if t.created_at else "",
            updated_at=t.updated_at.isoformat() if t.updated_at else "",
        )

    # ── Workload ──

    def get_workload(self, team_id: str) -> List[Dict]:
        """Get workload stats per agent (pending + in_progress tasks)."""
        from src.database.models import TeamTask, TeamMember
        members = self.list_members(team_id)
        workloads = []
        for m in members:
            active_count = (
                self.session.query(TeamTask)
                .filter(
                    TeamTask.assignee_id == m.id,
                    TeamTask.status.in_(["pending", "in_progress"]),
                )
                .count()
            )
            workloads.append({
                "member_id": m.id,
                "name": m.name,
                "role": m.role,
                "active_tasks": active_count,
                "specialties": m.specialties,
            })
        # Sort by active tasks descending (most loaded first)
        workloads.sort(key=lambda w: w["active_tasks"], reverse=True)
        return workloads

    def get_workload_balance(self, team_id: str) -> Dict:
        """Assess if team workload is balanced."""
        workloads = self.get_workload(team_id)
        if not workloads:
            return {"balanced": True, "message": "No members to assess."}
        counts = [w["active_tasks"] for w in workloads]
        avg = sum(counts) / len(counts)
        max_deviation = max(abs(c - avg) for c in counts) if avg > 0 else 0
        if max_deviation > 2:
            return {
                "balanced": False,
                "imbalance_level": "high" if max_deviation > 4 else "medium",
                "avg_tasks": round(avg, 1),
                "max_deviation": round(max_deviation, 1),
                "message": f"Workload imbalance detected. Avg: {avg:.1f}, max deviation: {max_deviation:.1f}",
            }
        return {
            "balanced": True,
            "avg_tasks": round(avg, 1),
            "message": "Team workload is balanced.",
        }


# ── Knowledge Repository ────────────────────────────────────────

class KnowledgeRepository:
    """CRUD for internal knowledge entries."""

    def __init__(self, session):
        self.session = session

    def search(self, team_id: str, query: str = "") -> List[KnowledgeEntryData]:
        from src.database.models import KnowledgeEntry
        q = self.session.query(KnowledgeEntry).filter(
            KnowledgeEntry.team_id == team_id
        )
        if query:
            like = f"%{query}%"
            q = q.filter(
                (KnowledgeEntry.title.like(like)) |
                (KnowledgeEntry.content.like(like))
            )
        q = q.order_by(KnowledgeEntry.updated_at.desc())
        return [self._to_data(e) for e in q.all()]

    def get_by_id(self, entry_id: str) -> Optional[KnowledgeEntryData]:
        from src.database.models import KnowledgeEntry
        e = self.session.query(KnowledgeEntry).filter(
            KnowledgeEntry.id == entry_id
        ).first()
        return self._to_data(e) if e else None

    def create(self, data: KnowledgeEntryData) -> KnowledgeEntryData:
        from src.database.models import KnowledgeEntry
        e = KnowledgeEntry(
            team_id=data.team_id,
            title=data.title,
            content=data.content or "",
            tags=data.tags or [],
            visibility=data.visibility or "team",
            created_by=data.created_by or None,
        )
        self.session.add(e)
        self.session.commit()
        return self._to_data(e)

    def update(self, data: KnowledgeEntryData) -> Optional[KnowledgeEntryData]:
        from src.database.models import KnowledgeEntry
        e = self.session.query(KnowledgeEntry).filter(
            KnowledgeEntry.id == data.id
        ).first()
        if not e:
            return None
        if data.title: e.title = data.title
        if data.content is not None: e.content = data.content
        if data.tags is not None: e.tags = data.tags
        if data.visibility: e.visibility = data.visibility
        self.session.commit()
        return self._to_data(e)

    def delete(self, entry_id: str) -> bool:
        from src.database.models import KnowledgeEntry
        e = self.session.query(KnowledgeEntry).filter(
            KnowledgeEntry.id == entry_id
        ).first()
        if not e:
            return False
        self.session.delete(e)
        self.session.commit()
        return True

    def _to_data(self, e) -> KnowledgeEntryData:
        return KnowledgeEntryData(
            id=str(e.id), team_id=str(e.team_id),
            title=e.title or "", content=e.content or "",
            tags=list(e.tags) if e.tags else [],
            visibility=e.visibility or "team",
            created_by=str(e.created_by) if e.created_by else "",
            created_at=e.created_at.isoformat() if e.created_at else "",
            updated_at=e.updated_at.isoformat() if e.updated_at else "",
        )


# ── Assignment Service ───────────────────────────────────────────

class AssignmentService:
    """Manage customer/task assignments with workload balancing."""

    def __init__(self, session, team_repo: TeamRepository = None):
        self.session = session
        self.team_repo = team_repo or TeamRepository(session)

    def assign_customer(
        self, team_id: str, customer_id: str,
        agent_id: str = None, assigned_by: str = "",
    ) -> Dict:
        """Assign a customer to an agent. If no agent_id, auto-assign."""
        from src.database.models import Assignment

        if not agent_id:
            agent_id = self._select_best_agent(team_id)

        a = Assignment(
            team_id=team_id,
            customer_id=customer_id,
            agent_id=agent_id,
            assigned_by=assigned_by or None,
            status="active",
        )
        self.session.add(a)
        self.session.commit()

        result = {
            "assignment_id": str(a.id),
            "team_id": team_id,
            "customer_id": customer_id,
            "agent_id": agent_id,
            "method": "auto" if not assigned_by else "manual",
        }

        # Auto-create a task for this assignment
        from src.database.models import TeamTask
        task = TeamTask(
            team_id=team_id,
            assignee_id=agent_id,
            customer_id=customer_id,
            task_type="general",
            title=f"Customer follow-up: Assigned",
            status="pending",
        )
        self.session.add(task)
        self.session.commit()
        result["task_id"] = str(task.id)

        return result

    def assign_task(
        self, task_id: str, team_id: str,
        agent_id: str = None, assigned_by: str = "",
    ) -> Dict:
        """Assign an existing task to an agent. Auto-assign if no agent_id."""
        from src.database.models import TeamTask, Assignment

        if not agent_id:
            agent_id = self._select_best_agent(team_id)

        # Update task
        task = self.session.query(TeamTask).filter(TeamTask.id == task_id).first()
        if task:
            task.assignee_id = agent_id
            task.status = "in_progress"

        # Create assignment record
        a = Assignment(
            team_id=team_id,
            task_id=task_id,
            agent_id=agent_id,
            assigned_by=assigned_by or None,
            status="active",
        )
        self.session.add(a)
        self.session.commit()

        return {
            "assignment_id": str(a.id),
            "task_id": task_id,
            "agent_id": agent_id,
            "method": "auto" if not assigned_by else "manual",
        }

    def complete_assignment(self, assignment_id: str) -> bool:
        """Mark assignment as completed."""
        from src.database.models import Assignment
        a = self.session.query(Assignment).filter(
            Assignment.id == assignment_id
        ).first()
        if not a:
            return False
        a.status = "completed"
        self.session.commit()
        return True

    def _select_best_agent(self, team_id: str) -> Optional[str]:
        """Auto-select the best agent based on workload balancing.

        Picks the agent with fewest active tasks (lightest load).
        """
        from src.database.models import TeamMember, TeamTask
        active_agents = (
            self.session.query(TeamMember)
            .filter(
                TeamMember.team_id == team_id,
                TeamMember.is_active == True,
                TeamMember.role.in_(["agent", "manager"]),
            )
            .all()
        )
        if not active_agents:
            return None

        best = None
        lowest_count = float("inf")
        for agent in active_agents:
            count = (
                self.session.query(TeamTask)
                .filter(
                    TeamTask.assignee_id == agent.id,
                    TeamTask.status.in_(["pending", "in_progress"]),
                )
                .count()
            )
            if count < lowest_count:
                lowest_count = count
                best = agent
        return str(best.id) if best else None


# ── Team Dashboard Service ───────────────────────────────────────

class TeamDashboardService:
    """Compute manager-level metrics and team overview."""

    def __init__(self, session, team_repo: TeamRepository = None):
        self.session = session
        self.team_repo = team_repo or TeamRepository(session)

    def get_overview(self, team_id: str) -> Dict:
        """Compute team overview metrics."""
        members = self.team_repo.list_members(team_id)
        tasks = self.team_repo.list_tasks(team_id)

        total_members = len([m for m in members if m.is_active])
        agents = [m for m in members if m.role == "agent"]
        managers = [m for m in members if m.role in ("manager", "admin")]

        pending_tasks = [t for t in tasks if t.status == "pending"]
        in_progress_tasks = [t for t in tasks if t.status == "in_progress"]
        completed_tasks = [t for t in tasks if t.status == "done"]

        # Customers assigned
        from src.database.models import Assignment
        total_customers = (
            self.session.query(Assignment)
            .filter(
                Assignment.team_id == team_id,
                Assignment.status == "active",
            )
            .count()
        )

        # Renewal rate (completed_tasks / total)
        renewal_rate = 0
        total_tasks = len(tasks)
        if total_tasks > 0:
            renewal_rate = round(len(completed_tasks) / total_tasks * 100)

        # Top performer (most completed tasks)
        top_performer = self._get_top_performer(team_id, tasks)
        needs_support = self._get_needs_support(team_id, tasks)

        return {
            "team_id": team_id,
            "total_members": total_members,
            "agents": len(agents),
            "managers": len(managers),
            "total_customers": total_customers,
            "total_tasks": total_tasks,
            "pending_tasks": len(pending_tasks),
            "in_progress_tasks": len(in_progress_tasks),
            "completed_tasks": len(completed_tasks),
            "renewal_rate": renewal_rate,
            "top_performer": top_performer,
            "needs_support": needs_support,
        }

    def get_agent_dashboard(self, member_id: str) -> Dict:
        """Get personalized daily view for an agent."""
        from src.database.models import TeamTask

        tasks = (
            self.session.query(TeamTask)
            .filter(
                TeamTask.assignee_id == member_id,
                TeamTask.status.in_(["pending", "in_progress"]),
            )
            .order_by(
                TeamTask.priority.desc(),  # Not sortable directly, use Python
                TeamTask.created_at.asc(),
            )
            .all()
        )

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_tasks = sorted(
            tasks, key=lambda t: priority_order.get(t.priority or "medium", 1)
        )

        return {
            "member_id": member_id,
            "total_pending": len(tasks),
            "priorities": {
                "high": sum(1 for t in sorted_tasks if t.priority == "high"),
                "medium": sum(1 for t in sorted_tasks if t.priority == "medium"),
                "low": sum(1 for t in sorted_tasks if t.priority == "low"),
            },
            "tasks": [
                {
                    "id": str(t.id),
                    "title": t.title,
                    "task_type": t.task_type,
                    "priority": t.priority,
                    "status": t.status,
                    "due_date": t.due_date.isoformat() if t.due_date else "",
                }
                for t in sorted_tasks
            ],
        }

    def _get_top_performer(self, team_id: str, tasks: List[TeamTaskData]) -> Dict:
        """Find the member with most completed tasks."""
        from collections import Counter
        completion_counts = Counter()
        member_names = {m.id: m.name for m in self.team_repo.list_members(team_id)}

        for t in tasks:
            if t.status == "done" and t.assignee_id:
                completion_counts[t.assignee_id] += 1

        if not completion_counts:
            return {"name": None, "completed": 0}

        top_id, top_count = completion_counts.most_common(1)[0]
        return {"name": member_names.get(top_id, "Unknown"), "completed": top_count}

    def _get_needs_support(self, team_id: str, tasks: List[TeamTaskData]) -> Dict:
        """Find the member with most pending tasks (may need help)."""
        from collections import Counter
        pending_counts = Counter()
        member_names = {m.id: m.name for m in self.team_repo.list_members(team_id)}

        for t in tasks:
            if t.status in ("pending", "in_progress") and t.assignee_id:
                pending_counts[t.assignee_id] += 1

        if not pending_counts:
            return {"name": None, "pending": 0}

        most_id, most_count = pending_counts.most_common(1)[0]
        return {"name": member_names.get(most_id, "Unknown"), "pending": most_count}
