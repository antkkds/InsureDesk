"""Debug auto-select."""
import sys
sys.path.insert(0, '/home/antkk/InsureDesk')

from src.database.db_manager import init_db, get_engine, get_session
from src.teams.repository import TeamRepository, TeamData, TeamMemberData, TeamTaskData

engine = get_engine(":memory:")
init_db(engine)
session = get_session(engine)
repo = TeamRepository(session)

team = repo.create(TeamData(name="Test"))

m1 = repo.add_member(TeamMemberData(team_id=team.id, name="Alice", role="manager"))
m2 = repo.add_member(TeamMemberData(team_id=team.id, name="Bob", role="agent"))
m3 = repo.add_member(TeamMemberData(team_id=team.id, name="Charlie", role="agent"))

print(f"Members: {[(m.name, m.role, m.id) for m in [m1, m2, m3]]}")
print(f"Team ID: {team.id}")

# Give Bob 5 tasks
for i in range(5):
    t = repo.create_task(TeamTaskData(team_id=team.id, title=f"T{i}"))
    repo.assign_task(t.id, m2.id)

# Check workloads
workloads = repo.get_workload(team.id)
for w in workloads:
    print(f"  {w['name']}: {w['active_tasks']} tasks")

# Check _select_best_agent directly
from src.database.models import TeamMember, TeamTask
members_q = session.query(TeamMember).filter(
    TeamMember.team_id == team.id,
    TeamMember.is_active == True,
    TeamMember.role.in_(["agent", "manager"]),
).all()
print(f"Active agents from query: {[(m.name, m.role) for m in members_q]}")

for agent in members_q:
    count = session.query(TeamTask).filter(
        TeamTask.assignee_id == agent.id,
        TeamTask.status.in_(["pending", "in_progress"]),
    ).count()
    print(f"  {agent.name}: {count} active tasks")

from src.teams.repository import AssignmentService
svc = AssignmentService(session, repo)
best = svc._select_best_agent(team.id)
print(f"Best agent ID: {best}, expected: {m3.id}")
