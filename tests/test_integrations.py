"""Tests: PI-17 Enterprise Integration Intelligence.

Scope: ~35 tests covering:
- Connector Registry (register, list, get)
- CSV Connector (connect, import, export, field mappings)
- Google Sheets Connector (config, placeholders)
- Google Calendar Connector (config, event creation)
- IntegrationRepository (connections, mappings, sync logs)
- IntegrationService (connect, sync import/export)
- CalendarEventRepository (create, list, update)
- E2E: Connect → Map fields → Import → Export → Sync log
"""

from __future__ import annotations

import os
import tempfile
import pytest


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def session():
    """Get an in-memory SQLAlchemy session."""
    from src.database.db_manager import init_db, get_engine, get_session
    engine = get_engine(":memory:")
    init_db(engine)
    return get_session(engine)


@pytest.fixture
def repo(session):
    from src.integrations.connectors import IntegrationRepository
    return IntegrationRepository(session)


@pytest.fixture
def service(repo):
    from src.integrations.connectors import IntegrationService
    return IntegrationService(repo.session, repo)


@pytest.fixture
def csv_connection(repo):
    """Create a CSV connection in the database."""
    from src.integrations.connectors import ExternalConnectionData
    return repo.create_connection(ExternalConnectionData(
        provider="csv", connection_type="crm",
        name="Test CSV", credentials_ref="/tmp/test_import.csv",
    ))


@pytest.fixture
def temp_csv():
    """Create a temporary CSV file with test data."""
    import csv
    path = "/tmp/test_import.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Name", "Phone", "Email", "IC"])
        w.writeheader()
        w.writerow({"Name": "Alice Tan", "Phone": "0123456789",
                     "Email": "alice@test.com", "IC": "900101-01-1234"})
        w.writerow({"Name": "Bob Lee", "Phone": "0198765432",
                     "Email": "bob@test.com", "IC": "850505-10-5678"})
    yield path
    if os.path.exists(path):
        os.remove(path)


# ══════════════════════════════════════════════════════════════════
# 1. Connector Registry (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestConnectorRegistry:
    """Verify ConnectorRegistry registration and discovery."""

    def test_registered_connectors(self):
        """All PI-17 connectors are registered."""
        from src.integrations.connectors import ConnectorRegistry
        available = ConnectorRegistry.list_available()
        names = [c["name"] for c in available]
        assert "csv" in names
        assert "google_sheets" in names
        assert "google_calendar" in names

    def test_get_connector(self):
        """Get a connector class by name."""
        from src.integrations.connectors import ConnectorRegistry, CSVConnector
        cls = ConnectorRegistry.get("csv")
        assert cls is CSVConnector

    def test_get_unknown_connector(self):
        """Unknown connector returns None."""
        from src.integrations.connectors import ConnectorRegistry
        assert ConnectorRegistry.get("nonexistent") is None

    def test_connector_metadata(self):
        """Each connector has proper metadata."""
        from src.integrations.connectors import ConnectorRegistry
        available = ConnectorRegistry.list_available()
        for c in available:
            assert c["name"]
            assert c["display_name"]
            assert c["type"] in ("crm", "calendar", "accounting")
            assert c["description"]


# ══════════════════════════════════════════════════════════════════
# 2. CSV Connector (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestCSVConnector:
    """Verify CSV import/export functionality."""

    def test_connect(self):
        """CSV connector connects successfully."""
        from src.integrations.connectors import ExternalConnectionData, CSVConnector
        conn = ExternalConnectionData(provider="csv", credentials_ref="/tmp/test.csv")
        csv = CSVConnector(conn)
        assert csv.connect() is True

    def test_test_connection_file_exists(self, temp_csv):
        """Test connection reports file exists."""
        from src.integrations.connectors import ExternalConnectionData, CSVConnector
        conn = ExternalConnectionData(provider="csv", credentials_ref=temp_csv)
        csv = CSVConnector(conn)
        result = csv.test_connection()
        assert result["ok"] is True

    def test_test_connection_file_missing(self):
        """Test connection reports file missing."""
        from src.integrations.connectors import ExternalConnectionData, CSVConnector
        conn = ExternalConnectionData(provider="csv", credentials_ref="/tmp/nonexistent.csv")
        csv = CSVConnector(conn)
        result = csv.test_connection()
        assert result["ok"] is False

    def test_csv_import(self, session, temp_csv):
        """Import CSV data with customer creation."""
        from src.integrations.connectors import ExternalConnectionData, CSVConnector
        conn = ExternalConnectionData(provider="csv", credentials_ref=temp_csv)
        csv = CSVConnector(conn, session)
        result = csv.import_data()
        assert result.success is True
        assert result.records_processed == 2
        assert result.records_succeeded == 2

    def test_csv_export(self):
        """Export CSV data."""
        from src.integrations.connectors import ExternalConnectionData, CSVConnector
        conn = ExternalConnectionData(provider="csv", credentials_ref="/tmp/test_export.csv")
        csv = CSVConnector(conn)
        data = [{"name": "Alice", "phone": "012345"}, {"name": "Bob", "phone": "987654"}]
        result = csv.export_data(data)
        assert result.success is True
        assert result.records_exported == 2
        # Cleanup
        if os.path.exists("/tmp/test_export.csv"):
            os.remove("/tmp/test_export.csv")


# ══════════════════════════════════════════════════════════════════
# 3. Google Sheets Connector (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestSheetsConnector:
    """Verify Google Sheets connector config and stubs."""

    def test_connect_with_sheet_id(self):
        """Connect succeeds when sheet_id is configured."""
        from src.integrations.connectors import ExternalConnectionData, GoogleSheetsConnector
        conn = ExternalConnectionData(provider="google_sheets", config={"sheet_id": "abc123"})
        sheets = GoogleSheetsConnector(conn)
        assert sheets.connect() is True

    def test_connect_without_sheet_id(self):
        """Connect fails without sheet_id."""
        from src.integrations.connectors import ExternalConnectionData, GoogleSheetsConnector
        conn = ExternalConnectionData(provider="google_sheets")
        sheets = GoogleSheetsConnector(conn)
        assert sheets.connect() is False

    def test_supported_mappings(self):
        """Returns expected field mappings."""
        from src.integrations.connectors import ExternalConnectionData, GoogleSheetsConnector
        conn = ExternalConnectionData(provider="google_sheets")
        sheets = GoogleSheetsConnector(conn)
        mappings = sheets.get_supported_mappings()
        assert len(mappings) >= 4
        assert any(m["target"] == "name" for m in mappings)


# ══════════════════════════════════════════════════════════════════
# 4. Google Calendar Connector (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestCalendarConnector:
    """Verify Google Calendar connector."""

    def test_connect(self):
        """Calendar connector connects."""
        from src.integrations.connectors import ExternalConnectionData, GoogleCalendarConnector
        conn = ExternalConnectionData(provider="google_calendar", config={"calendar_id": "primary"})
        cal = GoogleCalendarConnector(conn)
        assert cal.connect() is True

    def test_import_stub(self):
        """Import returns a descriptive message (OAuth needed)."""
        from src.integrations.connectors import ExternalConnectionData, GoogleCalendarConnector
        conn = ExternalConnectionData(provider="google_calendar")
        cal = GoogleCalendarConnector(conn)
        result = cal.import_data()
        assert result.success is True  # Stub returns success

    def test_supported_mappings(self):
        """Returns expected calendar field mappings."""
        from src.integrations.connectors import ExternalConnectionData, GoogleCalendarConnector
        conn = ExternalConnectionData(provider="google_calendar")
        cal = GoogleCalendarConnector(conn)
        mappings = cal.get_supported_mappings()
        assert any(m["target"] == "title" for m in mappings)
        assert any(m["target"] == "start_time" for m in mappings)


# ══════════════════════════════════════════════════════════════════
# 5. Integration Repository (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestIntegrationRepository:
    """Verify CRUD for connections, mappings, and sync logs."""

    def test_create_connection(self, repo):
        """Create an external connection."""
        from src.integrations.connectors import ExternalConnectionData
        c = repo.create_connection(ExternalConnectionData(
            provider="csv", connection_type="crm", name="My CSV"
        ))
        assert c.id
        assert c.provider == "csv"
        assert c.status == "disconnected"

    def test_list_connections(self, repo):
        """List connections, optionally filtered by type."""
        from src.integrations.connectors import ExternalConnectionData
        repo.create_connection(ExternalConnectionData(provider="csv", connection_type="crm"))
        repo.create_connection(ExternalConnectionData(provider="google_calendar", connection_type="calendar"))
        assert len(repo.list_connections()) == 2
        assert len(repo.list_connections("crm")) == 1
        assert len(repo.list_connections("calendar")) == 1

    def test_update_connection(self, repo):
        """Update connection status and config."""
        from src.integrations.connectors import ExternalConnectionData
        c = repo.create_connection(ExternalConnectionData(provider="csv", connection_type="crm"))
        c.status = "connected"
        updated = repo.update_connection(c)
        assert updated.status == "connected"

    def test_delete_connection(self, repo):
        """Soft-delete a connection."""
        from src.integrations.connectors import ExternalConnectionData
        c = repo.create_connection(ExternalConnectionData(provider="csv", connection_type="crm"))
        assert repo.delete_connection(c.id) is True
        deleted = repo.get_connection(c.id)
        assert deleted.is_active is False

    def test_create_sync_log(self, repo, csv_connection):
        """Create and complete a sync log."""
        from src.integrations.connectors import SyncLogData
        log = repo.create_sync_log(SyncLogData(
            connection_id=csv_connection.id, direction="import"
        ))
        assert log.status == "running"
        completed = repo.complete_sync_log(log.id, "success", processed=10, succeeded=10)
        assert completed.status == "success"


# ══════════════════════════════════════════════════════════════════
# 6. Field Mappings (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestFieldMappings:
    """Verify field mapping CRUD."""

    def test_create_mapping(self, repo, csv_connection):
        """Create a field mapping."""
        from src.integrations.connectors import FieldMappingData
        m = repo.create_mapping(FieldMappingData(
            connection_id=csv_connection.id,
            source_field="Name", target_field="name",
        ))
        assert m.id
        assert m.source_field == "Name"
        assert m.target_field == "name"

    def test_list_mappings(self, repo, csv_connection):
        """List mappings for a connection."""
        from src.integrations.connectors import FieldMappingData
        repo.create_mapping(FieldMappingData(connection_id=csv_connection.id,
                                              source_field="A", target_field="a"))
        repo.create_mapping(FieldMappingData(connection_id=csv_connection.id,
                                              source_field="B", target_field="b"))
        mappings = repo.list_mappings(csv_connection.id)
        assert len(mappings) == 2

    def test_delete_mapping(self, repo, csv_connection):
        """Soft-delete a field mapping."""
        from src.integrations.connectors import FieldMappingData
        m = repo.create_mapping(FieldMappingData(connection_id=csv_connection.id,
                                                  source_field="X", target_field="x"))
        assert repo.delete_mapping(m.id) is True

    def test_csv_import_with_mappings(self, session, repo, temp_csv, csv_connection):
        """Import CSV with custom field mappings."""
        from src.integrations.connectors import FieldMappingData, CSVConnector, ExternalConnectionData
        # Create mapping: Name -> name
        repo.create_mapping(FieldMappingData(
            connection_id=csv_connection.id,
            source_field="Name", target_field="name",
        ))
        conn_data = ExternalConnectionData(provider="csv", credentials_ref=temp_csv)
        csv = CSVConnector(conn_data, session)
        mappings = [FieldMappingData(source_field="Name", target_field="name", is_active=True)]
        result = csv.import_data(mappings)
        assert result.success is True
        assert result.records_succeeded >= 1


# ══════════════════════════════════════════════════════════════════
# 7. Integration Service (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestIntegrationService:
    """Verify high-level service orchestration."""

    def test_connect_provider(self, service):
        """Connect to a provider creates a connection entry."""
        conn = service.connect_provider("csv", name="Test CSV")
        assert conn.id
        assert conn.provider == "csv"

    def test_connect_unknown_provider(self, service):
        """Unknown provider raises ValueError."""
        import pytest
        with pytest.raises(ValueError):
            service.connect_provider("nonexistent")

    def test_sync_import_csv(self, service, repo, temp_csv):
        """Sync import using CSV connector."""
        conn = service.connect_provider("csv", name="CSV Test",
                                        credentials_ref=temp_csv)
        result = service.sync_import(conn.id)
        assert result.success is True
        # Check sync log was created
        logs = repo.list_sync_logs(conn.id)
        assert len(logs) >= 1

    def test_get_dashboard(self, service):
        """Dashboard returns overview of connections."""
        service.connect_provider("csv", name="CSV")
        service.connect_provider("google_calendar", name="Calendar")
        dashboard = service.get_dashboard()
        assert dashboard["total_connections"] == 2
        assert dashboard["connected_count"] >= 0


# ══════════════════════════════════════════════════════════════════
# 8. Calendar Event Repository (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestCalendarEventRepo:
    """Verify calendar event CRUD."""

    def test_create_event(self, session):
        from src.integrations.connectors import CalendarEventRepository, CalendarEventData
        repo = CalendarEventRepository(session)
        event = repo.create_event(CalendarEventData(
            title="Policy Review", event_type="review",
            start_time="2026-08-01T10:00:00",
            end_time="2026-08-01T11:00:00",
        ))
        assert event.id
        assert event.title == "Policy Review"
        assert event.status == "scheduled"

    def test_list_events(self, session):
        from src.integrations.connectors import CalendarEventRepository, CalendarEventData
        repo = CalendarEventRepository(session)
        repo.create_event(CalendarEventData(title="Event 1"))
        repo.create_event(CalendarEventData(title="Event 2"))
        assert len(repo.list_events()) == 2

    def test_list_events_by_status(self, session):
        from src.integrations.connectors import CalendarEventRepository, CalendarEventData
        repo = CalendarEventRepository(session)
        repo.create_event(CalendarEventData(title="Scheduled", status="scheduled"))
        repo.create_event(CalendarEventData(title="Done", status="completed"))
        scheduled = repo.list_events(status="scheduled")
        assert len(scheduled) == 1
        assert scheduled[0].title == "Scheduled"

    def test_update_event(self, session):
        from src.integrations.connectors import CalendarEventRepository, CalendarEventData
        repo = CalendarEventRepository(session)
        event = repo.create_event(CalendarEventData(title="Initial"))
        event.title = "Updated"
        event.status = "completed"
        updated = repo.update_event(event)
        assert updated.title == "Updated"
        assert updated.status == "completed"
        assert updated.updated_at


# ══════════════════════════════════════════════════════════════════
# 9. E2E Flow (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestE2EIntegration:
    """End-to-end: Connect → Map → Import → Export → Verify logs."""

    def test_full_csv_integration_flow(self, service, repo, session, temp_csv):
        """Full cycle: connect CSV → map fields → import → check logs."""
        # Step 1: Connect
        conn = service.connect_provider("csv", name="E2E CSV",
                                        credentials_ref=temp_csv)
        assert conn.status == "connected"

        # Step 2: Create field mappings
        from src.integrations.connectors import FieldMappingData
        repo.create_mapping(FieldMappingData(
            connection_id=conn.id,
            source_field="Name", target_field="name",
        ))
        repo.create_mapping(FieldMappingData(
            connection_id=conn.id,
            source_field="Phone", target_field="phone",
        ))

        # Step 3: Import
        result = service.sync_import(conn.id)
        assert result.success is True
        assert result.records_processed == 2

        # Step 4: Check sync log
        logs = repo.list_sync_logs(conn.id)
        assert len(logs) >= 1
        assert logs[0].status == "success"

    def test_calendar_event_lifecycle(self, session):
        """Create → list → update → complete a calendar event."""
        from src.integrations.connectors import CalendarEventRepository, CalendarEventData
        repo = CalendarEventRepository(session)

        # Create
        event = repo.create_event(CalendarEventData(
            title="John Policy Review",
            event_type="review",
            start_time="2026-08-15T14:00:00",
            end_time="2026-08-15T15:00:00",
            location="Office",
        ))
        assert event.id

        # List
        events = repo.list_events()
        assert len(events) == 1

        # Update
        event.status = "completed"
        updated = repo.update_event(event)
        assert updated.status == "completed"

    def test_multiple_connections_independent(self, repo):
        """Multiple connections are isolated."""
        from src.integrations.connectors import ExternalConnectionData
        repo.create_connection(ExternalConnectionData(
            provider="csv", connection_type="crm", name="CSV 1"
        ))
        repo.create_connection(ExternalConnectionData(
            provider="csv", connection_type="crm", name="CSV 2"
        ))
        all_conns = repo.list_connections()
        assert len(all_conns) == 2
        assert all_conns[0].name != all_conns[1].name
