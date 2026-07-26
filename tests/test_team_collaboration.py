"""Tests: PI-16 Agency Collaboration — Team, Assignment, Knowledge, Dashboard.

Scope: ~35 tests covering:
- Team CRUD (create, read, update, delete)
- Member management (add, remove, roles)
- Task management (create, assign, status)
- Workload balancing
- Knowledge sharing
- Assignment service
- Team dashboard / metrics
- E2E flow
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def team_repo():
    """Create TeamRepository with in-memory SQLite."""
    from src.database.db_manager import init_db, get_engine, get_session
    from src.teams.repository import TeamRepository
    engine = get_engine(":memory:")
    init_db(engine)
    session = get_session(engine)
    return TeamRepository(session)


@pytest.fixture
def session():
    """Get an in-memory SQLAlchemy session."""
    from src.database.db_manager import init_db, get_engine, get_session
    engine = get_engine(":memory:")
    init_db(engine)
    return get_session(engine)


@pytest.fixture
def knowledge_repo(session):
    from src.teams.repository import KnowledgeRepository
    return KnowledgeRepository(session)


@pytest.fixture
def team_with_members(team_repo):
    """Create a team with 3 members (1 manager, 2 agents)."""
    from src.teams.repository import TeamData, TeamMemberData
    team = team_repo.create(TeamData(name="Test Agency"))
    m1 = team_repo.add_member(TeamMemberData(team_id=team.id, name="Alice", role="manager", specialties=["life", "medical"]))
    m2 = team_repo.add_member(TeamMemberData(team_id=team.id, name="Bob", role="agent", specialties=["motor", "travel"]))
    m3 = team_repo.add_member(TeamMemberData(team_id=team.id, name="Charlie", role="agent", specialties=["medical"]))
    return team_repo, team, [m1, m2, m3]


# ══════════════════════════════════════════════════════════════════
# 1. Team CRUD (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestTeamCRUD:
    """Verify basic team create, read, update, delete."""

    def test_create_team(self, team_repo):
        """Create a team with name and description."""
        from src.teams.repository import TeamData
        data = TeamData(name="My Agency", description="Test team")
        team = team_repo.create(data)
        assert team.id
        assert team.name == "My Agency"
        assert team.description == "Test team"
        assert team.is_active is True

    def test_list_teams(self, team_repo):
        """List all teams."""
        from src.teams.repository import TeamData
        team_repo.create(TeamData(name="Team A"))
        team_repo.create(TeamData(name="Team B"))
        teams = team_repo.list_all()
        assert len(teams) == 2

    def test_get_team_by_id(self, team_repo):
        """Get a team by ID."""
        from src.teams.repository import TeamData
        created = team_repo.create(TeamData(name="Test"))
        fetched = team_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.name == "Test"

    def test_update_team(self, team_repo):
        """Update team name and description."""
        from src.teams.repository import TeamData
        team = team_repo.create(TeamData(name="Old Name"))
        team.name = "New Name"
        team.description = "Updated"
        updated = team_repo.update(team)
        assert updated.name == "New Name"
        assert updated.description == "Updated"

    def test_delete_team(self, team_repo):
        """Delete a team."""
        from src.teams.repository import TeamData
        team = team_repo.create(TeamData(name="Delete Me"))
        assert team_repo.delete(team.id) is True
        assert team_repo.get_by_id(team.id) is None
        assert team_repo.delete("nonexistent") is False


# ══════════════════════════════════════════════════════════════════
# 2. Member Management (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestMemberManagement:
    """Verify member add, list, remove, role assignment."""

    def test_add_member(self, team_repo):
        """Add a member to a team."""
        from src.teams.repository import TeamData, TeamMemberData
        team = team_repo.create(TeamData(name="Test"))
        member = team_repo.add_member(TeamMemberData(team_id=team.id, name="Alice", role="agent"))
        assert member.id
        assert member.name == "Alice"
        assert member.role == "agent"

    def test_list_members(self, team_repo):
        """List all members of a team."""
        from src.teams.repository import TeamData, TeamMemberData
        team = team_repo.create(TeamData(name="Test"))
        team_repo.add_member(TeamMemberData(team_id=team.id, name="A"))
        team_repo.add_member(TeamMemberData(team_id=team.id, name="B"))
        members = team_repo.list_members(team.id)
        assert len(members) == 2

    def test_get_member(self, team_repo):
        """Get a member by ID."""
        from src.teams.repository import TeamData, TeamMemberData
        team = team_repo.create(TeamData(name="Test"))
        member = team_repo.add_member(TeamMemberData(team_id=team.id, name="Alice"))
        fetched = team_repo.get_member(member.id)
        assert fetched.name == "Alice"

    def test_remove_member(self, team_repo):
        """Remove a member from a team."""
        from src.teams.repository import TeamData, TeamMemberData
        team = team_repo.create(TeamData(name="Test"))
        member = team_repo.add_member(TeamMemberData(team_id=team.id, name="Alice"))
        assert team_repo.remove_member(member.id) is True
        assert team_repo.get_member(member.id) is None

    def test_member_role_assign(self, team_repo):
        """Assign different roles to members."""
        from src.teams.repository import TeamData, TeamMemberData
        team = team_repo.create(TeamData(name="Test"))
        for role in ["agent", "manager", "admin"]:
            m = team_repo.add_member(TeamMemberData(team_id=team.id, name=f"User_{role}", role=role))
            assert m.role == role

    def test_member_specialties(self, team_repo):
        """Set and update member specialties."""
        from src.teams.repository import TeamData, TeamMemberData
        team = team_repo.create(TeamData(name="Test"))
        m = team_repo.add_member(TeamMemberData(team_id=team.id, name="Alice", specialties=["life", "medical"]))
        assert "life" in m.specialties
        assert "medical" in m.specialties


# ══════════════════════════════════════════════════════════════════
# 3. Task Management (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestTaskManagement:
    """Verify task creation, assignment, status updates."""

    def test_create_task(self, team_with_members):
        """Create a task in a team."""
        team_repo, team, _ = team_with_members
        from src.teams.repository import TeamTaskData
        task = team_repo.create_task(TeamTaskData(
            team_id=team.id, title="Renewal follow-up",
            task_type="renewal", priority="high",
        ))
        assert task.id
        assert task.title == "Renewal follow-up"
        assert task.status == "pending"

    def test_list_tasks(self, team_with_members):
        """List tasks for a team."""
        team_repo, team, _ = team_with_members
        from src.teams.repository import TeamTaskData
        team_repo.create_task(TeamTaskData(team_id=team.id, title="Task 1"))
        team_repo.create_task(TeamTaskData(team_id=team.id, title="Task 2"))
        tasks = team_repo.list_tasks(team.id)
        assert len(tasks) == 2

    def test_update_task_status(self, team_with_members):
        """Update a task's status."""
        team_repo, team, _ = team_with_members
        from src.teams.repository import TeamTaskData
        task = team_repo.create_task(TeamTaskData(team_id=team.id, title="Test"))
        updated = team_repo.update_task_status(task.id, "done")
        assert updated.status == "done"
        assert updated.completed_at

    def test_assign_task(self, team_with_members):
        """Assign a task to a member."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamTaskData
        task = team_repo.create_task(TeamTaskData(team_id=team.id, title="Test"))
        assigned = team_repo.assign_task(task.id, members[1].id)
        assert assigned.assignee_id == members[1].id
        assert assigned.status == "in_progress"

    def test_list_tasks_by_assignee(self, team_with_members):
        """List tasks assigned to a specific member."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamTaskData
        t1 = team_repo.create_task(TeamTaskData(team_id=team.id, title="T1"))
        t2 = team_repo.create_task(TeamTaskData(team_id=team.id, title="T2"))
        team_repo.assign_task(t1.id, members[1].id)
        team_repo.assign_task(t2.id, members[1].id)
        tasks = team_repo.list_tasks_by_assignee(members[1].id)
        assert len(tasks) == 2


# ══════════════════════════════════════════════════════════════════
# 4. Workload Balancing (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestWorkloadBalancing:
    """Verify workload calculation and balance detection."""

    def test_get_workload(self, team_with_members):
        """Get workload for all members."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamTaskData
        for m in members[:2]:
            t = team_repo.create_task(TeamTaskData(team_id=team.id, title=f"Task for {m.name}"))
            team_repo.assign_task(t.id, m.id)
        workloads = team_repo.get_workload(team.id)
        assert len(workloads) == 3  # all 3 members
        alice = [w for w in workloads if w["name"] == "Alice"][0]
        assert alice["active_tasks"] >= 0

    def test_workload_balanced_when_equal(self, team_with_members):
        """Balanced when all members have similar load."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamTaskData
        # Give same load to all
        for m in members:
            t = team_repo.create_task(TeamTaskData(team_id=team.id, title=f"Task"))
            team_repo.assign_task(t.id, m.id)
        balance = team_repo.get_workload_balance(team.id)
        assert balance.get("balanced") is True

    def test_workload_imbalanced_detected(self, team_with_members):
        """Detect when one member has much more work."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamTaskData
        # Load up one member with many tasks
        for i in range(6):
            t = team_repo.create_task(TeamTaskData(team_id=team.id, title=f"Task {i}"))
            team_repo.assign_task(t.id, members[1].id)
        balance = team_repo.get_workload_balance(team.id)
        assert balance.get("balanced") is False

    def test_workload_empty_team(self, team_repo):
        """Workload balance on empty team."""
        from src.teams.repository import TeamData
        team = team_repo.create(TeamData(name="Empty"))
        balance = team_repo.get_workload_balance(team.id)
        assert balance.get("balanced") is True


# ══════════════════════════════════════════════════════════════════
# 5. Assignment Service (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestAssignmentService:
    """Verify assignment logic and auto-selection."""

    def test_assign_customer(self, team_with_members):
        """Assign a customer to an agent."""
        team_repo, team, members = team_with_members
        from src.teams.repository import AssignmentService
        svc = AssignmentService(team_repo.session, team_repo)
        from src.database.models import Customer
        c = Customer(name="Test Client")
        team_repo.session.add(c)
        team_repo.session.commit()
        result = svc.assign_customer(
            team_id=team.id,
            customer_id=str(c.id),
            agent_id=members[1].id,
            assigned_by=members[0].id,
        )
        assert result["assignment_id"]
        assert result["agent_id"] == members[1].id
        assert result["method"] == "manual"
        assert result["task_id"]

    def test_assign_customer_auto(self, team_with_members):
        """Auto-assign customer to least loaded agent."""
        team_repo, team, members = team_with_members
        from src.teams.repository import AssignmentService
        svc = AssignmentService(team_repo.session, team_repo)
        from src.database.models import Customer
        c = Customer(name="Auto Client")
        team_repo.session.add(c)
        team_repo.session.commit()
        result = svc.assign_customer(team_id=team.id, customer_id=str(c.id))
        assert result["assignment_id"]
        assert result["agent_id"]
        assert result["method"] == "auto"

    def test_assign_task_to_agent(self, team_with_members):
        """Assign an existing task to an agent."""
        team_repo, team, members = team_with_members
        from src.teams.repository import AssignmentService, TeamTaskData
        svc = AssignmentService(team_repo.session, team_repo)
        task = team_repo.create_task(TeamTaskData(team_id=team.id, title="Test"))
        result = svc.assign_task(
            task_id=task.id,
            team_id=team.id,
            agent_id=members[1].id,
        )
        assert result["task_id"] == task.id
        assert result["agent_id"] == members[1].id

    def test_complete_assignment(self, team_with_members):
        """Complete an assignment."""
        team_repo, team, members = team_with_members
        from src.teams.repository import AssignmentService
        svc = AssignmentService(team_repo.session, team_repo)
        from src.database.models import Customer, Assignment as AssignmentModel
        c = Customer(name="Test")
        team_repo.session.add(c)
        team_repo.session.commit()
        a = AssignmentModel(team_id=team.id, customer_id=str(c.id),
                            agent_id=members[1].id, status="active")
        team_repo.session.add(a)
        team_repo.session.commit()
        assert svc.complete_assignment(str(a.id)) is True

    def test_auto_select_lightest_agent(self, team_with_members):
        """Auto-select picks agent with fewest tasks."""
        team_repo, team, members = team_with_members
        from src.teams.repository import AssignmentService, TeamTaskData
        # Give member[1] (Bob) 5 tasks, member[2] (Charlie) 0
        for i in range(5):
            t = team_repo.create_task(TeamTaskData(team_id=team.id, title=f"T{i}"))
            team_repo.assign_task(t.id, members[1].id)
        from src.database.models import Customer
        c = Customer(name="New Client")
        team_repo.session.add(c)
        team_repo.session.commit()
        svc = AssignmentService(team_repo.session, team_repo)
        result = svc.assign_customer(team_id=team.id, customer_id=str(c.id))
        # Should pick someone with 0 active tasks (Alice or Charlie)
        assert result["agent_id"] is not None
        assert result["agent_id"] != members[1].id  # Not Bob (5 tasks)


# ══════════════════════════════════════════════════════════════════
# 6. Knowledge Sharing (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestKnowledgeSharing:
    """Verify knowledge entry CRUD and search."""

    def test_create_knowledge_entry(self, team_with_members, knowledge_repo):
        """Create a knowledge entry."""
        team_repo, team, members = team_with_members
        from src.teams.repository import KnowledgeEntryData
        entry = knowledge_repo.create(KnowledgeEntryData(
            team_id=team.id,
            title="How to handle lapsed policies",
            content="Call customer within 7 days...",
            tags=["lapse", "renewal"],
            visibility="team",
            created_by=members[0].id,
        ))
        assert entry.id
        assert "lapse" in entry.tags
        assert entry.visibility == "team"

    def test_search_knowledge(self, team_with_members, knowledge_repo):
        """Search knowledge entries by keyword."""
        team_repo, team, _ = team_with_members
        from src.teams.repository import KnowledgeEntryData
        knowledge_repo.create(KnowledgeEntryData(
            team_id=team.id,
            title="Medical claim process",
            content="Step by step guide for medical claims",
            tags=["medical", "claim"],
        ))
        knowledge_repo.create(KnowledgeEntryData(
            team_id=team.id,
            title="Motor insurance renewal",
            content="How to renew motor insurance online",
            tags=["motor", "renewal"],
        ))
        results = knowledge_repo.search(team.id, "motor")
        assert len(results) == 1
        assert "motor" in results[0].tags

    def test_search_all_entries(self, team_with_members, knowledge_repo):
        """Search with empty query returns all."""
        team_repo, team, _ = team_with_members
        from src.teams.repository import KnowledgeEntryData
        knowledge_repo.create(KnowledgeEntryData(team_id=team.id, title="A"))
        knowledge_repo.create(KnowledgeEntryData(team_id=team.id, title="B"))
        assert len(knowledge_repo.search(team.id)) == 2

    def test_update_knowledge(self, team_with_members, knowledge_repo):
        """Update a knowledge entry."""
        team_repo, team, _ = team_with_members
        from src.teams.repository import KnowledgeEntryData
        entry = knowledge_repo.create(KnowledgeEntryData(team_id=team.id, title="Original"))
        entry.title = "Updated"
        entry.content = "New content"
        updated = knowledge_repo.update(entry)
        assert updated.title == "Updated"
        assert updated.content == "New content"

    def test_delete_knowledge(self, team_with_members, knowledge_repo):
        """Delete a knowledge entry."""
        team_repo, team, _ = team_with_members
        from src.teams.repository import KnowledgeEntryData
        entry = knowledge_repo.create(KnowledgeEntryData(team_id=team.id, title="Delete me"))
        assert knowledge_repo.delete(entry.id) is True
        assert knowledge_repo.get_by_id(entry.id) is None


# ══════════════════════════════════════════════════════════════════
# 7. Team Dashboard (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestTeamDashboard:
    """Verify team metrics and dashboard."""

    def test_get_overview(self, team_with_members):
        """Get team overview with all metrics."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamDashboardService
        svc = TeamDashboardService(team_repo.session, team_repo)
        overview = svc.get_overview(team.id)
        assert overview["total_members"] == 3
        assert overview["agents"] == 2  # Alice is manager
        assert overview["managers"] == 1  # Alice
        assert overview["total_tasks"] == 0
        assert overview["renewal_rate"] == 0

    def test_overview_with_tasks(self, team_with_members):
        """Dashboard reflects task activity."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamDashboardService, TeamTaskData
        svc = TeamDashboardService(team_repo.session, team_repo)
        # Create and complete some tasks
        for i in range(3):
            t = team_repo.create_task(TeamTaskData(team_id=team.id, title=f"T{i}"))
            team_repo.update_task_status(t.id, "done")
        # Create pending task
        team_repo.create_task(TeamTaskData(team_id=team.id, title="Pending"))
        overview = svc.get_overview(team.id)
        assert overview["total_tasks"] == 4
        assert overview["completed_tasks"] == 3
        assert overview["pending_tasks"] == 1
        assert overview["renewal_rate"] == 75

    def test_top_performer(self, team_with_members):
        """Identify the top performing member."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamDashboardService, TeamTaskData
        svc = TeamDashboardService(team_repo.session, team_repo)
        for i in range(5):
            t = team_repo.create_task(TeamTaskData(team_id=team.id, title=f"T{i}"))
            team_repo.assign_task(t.id, members[1].id)
            team_repo.update_task_status(t.id, "done")
        for i in range(2):
            t = team_repo.create_task(TeamTaskData(team_id=team.id, title=f"X{i}"))
            team_repo.assign_task(t.id, members[2].id)
            team_repo.update_task_status(t.id, "done")
        overview = svc.get_overview(team.id)
        assert overview["top_performer"]["name"] == members[1].name

    def test_needs_support(self, team_with_members):
        """Identify member who needs support (most pending)."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamDashboardService, TeamTaskData
        svc = TeamDashboardService(team_repo.session, team_repo)
        # Give Charlie many pending tasks
        for i in range(7):
            t = team_repo.create_task(TeamTaskData(team_id=team.id, title=f"T{i}"))
            team_repo.assign_task(t.id, members[2].id)
        overview = svc.get_overview(team.id)
        assert overview["needs_support"]["name"] == members[2].name
        assert overview["needs_support"]["pending"] >= 7

    def test_agent_dashboard(self, team_with_members):
        """Get personalized agent daily view."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamDashboardService, TeamTaskData
        svc = TeamDashboardService(team_repo.session, team_repo)
        for p in ["high", "medium", "low"]:
            t = team_repo.create_task(TeamTaskData(
                team_id=team.id, title=f"{p} task",
                priority=p,
            ))
            team_repo.assign_task(t.id, members[1].id)
        dashboard = svc.get_agent_dashboard(members[1].id)
        assert dashboard["total_pending"] == 3
        assert dashboard["priorities"]["high"] == 1
        assert dashboard["priorities"]["medium"] == 1
        assert dashboard["priorities"]["low"] == 1


# ══════════════════════════════════════════════════════════════════
# 8. E2E Flow (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestE2EFlow:
    """End-to-end: event → workflow → task → assignment → completion → metric update."""

    def test_full_team_lifecycle(self, team_with_members):
        """Create team → add members → create tasks → assign → complete → verify metrics."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamDashboardService, TeamTaskData
        svc = TeamDashboardService(team_repo.session, team_repo)

        # Step 1: Create tasks
        tasks = []
        for i in range(4):
            t = team_repo.create_task(TeamTaskData(
                team_id=team.id,
                title=f"Renewal case #{i}",
                task_type="renewal",
                priority="high" if i < 2 else "medium",
            ))
            tasks.append(t)

        # Step 2: Assign to agents
        for i, t in enumerate(tasks):
            team_repo.assign_task(t.id, members[1 + (i % 2)].id)

        # Step 3: Complete some tasks
        for t in tasks[:3]:
            team_repo.update_task_status(t.id, "done")

        # Step 4: Check metrics updated
        overview = svc.get_overview(team.id)
        assert overview["total_tasks"] == 4
        assert overview["completed_tasks"] == 3
        assert overview["pending_tasks"] == 0
        assert overview["in_progress_tasks"] == 1
        assert overview["renewal_rate"] == 75

    def test_workload_balance_after_assignment(self, team_with_members):
        """Workload balance updates after assignments and completions."""
        team_repo, team, members = team_with_members
        from src.teams.repository import TeamTaskData

        # Assign 3 tasks to Bob, 1 to Charlie
        for i in range(3):
            t = team_repo.create_task(TeamTaskData(team_id=team.id, title=f"B{i}"))
            team_repo.assign_task(t.id, members[1].id)
        t = team_repo.create_task(TeamTaskData(team_id=team.id, title="C1"))
        team_repo.assign_task(t.id, members[2].id)

        # Complete Bob's tasks (he should now have 0 active)
        for t in team_repo.list_tasks_by_assignee(members[1].id):
            team_repo.update_task_status(t.id, "done")

        workloads = team_repo.get_workload(team.id)
        bob = [w for w in workloads if w["name"] == "Bob"][0]
        charlie = [w for w in workloads if w["name"] == "Charlie"][0]
        assert bob["active_tasks"] == 0
        assert charlie["active_tasks"] == 1

    def test_knowledge_search_permissions(self, team_with_members, knowledge_repo):
        """Knowledge entries respect visibility."""
        team_repo, team, _ = team_with_members
        from src.teams.repository import KnowledgeEntryData
        knowledge_repo.create(KnowledgeEntryData(
            team_id=team.id, title="Team only", visibility="team",
        ))
        knowledge_repo.create(KnowledgeEntryData(
            team_id=team.id, title="Public", visibility="public",
        ))
        results = knowledge_repo.search(team.id)
        assert len(results) == 2
        visibilities = {e.visibility for e in results}
        assert "team" in visibilities
        assert "public" in visibilities

    def test_assignment_creates_task(self, team_with_members):
        """Customer assignment auto-creates a task."""
        team_repo, team, members = team_with_members
        from src.teams.repository import AssignmentService
        svc = AssignmentService(team_repo.session, team_repo)
        from src.database.models import Customer
        c = Customer(name="New Client")
        team_repo.session.add(c)
        team_repo.session.commit()
        result = svc.assign_customer(team_id=team.id, customer_id=str(c.id))
        assert result["task_id"]
        tasks = team_repo.list_tasks(team.id)
        assert any(t.id == result["task_id"] for t in tasks)

    def test_multiple_teams_independent(self, team_repo):
        """Teams are isolated — members from one don't leak to another."""
        from src.teams.repository import TeamData, TeamMemberData
        t1 = team_repo.create(TeamData(name="Team A"))
        t2 = team_repo.create(TeamData(name="Team B"))
        team_repo.add_member(TeamMemberData(team_id=t1.id, name="Alice"))
        team_repo.add_member(TeamMemberData(team_id=t2.id, name="Bob"))
        assert len(team_repo.list_members(t1.id)) == 1
        assert len(team_repo.list_members(t2.id)) == 1
