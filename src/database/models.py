"""InsureDesk — Database models (SQLAlchemy)."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Integer, Float, Boolean, JSON, ForeignKey, create_engine
)
from sqlalchemy.orm import DeclarativeBase, relationship
# GUID not available in sqlite dialect — use String for UUIDs


class Base(DeclarativeBase):
    pass


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


# ── Customer ─────────────────────────────────────────────────────

class Customer(Base):
    __tablename__ = "customers"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False, index=True)
    phone = Column(String(50), nullable=True)
    ic_number = Column(String(20), nullable=True, index=True)
    email = Column(String(200), nullable=True)
    language = Column(String(10), default="en")  # en/ms/zh
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    policies = relationship("Policy", back_populates="customer", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="customer", cascade="all, delete-orphan")


# ── Policy ───────────────────────────────────────────────────────

class Policy(Base):
    __tablename__ = "policies"

    id = Column(String(36), primary_key=True, default=_uuid)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    company = Column(String(100), nullable=False)          # Great Eastern, Allianz, etc.
    policy_number = Column(String(100), nullable=False, index=True)
    policy_type = Column(String(50), default="")           # life/general/medical
    status = Column(String(20), default="active")          # active/lapsed/claim/expired
    start_date = Column(String(20), nullable=True)
    end_date = Column(String(20), nullable=True)
    premium = Column(String(50), nullable=True)
    coverage_summary = Column(Text, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    customer = relationship("Customer", back_populates="policies")


# ── Document ─────────────────────────────────────────────────────

class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    doc_type = Column(String(50), default="other")         # policy/ic/photo/police_report/claim/other
    filename = Column(String(500), nullable=False)
    filepath = Column(String(1000), nullable=False)
    tags = Column(JSON, default=list)
    notes = Column(Text, default="")
    file_size = Column(Float, default=0)
    created_at = Column(DateTime, default=_now)

    customer = relationship("Customer", back_populates="documents")


# ── Company (Insurer) ────────────────────────────────────────────

class Company(Base):
    __tablename__ = "companies"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    short_name = Column(String(20), nullable=False, unique=True, index=True)  # GE, AIA, etc.
    portal_url = Column(String(500), nullable=True)
    adapter_name = Column(String(100), nullable=True)      # great_eastern, allianz, etc.
    is_active = Column(Boolean, default=True)
    last_sync = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)


# ── Policy Parse Record (UIP-AI parsed policy data) ──────────────

class PolicyParseRecord(Base):
    """Structured policy data returned by UIP-AI OCR + LLM parsing.

    InsureDesk sends raw PDFs to UIP-AI via Bridge. UIP-AI handles
    OCR + LLM extraction and returns structured JSON stored here.
    """
    __tablename__ = "policy_parse_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=True)
    company = Column(String(200), default="")
    policy_number = Column(String(200), default="")
    policy_type = Column(String(50), default="")

    # Policy details (from UIP-AI parse)
    status = Column(String(20), default="active")          # active/lapsed/claim/expired
    premium = Column(String(50), default="")
    start_date = Column(String(20), default="")
    end_date = Column(String(20), default="")

    # Coverage data (JSON arrays from UIP-AI)
    coverages_json = Column(Text, default="")               # JSON: [{name, amount, note}]
    exclusions_json = Column(Text, default="")              # JSON: [string, ...]
    summary = Column(Text, default="")
    raw_json = Column(Text, default="")                     # Full UIP-AI response

    # Version tracking (for policy change detection)
    version = Column(Integer, default=1)
    previous_version_id = Column(String(36), nullable=True)

    # Parse status
    parse_status = Column(String(20), default="pending")    # pending/processing/done/error
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    customer = relationship("Customer", backref="policy_parse_records")
    document = relationship("Document", backref="policy_parse_records")


# ── Team (PI-16: Agency Collaboration) ─────────────────────────────

class Team(Base):
    """A team of insurance agents/managers."""
    __tablename__ = "teams"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    tasks = relationship("TeamTask", back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    """Member of a team (agent, manager, admin)."""
    __tablename__ = "team_members"

    id = Column(String(36), primary_key=True, default=_uuid)
    team_id = Column(String(36), ForeignKey("teams.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    role = Column(String(20), default="agent")          # agent / manager / admin
    email = Column(String(200), nullable=True)
    phone = Column(String(50), nullable=True)
    specialties = Column(JSON, default=list)             # ["life", "medical", "motor", "travel"]
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    team = relationship("Team", back_populates="members")
    assigned_tasks = relationship("TeamTask", back_populates="assignee",
                                  foreign_keys="TeamTask.assignee_id")
    assignments = relationship("Assignment", back_populates="agent",
                               foreign_keys="Assignment.agent_id")


class TeamTask(Base):
    """Tasks within a team (renewals, follow-ups, claims)."""
    __tablename__ = "team_tasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    team_id = Column(String(36), ForeignKey("teams.id"), nullable=False, index=True)
    assignee_id = Column(String(36), ForeignKey("team_members.id"), nullable=True, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    task_type = Column(String(50), default="general")    # renewal / followup / claim / general
    title = Column(String(300), nullable=False)
    description = Column(Text, default="")
    priority = Column(String(10), default="medium")      # high / medium / low
    status = Column(String(20), default="pending")       # pending / in_progress / done / cancelled
    due_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    team = relationship("Team", back_populates="tasks")
    assignee = relationship("TeamMember", back_populates="assigned_tasks",
                            foreign_keys=[assignee_id])
    customer = relationship("Customer", backref="team_tasks")


class KnowledgeEntry(Base):
    """Internal knowledge sharing for teams."""
    __tablename__ = "knowledge_entries"

    id = Column(String(36), primary_key=True, default=_uuid)
    team_id = Column(String(36), ForeignKey("teams.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    content = Column(Text, default="")
    tags = Column(JSON, default=list)
    visibility = Column(String(20), default="team")      # team / public
    created_by = Column(String(36), ForeignKey("team_members.id"), nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    team = relationship("Team", backref="knowledge_entries")
    creator = relationship("TeamMember", backref="knowledge_entries")


class Assignment(Base):
    """Customer/task assignment tracking with workload awareness."""
    __tablename__ = "assignments"

    id = Column(String(36), primary_key=True, default=_uuid)
    team_id = Column(String(36), ForeignKey("teams.id"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    agent_id = Column(String(36), ForeignKey("team_members.id"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("team_tasks.id"), nullable=True)
    assigned_by = Column(String(36), ForeignKey("team_members.id"), nullable=True)
    assigned_at = Column(DateTime, default=_now)
    status = Column(String(20), default="active")         # active / completed / reassigned
    note = Column(Text, default="")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    agent = relationship("TeamMember", back_populates="assignments",
                         foreign_keys=[agent_id])
    assignor = relationship("TeamMember", backref="assignments_made",
                            foreign_keys=[assigned_by])
    customer = relationship("Customer", backref="assignments")
    task = relationship("TeamTask", backref="assignments")


# ── PI-17: Enterprise Integrations ───────────────────────────────

class ExternalConnection(Base):
    """Connection to an external system (CRM, Calendar, Accounting)."""
    __tablename__ = "external_connections"

    id = Column(String(36), primary_key=True, default=_uuid)
    provider = Column(String(100), nullable=False, index=True)  # csv / google_sheets / google_calendar / airtable
    connection_type = Column(String(50), nullable=False)        # crm / calendar / accounting
    name = Column(String(200), default="")
    credentials_ref = Column(String(500), default="")           # Path or encrypted ref
    config = Column(JSON, default=dict)                         # Provider-specific settings
    status = Column(String(20), default="disconnected")         # disconnected / connected / error
    last_sync = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class FieldMapping(Base):
    """Field mapping between external system and InsureDesk fields."""
    __tablename__ = "field_mappings"

    id = Column(String(36), primary_key=True, default=_uuid)
    connection_id = Column(String(36), ForeignKey("external_connections.id"), nullable=False, index=True)
    source_field = Column(String(200), nullable=False)          # External field name
    target_field = Column(String(200), nullable=False)          # InsureDesk field name
    transform_rule = Column(String(500), default="")            # Optional transform (e.g. "lowercase", "date_parse")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)

    connection = relationship("ExternalConnection", backref="field_mappings")


class SyncLog(Base):
    """Sync history for external connections."""
    __tablename__ = "sync_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    connection_id = Column(String(36), ForeignKey("external_connections.id"), nullable=False, index=True)
    direction = Column(String(10), default="import")           # import / export
    status = Column(String(20), default="running")             # running / success / error
    records_processed = Column(Integer, default=0)
    records_succeeded = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    error_message = Column(Text, default="")
    started_at = Column(DateTime, default=_now)
    completed_at = Column(DateTime, nullable=True)

    connection = relationship("ExternalConnection", backref="sync_logs")


class CalendarEvent(Base):
    """Calendar events synced from/to external calendars."""
    __tablename__ = "calendar_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    connection_id = Column(String(36), ForeignKey("external_connections.id"), nullable=True, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("team_tasks.id"), nullable=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, default="")
    event_type = Column(String(50), default="appointment")     # appointment / review / followup / renewal
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    location = Column(String(300), default="")
    external_id = Column(String(300), nullable=True)           # ID from Google Calendar etc.
    status = Column(String(20), default="scheduled")           # scheduled / completed / cancelled
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    connection = relationship("ExternalConnection", backref="calendar_events")
    customer = relationship("Customer", backref="calendar_events")
    task = relationship("TeamTask", backref="calendar_events")


# ── PI-18: Family & Predictive Intelligence ─────────────────────

class FamilyMember(Base):
    """Family member linked to a customer (spouse, child, parent, sibling)."""
    __tablename__ = "family_members"

    id = Column(String(36), primary_key=True, default=_uuid)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    relation = Column(String(20), nullable=False)        # spouse / child / parent / sibling / other
    full_name = Column(String(200), nullable=False)
    date_of_birth = Column(String(20), nullable=True)
    gender = Column(String(10), default="")
    occupation = Column(String(200), default="")
    is_dependent = Column(Boolean, default=False)
    is_disabled = Column(Boolean, default=False)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    customer = relationship("Customer", backref="family_members")


class Household(Base):
    """A household grouping multiple customers together."""
    __tablename__ = "households"

    id = Column(String(36), primary_key=True, default=_uuid)
    primary_customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    name = Column(String(200), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    primary_customer = relationship("Customer", backref="primary_household",
                                    foreign_keys=[primary_customer_id])


class HouseholdMember(Base):
    """Many-to-many: customers in a household."""
    __tablename__ = "household_members"

    id = Column(String(36), primary_key=True, default=_uuid)
    household_id = Column(String(36), ForeignKey("households.id"), nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    role = Column(String(20), default="member")              # primary / member
    created_at = Column(DateTime, default=_now)

    household = relationship("Household", backref="members")
    customer = relationship("Customer", backref="households")


class LifeEvent(Base):
    """Important life milestones for prediction triggers."""
    __tablename__ = "life_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    member_id = Column(String(36), ForeignKey("family_members.id"), nullable=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # child_university / child_turns_18 / retirement / marriage / newborn / parent_senior
    event_date = Column(String(20), nullable=True)               # When the event occurs/happened
    reminder_offset_days = Column(Integer, default=0)            # Days before to remind
    notes = Column(Text, default="")
    is_acknowledged = Column(Boolean, default=False)             # Has the advisor addressed this
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    customer = relationship("Customer", backref="life_events")
    member = relationship("FamilyMember", backref="life_events")


# ── PI-19: Knowledge & Reasoning Intelligence ──────────────────

class KnowledgeSource(Base):
    """Unified catalog of all knowledge sources across the agency."""
    __tablename__ = "knowledge_sources"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_type = Column(String(50), nullable=False, index=True)  # policy_document / claim_guide / company_circular / sop / faq / case_note / training / market_notice
    title = Column(String(300), nullable=False)
    content = Column(Text, default="")
    tags = Column(JSON, default=list)
    language = Column(String(10), default="en")                   # en / ms / zh
    source_url = Column(String(500), default="")
    source_ref = Column(String(100), default="")                  # External reference number
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class CaseRecord(Base):
    """Insurance case records — experience, outcomes, lessons."""
    __tablename__ = "case_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    category = Column(String(50), nullable=False, index=True)     # claim_rejected / underwriting_exception / successful_appeal / renewal_negotiation / complaint
    title = Column(String(300), nullable=False)
    summary = Column(Text, default="")
    outcome = Column(String(500), default="")
    lessons = Column(Text, default="")
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    related_documents = Column(JSON, default=list)                 # List of document IDs or URLs
    tags = Column(JSON, default=list)
    is_published = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    customer = relationship("Customer", backref="case_records")


class ReasoningLog(Base):
    """Log of reasoning queries for audit and improvement."""
    __tablename__ = "reasoning_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    query = Column(Text, nullable=False)
    answer = Column(Text, default="")
    evidence = Column(JSON, default=list)                          # [{source_id, source_type, title, excerpt, confidence}]
    confidence = Column(String(10), default="medium")              # high / medium / low
    processing_time_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)


# ── PI-20: Autonomous Operations ───────────────────────────────

class OperationalGoal(Base):
    """Persistent operational goals for the autonomous engine."""
    __tablename__ = "operational_goals"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    metric_name = Column(String(100), nullable=False, index=True)  # renewal_rate / overdue_tasks / response_time / critical_customers
    current_value = Column(Float, default=0.0)
    target_value = Column(Float, default=100.0)
    unit = Column(String(20), default="%")
    status = Column(String(20), default="on_track")               # on_track / needs_attention / critical
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class OpportunityAction(Base):
    """Proactively scheduled actions from the opportunity engine."""
    __tablename__ = "opportunity_actions"

    id = Column(String(36), primary_key=True, default=_uuid)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    category = Column(String(50), nullable=False, index=True)      # renewal_risk / coverage_gap / family_event / market_alert
    priority = Column(String(10), default="medium")                # critical / high / medium / low
    title = Column(String(300), nullable=False)
    description = Column(Text, default="")
    recommended_action = Column(String(500), default="")
    status = Column(String(20), default="pending")                 # pending / approved / completed / dismissed
    requires_approval = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    customer = relationship("Customer", backref="opportunity_actions")


class RecommendationOutcome(Base):
    """Track whether recommendations led to desired outcomes."""
    __tablename__ = "recommendation_outcomes"

    id = Column(String(36), primary_key=True, default=_uuid)
    action_id = Column(String(36), ForeignKey("opportunity_actions.id"), nullable=True, index=True)
    customer_id = Column(String(36), ForeignKey("customers.id"), nullable=True, index=True)
    recommendation_type = Column(String(50), nullable=False)
    was_accepted = Column(Boolean, default=False)
    was_successful = Column(Boolean, default=False)
    outcome_notes = Column(Text, default="")
    recorded_at = Column(DateTime, default=_now)

    action = relationship("OpportunityAction", backref="outcomes")
    customer = relationship("Customer", backref="recommendation_outcomes")


# ── Settings ─────────────────────────────────────────────────────

class PortalCredential(Base):
    """Encrypted portal login credentials.

    Username and password are AES-256-GCM encrypted before storage.
    Master key lives in OS Secret Store (keyring), NOT in the database.
    """
    __tablename__ = "portal_credentials"

    id = Column(String(36), primary_key=True, default=_uuid)
    portal = Column(String(100), nullable=False, index=True)          # great_eastern, allianz, aia
    account_name = Column(String(200), default="default")              # "Anthony HQ", "Personal", etc.
    encrypted_username = Column(String(1000), nullable=False)
    encrypted_password = Column(String(1000), nullable=False)
    is_default = Column(Boolean, default=False)
    enabled = Column(Boolean, default=True)
    last_verified = Column(DateTime, nullable=True)
    last_used = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=_now, onupdate=_now)
