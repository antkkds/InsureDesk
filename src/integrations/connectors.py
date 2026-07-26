"""InsureDesk — Universal Connector Framework (PI-17, Module D).

Provides:
- BaseConnector ABC (all connectors inherit)
- ConnectorRegistry (discover available connectors)
- CSVConnector (import/export customer data)
- GoogleSheetsConnector (basic sheet integration)
- GoogleCalendarConnector (sync tasks to calendar)
- IntegrationService (manage connections, sync, field mappings)
"""

import csv
import io
import json
import uuid
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


# ── Domain Models ────────────────────────────────────────────────

@dataclass
class ExternalConnectionData:
    id: str = ""
    provider: str = ""
    connection_type: str = ""     # crm / calendar / accounting
    name: str = ""
    credentials_ref: str = ""
    config: dict = field(default_factory=dict)
    status: str = "disconnected"  # disconnected / connected / error
    last_sync: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class FieldMappingData:
    id: str = ""
    connection_id: str = ""
    source_field: str = ""
    target_field: str = ""
    transform_rule: str = ""
    is_active: bool = True
    created_at: str = ""


@dataclass
class SyncLogData:
    id: str = ""
    connection_id: str = ""
    direction: str = "import"     # import / export
    status: str = "running"       # running / success / error
    records_processed: int = 0
    records_succeeded: int = 0
    records_failed: int = 0
    error_message: str = ""
    started_at: str = ""
    completed_at: str = ""


@dataclass
class CalendarEventData:
    id: str = ""
    connection_id: str = ""
    customer_id: str = ""
    task_id: str = ""
    title: str = ""
    description: str = ""
    event_type: str = "appointment"  # appointment / review / followup / renewal
    start_time: str = ""
    end_time: str = ""
    location: str = ""
    external_id: str = ""
    status: str = "scheduled"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool = False
    records_imported: int = 0
    records_exported: int = 0
    records_failed: int = 0
    errors: list = field(default_factory=list)
    message: str = ""


# ── Connector Registry ──────────────────────────────────────────

class ConnectorRegistry:
    """Registry of available connector implementations."""

    _connectors: dict = {}

    @classmethod
    def register(cls, name: str, connector_cls):
        """Register a connector class by name."""
        cls._connectors[name] = connector_cls

    @classmethod
    def get(cls, name: str) -> Optional[type]:
        """Get a connector class by name."""
        return cls._connectors.get(name)

    @classmethod
    def list_available(cls) -> List[Dict]:
        """List all registered connectors with metadata."""
        return [
            {
                "name": name,
                "display_name": conn_cls.display_name,
                "type": conn_cls.connector_type,
                "description": conn_cls.description,
            }
            for name, conn_cls in cls._connectors.items()
        ]


# ── Base Connector ──────────────────────────────────────────────

class BaseConnector(ABC):
    """Abstract base class for all integration connectors.

    Each connector knows how to:
    - Connect/authenticate to external system
    - Import data into InsureDesk
    - Export data from InsureDesk
    - Test connection health
    """

    display_name: str = ""
    connector_type: str = ""     # crm / calendar / accounting
    description: str = ""

    def __init__(self, connection: ExternalConnectionData, session=None):
        self.connection = connection
        self.session = session
        self._connected = False

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the external system."""
        ...

    @abstractmethod
    def disconnect(self):
        """Disconnect from the external system."""
        ...

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Test if the connection is working. Returns {'ok': bool, 'message': str}."""
        ...

    @abstractmethod
    def import_data(self, mappings: List[FieldMappingData] = None) -> SyncResult:
        """Import data from external system into InsureDesk."""
        ...

    @abstractmethod
    def export_data(self, data: List[Dict], mappings: List[FieldMappingData] = None) -> SyncResult:
        """Export data from InsureDesk to external system."""
        ...

    def get_supported_mappings(self) -> List[Dict]:
        """Return default field mappings for this connector."""
        return []


# ── CSV Connector ───────────────────────────────────────────────

class CSVConnector(BaseConnector):
    """Import/export customer data via CSV files."""

    display_name = "CSV Import/Export"
    connector_type = "crm"
    description = "Import customers from CSV or export to CSV"

    def __init__(self, connection: ExternalConnectionData, session=None):
        super().__init__(connection, session)
        self._csv_path = connection.credentials_ref or ""

    def connect(self) -> bool:
        path = self.connection.credentials_ref
        if path and os.path.exists(path):
            self._connected = True
            return True
        # CSV doesn't need auth, just file path
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False

    def test_connection(self) -> Dict[str, Any]:
        path = self.connection.credentials_ref
        if not path:
            return {"ok": False, "message": "No file path configured."}
        if os.path.exists(path):
            return {"ok": True, "message": f"File exists: {Path(path).name}"}
        return {"ok": False, "message": f"File not found: {path}"}

    def import_data(self, mappings: List[FieldMappingData] = None) -> SyncResult:
        result = SyncResult()
        path = self.connection.credentials_ref
        if not path or not os.path.exists(path):
            result.message = f"File not found: {path}"
            return result

        try:
            with open(path, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                result.success = True
                result.message = "CSV file is empty."
                return result

            result.records_processed = len(rows)
            # Apply mappings if provided
            if mappings:
                rows = self._apply_mappings(rows, mappings)

            # If session available, import to database
            imported = 0
            if self.session and rows:
                from src.database.models import Customer
                for row in rows:
                    try:
                        customer = Customer(
                            name=row.get("name", row.get("Name", "Unknown")),
                            phone=row.get("phone", row.get("Phone", "")),
                            email=row.get("email", row.get("Email", "")),
                            ic_number=row.get("ic_number", row.get("IC", "")),
                        )
                        self.session.add(customer)
                        imported += 1
                    except Exception as e:
                        result.records_failed += 1
                        result.errors.append(str(e))
                self.session.commit()

            result.records_succeeded = imported
            result.success = True
            result.message = f"Imported {imported}/{len(rows)} records from CSV."

        except Exception as e:
            result.success = False
            result.message = str(e)
            result.errors.append(str(e))

        return result

    def export_data(self, data: List[Dict], mappings: List[FieldMappingData] = None) -> SyncResult:
        result = SyncResult()
        path = self.connection.credentials_ref or "customers_export.csv"

        try:
            if not data:
                result.success = True
                result.message = "No data to export."
                return result

            # Apply reverse mappings if provided
            if mappings:
                data = self._apply_reverse_mappings(data, mappings)

            fieldnames = set()
            for row in data:
                fieldnames.update(row.keys())
            fieldnames = sorted(fieldnames)

            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in data:
                    writer.writerow(row)

            result.records_exported = len(data)
            result.records_succeeded = len(data)
            result.success = True
            result.message = f"Exported {len(data)} records to {path}."

        except Exception as e:
            result.success = False
            result.message = str(e)
            result.errors.append(str(e))

        return result

    def get_supported_mappings(self) -> List[Dict]:
        return [
            {"source": "Name", "target": "name", "description": "Customer name"},
            {"source": "Phone", "target": "phone", "description": "Phone number"},
            {"source": "Email", "target": "email", "description": "Email address"},
            {"source": "IC", "target": "ic_number", "description": "IC number"},
            {"source": "Notes", "target": "notes", "description": "Customer notes"},
        ]

    def _apply_mappings(self, rows: List[Dict], mappings: List[FieldMappingData]) -> List[Dict]:
        """Transform rows using field mappings."""
        mapping_dict = {m.source_field: m.target_field for m in mappings if m.is_active}
        mapped_rows = []
        for row in rows:
            new_row = {}
            for source_key, value in row.items():
                target_key = mapping_dict.get(source_key, source_key)
                new_row[target_key] = value
            mapped_rows.append(new_row)
        return mapped_rows

    def _apply_reverse_mappings(self, data: List[Dict], mappings: List[FieldMappingData]) -> List[Dict]:
        """Transform rows back to external field names (for export)."""
        reverse_map = {m.target_field: m.source_field for m in mappings if m.is_active}
        mapped_data = []
        for row in data:
            new_row = {}
            for target_key, value in row.items():
                source_key = reverse_map.get(target_key, target_key)
                new_row[source_key] = value
            mapped_data.append(new_row)
        return mapped_data


# ── Google Sheets Connector ─────────────────────────────────────

class GoogleSheetsConnector(BaseConnector):
    """Sync customer data with Google Sheets."""

    display_name = "Google Sheets"
    connector_type = "crm"
    description = "Sync customer data with Google Sheets (API key or OAuth)"

    def __init__(self, connection: ExternalConnectionData, session=None):
        super().__init__(connection, session)
        self._sheet_id = connection.config.get("sheet_id", "")
        self._api_key = connection.credentials_ref or ""

    def connect(self) -> bool:
        # For MVP: just validate config
        self._sheet_id = self.connection.config.get("sheet_id", "")
        self._connected = bool(self._sheet_id)
        return self._connected

    def disconnect(self):
        self._connected = False

    def test_connection(self) -> Dict[str, Any]:
        if self._sheet_id:
            return {"ok": True, "message": f"Sheet ID configured: {self._sheet_id[:20]}..."}
        return {"ok": False, "message": "No Sheet ID configured."}

    def import_data(self, mappings: List[FieldMappingData] = None) -> SyncResult:
        # MVP: placeholder — real implementation needs Google Sheets API
        result = SyncResult()
        result.success = True
        result.message = ("Google Sheets import requires OAuth setup. "
                          "Configure via Settings > Integrations.")
        return result

    def export_data(self, data: List[Dict], mappings: List[FieldMappingData] = None) -> SyncResult:
        # MVP: placeholder
        result = SyncResult()
        result.success = True
        result.message = ("Google Sheets export requires OAuth setup. "
                          "Configure via Settings > Integrations.")
        return result

    def get_supported_mappings(self) -> List[Dict]:
        return [
            {"source": "Customer Name", "target": "name"},
            {"source": "Phone Number", "target": "phone"},
            {"source": "Email Address", "target": "email"},
            {"source": "IC Number", "target": "ic_number"},
        ]


# ── Google Calendar Connector ───────────────────────────────────

class GoogleCalendarConnector(BaseConnector):
    """Sync InsureDesk tasks/events with Google Calendar."""

    display_name = "Google Calendar"
    connector_type = "calendar"
    description = "Create and sync appointments, reviews, and follow-ups"

    def __init__(self, connection: ExternalConnectionData, session=None):
        super().__init__(connection, session)
        self._calendar_id = connection.config.get("calendar_id", "primary")

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False

    def test_connection(self) -> Dict[str, Any]:
        return {"ok": True, "message": "Google Calendar ready (OAuth setup required for live sync)."}

    def import_data(self, mappings: List[FieldMappingData] = None) -> SyncResult:
        result = SyncResult()
        result.success = True
        result.message = "Calendar events will be synced when OAuth is configured."
        return result

    def export_data(self, data: List[Dict], mappings: List[FieldMappingData] = None) -> SyncResult:
        """Export events/tasks to Google Calendar (placeholder for MVP)."""
        result = SyncResult()
        result.success = True
        result.message = f"Would create {len(data)} events in Google Calendar."
        return result

    def get_supported_mappings(self) -> List[Dict]:
        return [
            {"source": "Title", "target": "title"},
            {"source": "Description", "target": "description"},
            {"source": "Start Time", "target": "start_time"},
            {"source": "End Time", "target": "end_time"},
            {"source": "Location", "target": "location"},
        ]


# ── Register Connectors ─────────────────────────────────────────

ConnectorRegistry.register("csv", CSVConnector)
ConnectorRegistry.register("google_sheets", GoogleSheetsConnector)
ConnectorRegistry.register("google_calendar", GoogleCalendarConnector)


# ── Integration Repository ──────────────────────────────────────

class IntegrationRepository:
    """CRUD for external connections, field mappings, sync logs."""

    def __init__(self, session):
        self.session = session

    # ── Connections ──

    def list_connections(self, connection_type: str = None) -> List[ExternalConnectionData]:
        from src.database.models import ExternalConnection
        q = self.session.query(ExternalConnection).filter(ExternalConnection.is_active == True)
        if connection_type:
            q = q.filter(ExternalConnection.connection_type == connection_type)
        q = q.order_by(ExternalConnection.provider)
        return [self._conn_to_data(c) for c in q.all()]

    def get_connection(self, conn_id: str) -> Optional[ExternalConnectionData]:
        from src.database.models import ExternalConnection
        c = self.session.query(ExternalConnection).filter(ExternalConnection.id == conn_id).first()
        return self._conn_to_data(c) if c else None

    def create_connection(self, data: ExternalConnectionData) -> ExternalConnectionData:
        from src.database.models import ExternalConnection
        c = ExternalConnection(
            provider=data.provider,
            connection_type=data.connection_type,
            name=data.name or data.provider,
            credentials_ref=data.credentials_ref or "",
            config=data.config or {},
            status="disconnected",
        )
        self.session.add(c)
        self.session.commit()
        return self._conn_to_data(c)

    def update_connection(self, data: ExternalConnectionData) -> Optional[ExternalConnectionData]:
        from src.database.models import ExternalConnection
        c = self.session.query(ExternalConnection).filter(
            ExternalConnection.id == data.id
        ).first()
        if not c:
            return None
        if data.name: c.name = data.name
        if data.credentials_ref is not None: c.credentials_ref = data.credentials_ref
        if data.config: c.config = {**c.config, **data.config}
        if data.status: c.status = data.status
        if data.last_sync: c.last_sync = datetime.fromisoformat(data.last_sync)
        self.session.commit()
        return self._conn_to_data(c)

    def delete_connection(self, conn_id: str) -> bool:
        from src.database.models import ExternalConnection
        c = self.session.query(ExternalConnection).filter(
            ExternalConnection.id == conn_id
        ).first()
        if not c:
            return False
        c.is_active = False
        self.session.commit()
        return True

    def _conn_to_data(self, c) -> ExternalConnectionData:
        return ExternalConnectionData(
            id=str(c.id), provider=c.provider or "",
            connection_type=c.connection_type or "",
            name=c.name or "", credentials_ref=c.credentials_ref or "",
            config=dict(c.config) if c.config else {},
            status=c.status or "disconnected",
            last_sync=c.last_sync.isoformat() if c.last_sync else "",
            is_active=c.is_active if c.is_active is not None else True,
            created_at=c.created_at.isoformat() if c.created_at else "",
            updated_at=c.updated_at.isoformat() if c.updated_at else "",
        )

    # ── Field Mappings ──

    def list_mappings(self, connection_id: str) -> List[FieldMappingData]:
        from src.database.models import FieldMapping
        mappings = self.session.query(FieldMapping).filter(
            FieldMapping.connection_id == connection_id,
            FieldMapping.is_active == True,
        ).all()
        return [self._mapping_to_data(m) for m in mappings]

    def create_mapping(self, data: FieldMappingData) -> FieldMappingData:
        from src.database.models import FieldMapping
        m = FieldMapping(
            connection_id=data.connection_id,
            source_field=data.source_field,
            target_field=data.target_field,
            transform_rule=data.transform_rule or "",
        )
        self.session.add(m)
        self.session.commit()
        return self._mapping_to_data(m)

    def delete_mapping(self, mapping_id: str) -> bool:
        from src.database.models import FieldMapping
        m = self.session.query(FieldMapping).filter(
            FieldMapping.id == mapping_id
        ).first()
        if not m:
            return False
        m.is_active = False
        self.session.commit()
        return True

    def _mapping_to_data(self, m) -> FieldMappingData:
        return FieldMappingData(
            id=str(m.id), connection_id=str(m.connection_id),
            source_field=m.source_field or "",
            target_field=m.target_field or "",
            transform_rule=m.transform_rule or "",
            is_active=m.is_active if m.is_active is not None else True,
            created_at=m.created_at.isoformat() if m.created_at else "",
        )

    # ── Sync Logs ──

    def list_sync_logs(self, connection_id: str, limit: int = 20) -> List[SyncLogData]:
        from src.database.models import SyncLog
        logs = self.session.query(SyncLog).filter(
            SyncLog.connection_id == connection_id
        ).order_by(SyncLog.started_at.desc()).limit(limit).all()
        return [self._log_to_data(l) for l in logs]

    def create_sync_log(self, data: SyncLogData) -> SyncLogData:
        from src.database.models import SyncLog
        l = SyncLog(
            connection_id=data.connection_id,
            direction=data.direction or "import",
            status=data.status or "running",
            records_processed=data.records_processed or 0,
            records_succeeded=data.records_succeeded or 0,
            records_failed=data.records_failed or 0,
            error_message=data.error_message or "",
        )
        self.session.add(l)
        self.session.commit()
        return self._log_to_data(l)

    def complete_sync_log(self, log_id: str, status: str, processed: int = 0,
                          succeeded: int = 0, failed: int = 0,
                          error: str = "") -> Optional[SyncLogData]:
        from src.database.models import SyncLog
        l = self.session.query(SyncLog).filter(SyncLog.id == log_id).first()
        if not l:
            return None
        l.status = status
        l.records_processed = processed
        l.records_succeeded = succeeded
        l.records_failed = failed
        if error:
            l.error_message = error
        l.completed_at = _now()
        self.session.commit()
        return self._log_to_data(l)

    def _log_to_data(self, l) -> SyncLogData:
        return SyncLogData(
            id=str(l.id), connection_id=str(l.connection_id),
            direction=l.direction or "import",
            status=l.status or "running",
            records_processed=l.records_processed or 0,
            records_succeeded=l.records_succeeded or 0,
            records_failed=l.records_failed or 0,
            error_message=l.error_message or "",
            started_at=l.started_at.isoformat() if l.started_at else "",
            completed_at=l.completed_at.isoformat() if l.completed_at else "",
        )


# ── Calendar Event Repository ───────────────────────────────────

class CalendarEventRepository:
    """CRUD for calendar events."""

    def __init__(self, session):
        self.session = session

    def list_events(self, customer_id: str = None, status: str = None) -> List[CalendarEventData]:
        from src.database.models import CalendarEvent
        q = self.session.query(CalendarEvent)
        if customer_id:
            q = q.filter(CalendarEvent.customer_id == customer_id)
        if status:
            q = q.filter(CalendarEvent.status == status)
        q = q.order_by(CalendarEvent.start_time.asc()).limit(50)
        return [self._event_to_data(e) for e in q.all()]

    def get_by_task(self, task_id: str) -> Optional[CalendarEventData]:
        from src.database.models import CalendarEvent
        e = self.session.query(CalendarEvent).filter(
            CalendarEvent.task_id == task_id
        ).first()
        return self._event_to_data(e) if e else None

    def create_event(self, data: CalendarEventData) -> CalendarEventData:
        from src.database.models import CalendarEvent
        e = CalendarEvent(
            connection_id=data.connection_id or None,
            customer_id=data.customer_id or None,
            task_id=data.task_id or None,
            title=data.title,
            description=data.description or "",
            event_type=data.event_type or "appointment",
            start_time=datetime.fromisoformat(data.start_time) if data.start_time else None,
            end_time=datetime.fromisoformat(data.end_time) if data.end_time else None,
            location=data.location or "",
            external_id=data.external_id or "",
            status=data.status or "scheduled",
        )
        self.session.add(e)
        self.session.commit()
        return self._event_to_data(e)

    def update_event(self, data: CalendarEventData) -> Optional[CalendarEventData]:
        from src.database.models import CalendarEvent
        e = self.session.query(CalendarEvent).filter(
            CalendarEvent.id == data.id
        ).first()
        if not e:
            return None
        if data.title: e.title = data.title
        if data.description is not None: e.description = data.description
        if data.event_type: e.event_type = data.event_type
        if data.start_time: e.start_time = datetime.fromisoformat(data.start_time)
        if data.end_time: e.end_time = datetime.fromisoformat(data.end_time)
        if data.location is not None: e.location = data.location
        if data.status: e.status = data.status
        if data.external_id: e.external_id = data.external_id
        self.session.commit()
        return self._event_to_data(e)

    def _event_to_data(self, e) -> CalendarEventData:
        return CalendarEventData(
            id=str(e.id),
            connection_id=str(e.connection_id) if e.connection_id else "",
            customer_id=str(e.customer_id) if e.customer_id else "",
            task_id=str(e.task_id) if e.task_id else "",
            title=e.title or "",
            description=e.description or "",
            event_type=e.event_type or "appointment",
            start_time=e.start_time.isoformat() if e.start_time else "",
            end_time=e.end_time.isoformat() if e.end_time else "",
            location=e.location or "",
            external_id=e.external_id or "",
            status=e.status or "scheduled",
            created_at=e.created_at.isoformat() if e.created_at else "",
            updated_at=e.updated_at.isoformat() if e.updated_at else "",
        )


# ── Integration Service ─────────────────────────────────────────

class IntegrationService:
    """High-level service for managing integrations.

    Orchestrates: connection management → connector execution → sync logging.
    """

    def __init__(self, session, integration_repo: IntegrationRepository = None):
        self.session = session
        self.repo = integration_repo or IntegrationRepository(session)

    def connect_provider(self, provider: str, name: str = "",
                         credentials_ref: str = "", config: dict = None) -> ExternalConnectionData:
        """Create a new connection and test connectivity."""
        conn_cls = ConnectorRegistry.get(provider)
        if not conn_cls:
            raise ValueError(f"Unknown provider: {provider}")

        conn_data = ExternalConnectionData(
            provider=provider,
            connection_type=conn_cls.connector_type,
            name=name or provider,
            credentials_ref=credentials_ref or "",
            config=config or {},
        )
        connection = self.repo.create_connection(conn_data)

        # Test connection
        connector = conn_cls(connection, self.session)
        try:
            if connector.connect():
                connection.status = "connected"
                self.repo.update_connection(connection)
        except Exception:
            connection.status = "error"
            self.repo.update_connection(connection)

        return connection

    def sync_import(self, connection_id: str) -> SyncResult:
        """Import data from a connected external system."""
        conn = self.repo.get_connection(connection_id)
        if not conn:
            return SyncResult(success=False, message="Connection not found.")

        conn_cls = ConnectorRegistry.get(conn.provider)
        if not conn_cls:
            return SyncResult(success=False, message=f"Unknown provider: {conn.provider}")

        # Create sync log
        log = self.repo.create_sync_log(SyncLogData(
            connection_id=connection_id, direction="import", status="running"
        ))

        # Execute import
        connector = conn_cls(conn, self.session)
        mappings = self.repo.list_mappings(connection_id)
        try:
            result = connector.import_data(mappings)
            self.repo.complete_sync_log(
                log.id, "success" if result.success else "error",
                processed=result.records_processed,
                succeeded=result.records_succeeded,
                failed=result.records_failed,
                error="; ".join(result.errors) if result.errors else "",
            )
        except Exception as e:
            self.repo.complete_sync_log(log.id, "error", error=str(e))
            result = SyncResult(success=False, message=str(e))

        # Update last sync
        conn.last_sync = _now().isoformat()
        self.repo.update_connection(conn)
        return result

    def sync_export(self, connection_id: str, data: List[Dict]) -> SyncResult:
        """Export data to a connected external system."""
        conn = self.repo.get_connection(connection_id)
        if not conn:
            return SyncResult(success=False, message="Connection not found.")

        conn_cls = ConnectorRegistry.get(conn.provider)
        if not conn_cls:
            return SyncResult(success=False, message=f"Unknown provider: {conn.provider}")

        log = self.repo.create_sync_log(SyncLogData(
            connection_id=connection_id, direction="export", status="running"
        ))

        connector = conn_cls(conn, self.session)
        mappings = self.repo.list_mappings(connection_id)
        try:
            result = connector.export_data(data, mappings)
            self.repo.complete_sync_log(
                log.id, "success" if result.success else "error",
                processed=result.records_exported,
                succeeded=result.records_succeeded,
                failed=result.records_failed,
                error="; ".join(result.errors) if result.errors else "",
            )
        except Exception as e:
            self.repo.complete_sync_log(log.id, "error", error=str(e))
            result = SyncResult(success=False, message=str(e))

        conn.last_sync = _now().isoformat()
        self.repo.update_connection(conn)
        return result

    def get_dashboard(self) -> Dict:
        """Get integration overview for the UI."""
        connections = self.repo.list_connections()
        by_type = {"crm": {"connected": 0, "total": 0, "items": []},
                   "calendar": {"connected": 0, "total": 0, "items": []},
                   "accounting": {"connected": 0, "total": 0, "items": []}}

        for conn in connections:
            ct = conn.connection_type
            if ct not in by_type:
                continue
            by_type[ct]["total"] += 1
            if conn.status == "connected":
                by_type[ct]["connected"] += 1
            by_type[ct]["items"].append({
                "id": conn.id,
                "name": conn.name,
                "provider": conn.provider,
                "status": conn.status,
                "last_sync": conn.last_sync[:16] if conn.last_sync else "",
            })

        return {
            "connections": by_type,
            "total_connections": len(connections),
            "connected_count": sum(1 for c in connections if c.status == "connected"),
        }
