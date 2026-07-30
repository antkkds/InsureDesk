"""InsureDesk — Desktop Shell (PySide6 Main Application).

This is the main entry point for the InsureDesk desktop application.
"""

import sys
import os
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFrame, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QTextEdit, QDialog, QFormLayout, QComboBox, QTabWidget,
    QSplitter, QFileDialog, QListWidget, QListWidgetItem,
    QGroupBox, QScrollArea, QMenu, QMenuBar, QStatusBar,
    QToolBar, QInputDialog, QDialogButtonBox, QCheckBox,
    QDateEdit, QSpinBox, QDoubleSpinBox, QProgressBar,
)
from pathlib import Path
from PySide6.QtCore import Qt, QSize, Signal, Slot, QThread, QTimer
from PySide6.QtGui import QIcon, QFont, QAction, QPixmap

import logging
logger = logging.getLogger("insuredesk.desktop.app")

# Import InsureDesk modules
from src.database.db_manager import init_db, get_engine, get_session, seed_companies
from src.database.models import Base, Customer, Policy, Document, Company, Setting

from src.customers.repository import CustomerRepository, PolicyRepository, DocumentRepository, CustomerData, PolicyData, DocumentData
from src.documents.vault import DocumentVault
from src.bridge.protocol import BridgeClient, BridgeMessage, BridgeResponse
from src.browser.driver import BrowserEngine
from src.teams.repository import TeamRepository, AssignmentService, KnowledgeRepository, TeamDashboardService, TeamData, TeamMemberData
from src.integrations.connectors import IntegrationRepository, IntegrationService, ConnectorRegistry, ExternalConnectionData, FieldMappingData, CSVConnector
from src.predictive.engine import FamilyRepository, HealthScoreService, PredictiveService, DailyPlannerService, FamilyMemberData, LifeEventData
from src.autonomous.engine import GoalEngine, ProactiveEngine, ReviewEngine, ImprovementTracker
from src.runtime.credential_service import CredentialService


# ── Constants ────────────────────────────────────────────────────

APP_NAME = "InsureDesk"
APP_VERSION = "1.0.0"
APP_DIR = Path.home() / "InsureDesk"


# ── Main Window ──────────────────────────────────────────────────

class InsureDeskWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — Insurance Agent Workspace")
        self.setMinimumSize(1200, 800)

        # Initialize database
        engine = get_engine()
        init_db(engine)
        self.session = get_session(engine)
        seed_companies(self.session)

        # Initialize services
        self.customer_repo = CustomerRepository(self.session)
        self.policy_repo = PolicyRepository(self.session)
        self.document_vault = DocumentVault(self.session)
        self.bridge_client = BridgeClient()
        self.team_repo = TeamRepository(self.session)
        self.assignment_service = AssignmentService(self.session, self.team_repo)
        self.knowledge_repo = KnowledgeRepository(self.session)
        self.team_dashboard = TeamDashboardService(self.session, self.team_repo)
        self.integration_repo = IntegrationRepository(self.session)
        self.integration_service = IntegrationService(self.session, self.integration_repo)
        self.family_repo = FamilyRepository(self.session)
        self.health_service = HealthScoreService(self.session)
        self.predictive_service = PredictiveService(self.session)
        self.planner_service = DailyPlannerService(self.session)
        self.goal_engine = GoalEngine(self.session)
        self.goal_engine.initialize_defaults()
        self.proactive_engine = ProactiveEngine(self.session)
        self.review_engine = ReviewEngine(self.session)
        self.improvement_tracker = ImprovementTracker(self.session)

        # Credential Vault
        self.credential_service = CredentialService(self.session)

        # Browser engine (lazy)
        self.browser_engine = None

        # ── External plugins ──────────────────────────────
        self._load_external_plugins()

        # Assistant name
        self.assistant_name = self._get_setting("assistant_name", "Marry")

        # Build UI
        self._build_ui()

        # Connect to UIP-AI if token exists
        saved_token = self._get_setting("uip_ai_token", "")
        if saved_token:
            self.bridge_client.connect(saved_token)
            self._update_connection_status()

    def _load_external_plugins(self) -> None:
        """Load plugins from external ``plugins/`` directory.

        Searches relative to the executable (PyInstaller build) or
        the project root (development).
        """
        # Determine the base directory
        if getattr(sys, 'frozen', False):
            # PyInstaller COLLECT mode: plugins are in _internal/plugins/
            base = Path(sys.executable).parent / "_internal"
            if not (base / "plugins").is_dir():
                base = Path(sys.executable).parent
        else:
            base = Path(__file__).parent.parent.parent  # src/desktop/app.py → project root

        plugin_dir = base / "plugins"
        if not plugin_dir.is_dir():
            plugin_dir = Path.cwd() / "plugins"

        from src.plugins.registry import default_registry
        count = default_registry.load_from_directory(str(plugin_dir))
        if count > 0:
            logger.info("Loaded %d external plugin(s) from %s", count, plugin_dir)

    def _get_setting(self, key: str, default: str = "") -> str:
        setting = self.session.query(Setting).filter(Setting.key == key).first()
        return setting.value if setting else default

    def _set_setting(self, key: str, value: str):
        setting = self.session.query(Setting).filter(Setting.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = Setting(key=key, value=value)
            self.session.add(setting)
        self.session.commit()

    def _build_ui(self):
        """Build the main user interface."""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar navigation
        sidebar = self._build_sidebar()
        main_layout.addWidget(sidebar)

        # Content area (stacked widget for different views)
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack, 1)

        # Create views
        self.dashboard_view = DashboardWidget(self)
        self.customers_view = CustomersWidget(self)
        self.documents_view = DocumentsWidget(self)
        self.companies_view = CompaniesWidget(self)
        self.assistant_view = AssistantWidget(self)
        self.team_view = TeamWidget(self)
        self.settings_view = SettingsWidget(self, self.credential_service)

        self.content_stack.addWidget(self.dashboard_view)    # index 0
        self.content_stack.addWidget(self.customers_view)    # index 1
        self.content_stack.addWidget(self.documents_view)    # index 2
        self.content_stack.addWidget(self.companies_view)    # index 3
        self.content_stack.addWidget(self.assistant_view)    # index 4
        self.content_stack.addWidget(self.team_view)         # index 5
        self.content_stack.addWidget(self.settings_view)     # index 6

        # Show dashboard by default
        self.content_stack.setCurrentIndex(0)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.connection_label = QLabel("🔴 Disconnected")
        self.status_bar.addPermanentWidget(self.connection_label)

    def _build_sidebar(self) -> QWidget:
        """Build the left sidebar navigation."""
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("""
            QWidget {
                background-color: #1a1a2e;
                color: white;
            }
            QPushButton {
                text-align: left;
                padding: 12px 16px;
                border: none;
                color: #ccc;
                font-size: 13px;
                background: transparent;
            }
            QPushButton:hover {
                background-color: #16213e;
                color: white;
            }
            QPushButton:checked {
                background-color: #0f3460;
                color: #e94560;
                font-weight: bold;
            }
            QLabel#title {
                font-size: 18px;
                font-weight: bold;
                padding: 20px 16px 10px;
                color: #e94560;
            }
            QLabel#subtitle {
                font-size: 10px;
                padding: 0px 16px 20px;
                color: #888;
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Brand
        title = QLabel("InsureDesk")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("Powered by UIP-AI")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)

        # Navigation buttons
        self.nav_buttons = []
        nav_items = [
            ("🏠  Dashboard", 0),
            ("👥  Customers", 1),
            ("📄  Documents", 2),
            ("🌐  Companies", 3),
            ("🤖  Assistant", 4),
            ("🏢  Team", 5),
            ("⚙  Settings", 6),
        ]

        for text, idx in nav_items:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, i=idx: self._switch_view(i))
            layout.addWidget(btn)
            self.nav_buttons.append(btn)

        layout.addStretch()

        # Version
        version = QLabel(f"v{APP_VERSION}")
        version.setStyleSheet("padding: 10px 16px; color: #555; font-size: 10px;")
        layout.addWidget(version)

        return sidebar

    def _switch_view(self, index: int):
        """Switch to a different view."""
        self.content_stack.setCurrentIndex(index)
        for btn in self.nav_buttons:
            btn.setChecked(False)
        if index < len(self.nav_buttons):
            self.nav_buttons[index].setChecked(True)

    def _update_connection_status(self):
        """Update the connection status indicator."""
        if self.bridge_client.connected:
            self.connection_label.setText("🟢 Connected")
            self.connection_label.setStyleSheet("color: #4caf50;")
        else:
            self.connection_label.setText("🔴 Disconnected")
            self.connection_label.setStyleSheet("color: #f44336;")

    def closeEvent(self, event):
        """Clean up on close."""
        if self.browser_engine:
            import asyncio
            try:
                asyncio.run(self.browser_engine.stop())
            except:
                pass
        self.session.close()
        event.accept()


# ── Views ────────────────────────────────────────────────────────

class DashboardWidget(QWidget):
    """PI-8 Dashboard view — lifecycle intelligence for daily workflow.

    Answers: "Who needs my attention today?"

    Shows:
    - 🔴 Urgent items (renewal ≤ 7 days, grace period)
    - 🟡 Upcoming items (renewals in 8-30 days)
    - 📋 Today's tasks (scannable checklist)
    - 📊 Portfolio overview (counts by status)
    """

    def __init__(self, app: InsureDeskWindow):
        super().__init__()
        self.app = app
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(30, 30, 30, 30)
        self._build_header()
        self._build_content()

    def _build_header(self):
        # Header
        header = QLabel("🏠  Good Morning!")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #1a1a2e;")
        self._layout.addWidget(header)

        subtitle = QLabel(
            f"Your AI Assistant \"{self.app.assistant_name}\" is ready. "
            "Here's what needs your attention today."
        )
        subtitle.setStyleSheet("font-size: 14px; color: #666; margin-bottom: 15px;")
        subtitle.setWordWrap(True)
        self._layout.addWidget(subtitle)

    def _build_content(self):
        # Stats cards row
        self._stats_row = QHBoxLayout()
        self._layout.addLayout(self._stats_row)

        # Main content area
        splitter = QSplitter(Qt.Horizontal)

        # Left: urgent + upcoming
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 10, 0)

        # Urgent section
        urgent_group = QGroupBox("🔴  Urgent")
        urgent_group.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 14px; padding-top: 12px;
                        border: 1px solid #e0e0e0; border-radius: 8px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
        """)
        urgent_layout = QVBoxLayout(urgent_group)
        self.urgent_list = QLabel("No urgent items.")
        self.urgent_list.setStyleSheet("color: #888; padding: 10px;")
        self.urgent_list.setWordWrap(True)
        urgent_layout.addWidget(self.urgent_list)
        left_layout.addWidget(urgent_group)

        # Upcoming section
        upcoming_group = QGroupBox("🟡  Upcoming")
        upcoming_group.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 14px; padding-top: 12px;
                        border: 1px solid #e0e0e0; border-radius: 8px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
        """)
        upcoming_layout = QVBoxLayout(upcoming_group)
        self.upcoming_list = QLabel("No upcoming renewals.")
        self.upcoming_list.setStyleSheet("color: #888; padding: 10px;")
        self.upcoming_list.setWordWrap(True)
        upcoming_layout.addWidget(self.upcoming_list)
        left_layout.addWidget(upcoming_group)

        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # Right: portfolio overview + actions
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)

        # Portfolio overview
        portfolio_group = QGroupBox("📊  Portfolio Overview")
        portfolio_group.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 14px; padding-top: 12px;
                        border: 1px solid #e0e0e0; border-radius: 8px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
        """)
        portfolio_layout = QVBoxLayout(portfolio_group)
        self.portfolio_stats = QLabel("Loading...")
        self.portfolio_stats.setStyleSheet("font-size: 13px; padding: 10px;")
        portfolio_layout.addWidget(self.portfolio_stats)
        right_layout.addWidget(portfolio_group)

        # Quick Actions
        actions_group = QGroupBox("⚡  Quick Actions")
        actions_group.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 14px; padding-top: 12px;
                        border: 1px solid #e0e0e0; border-radius: 8px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
        """)
        actions_layout = QVBoxLayout(actions_group)

        quick_actions = [
            ("👤  New Customer", self._new_customer, "#4caf50"),
            ("📄  Upload Document", self._upload_doc, "#2196f3"),
            ("🔍  Scan Renewals", self._scan_now, "#ff9800"),
            ("🤖  Ask Assistant", self._ask_assistant, "#9c27b0"),
        ]
        for label, callback, color in quick_actions:
            btn = QPushButton(label)
            btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 12px; font-size: 13px; text-align: left;
                    background: white; border: 1px solid #e0e0e0;
                    border-radius: 6px; color: {color};
                }}
                QPushButton:hover {{ background: #f5f5f5; border-color: {color}; }}
            """)
            btn.clicked.connect(callback)
            actions_layout.addWidget(btn)

        right_layout.addWidget(actions_group)

        # ── PI-20: Autonomous Review ──
        auto_group = QGroupBox("🤖  Autonomous Review")
        auto_group.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 14px; padding-top: 12px;
                        border: 1px solid #e0e0e0; border-radius: 8px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
        """)
        auto_layout = QVBoxLayout(auto_group)
        self.review_summary = QLabel("Run morning review to see today's priorities.")
        self.review_summary.setStyleSheet("color: #888; padding: 8px; font-size: 12px;")
        self.review_summary.setWordWrap(True)
        auto_layout.addWidget(self.review_summary)
        self.review_goals = QLabel("")
        self.review_goals.setStyleSheet("color: #555; padding: 4px 8px; font-size: 11px;")
        self.review_goals.setWordWrap(True)
        auto_layout.addWidget(self.review_goals)
        run_review_btn = QPushButton("▶  Generate Morning Review")
        run_review_btn.setStyleSheet("""
            QPushButton { background: #1a1a2e; color: white; padding: 8px 16px;
                          border-radius: 6px; font-weight: bold; }
            QPushButton:hover { background: #0f3460; }
        """)
        run_review_btn.clicked.connect(self._run_morning_review)
        auto_layout.addWidget(run_review_btn)
        right_layout.addWidget(auto_group)

        right_layout.addStretch()

        splitter.addWidget(right_panel)
        splitter.setSizes([500, 400])
        self._layout.addWidget(splitter)

        # Refresh timer (every 5 minutes)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(300000)

        # Refresh button
        refresh_layout = QHBoxLayout()
        refresh_layout.addStretch()
        refresh_btn = QPushButton("🔄  Refresh Dashboard")
        refresh_btn.setStyleSheet("""
            QPushButton { padding: 6px 14px; font-size: 12px;
                          background: #f5f5f5; border: 1px solid #ddd;
                          border-radius: 4px; }
            QPushButton:hover { background: #e8e8e8; }
        """)
        refresh_btn.clicked.connect(self.refresh)
        refresh_layout.addWidget(refresh_btn)
        self._layout.addLayout(refresh_layout)

        # Initial load
        QTimer.singleShot(500, self.refresh)

    def refresh(self):
        """Refresh dashboard from UIP-AI."""
        try:
            # Local stats from database
            total_customers = self.app.session.query(Customer).count()
            total_policies = self.app.session.query(Policy).count()

            # Try UIP-AI dashboard
            dashboard_data = None
            if self.app.bridge_client.connected:
                dashboard_data = self.app.bridge_client.get_dashboard()

            if dashboard_data:
                # Update urgent list
                urgent = dashboard_data.get("urgent_items", [])
                if urgent:
                    html = "<div style='line-height: 1.6;'>"
                    for item in urgent[:10]:
                        html += (
                            f"<div style='padding: 6px 8px; margin: 2px 0; "
                            f"background: #fff5f5; border-left: 3px solid #e94560; "
                            f"border-radius: 3px;'>"
                            f"<b>{item.get('product_name', 'Policy')}</b> — "
                            f"{item.get('company', '')}<br>"
                            f"<span style='color: #888; font-size: 12px;'>"
                            f"Due: {item.get('due_date', 'N/A')} — {item.get('reason', '')}"
                            f"</span></div>"
                        )
                    html += "</div>"
                    self.urgent_list.setText(html)
                else:
                    self.urgent_list.setText("✅  No urgent items today.")

                # Update upcoming list
                upcoming = dashboard_data.get("upcoming_items", [])
                if upcoming:
                    html = "<div style='line-height: 1.6;'>"
                    for item in upcoming[:10]:
                        html += (
                            f"<div style='padding: 6px 8px; margin: 2px 0; "
                            f"background: #fffef5; border-left: 3px solid #ff9800; "
                            f"border-radius: 3px;'>"
                            f"<b>{item.get('product_name', 'Policy')}</b> — "
                            f"{item.get('company', '')}<br>"
                            f"<span style='color: #888; font-size: 12px;'>"
                            f"Due: {item.get('due_date', '')}"
                            f"</span></div>"
                        )
                    html += "</div>"
                    self.upcoming_list.setText(html)
                else:
                    self.upcoming_list.setText("No upcoming renewals.")

                # Update portfolio overview
                portfolio = dashboard_data.get("portfolio", {})
                p_text = (
                    f"<div style='line-height: 1.8; font-size: 14px;'>"
                    f"👥  Customers: <b>{portfolio.get('total_customers', total_customers)}</b><br>"
                    f"📋  Total Policies: <b>{portfolio.get('total_policies', total_policies)}</b><br>"
                    f"🟢  Active: <b>{portfolio.get('active', 0)}</b><br>"
                    f"🟡  Renewing: <b>{portfolio.get('renewing', 0)}</b><br>"
                    f"🔴  Lapsed: <b>{portfolio.get('lapsed', 0)}</b><br>"
                    f"📨  Changes: <b>{dashboard_data.get('changes_pending', 0)}</b>"
                    f"</div>"
                )
                self.portfolio_stats.setText(p_text)

            else:
                # Fallback: local stats only
                p_text = (
                    f"<div style='line-height: 1.8; font-size: 14px;'>"
                    f"👥  Customers: <b>{total_customers}</b><br>"
                    f"📋  Policies: <b>{total_policies}</b><br>"
                    f"🔗  UIP-AI: <b style='color: #e94560;'>Disconnected</b>"
                    f"</div>"
                )
                self.portfolio_stats.setText(p_text)
                self.urgent_list.setText("🔴  UIP-AI not connected. Lifecycle data unavailable.")

        except Exception as e:
            self.urgent_list.setText(f"⚠️  Dashboard error: {e}")

    def _new_customer(self):
        self.app._switch_view(1)
        self.app.customers_view._add_customer()

    def _upload_doc(self):
        self.app._switch_view(2)

    def _scan_now(self):
        """Trigger a lifecycle scan and refresh."""
        if self.app.bridge_client.connected:
            result = self.app.bridge_client.scan_lifecycles()
            if result:
                self.refresh()
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Not Connected",
                              "UIP-AI is not connected. Cannot scan lifecycles.")

    def _ask_assistant(self):
        self.app._switch_view(4)

    def _run_morning_review(self):
        """Generate autonomous morning review briefing."""
        try:
            self.review_summary.setText("⏳ Generating morning review...")
            QApplication.processEvents()
            review = self.app.review_engine.generate_morning_review()
            self.review_summary.setText(f"📋 **{review.summary}**")
            # Goals status
            goal_lines = []
            for g in review.goals:
                icon = "🟢" if g["status"] == "on_track" else "🟡" if g["status"] == "needs_attention" else "🔴"
                goal_lines.append(f"{icon} {g['name']}: {g['current']}/{g['target']} {g['unit']}")
            self.review_goals.setText("\n".join(goal_lines))
        except Exception as e:
            self.review_summary.setText(f"⚠ Error: {e}")


class CustomersWidget(QWidget):
    """Customer workspace — manage insurance customers."""

    def __init__(self, app: InsureDeskWindow):
        super().__init__()
        self.app = app
        self.current_customer_id = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QHBoxLayout()
        title = QLabel("👥  Customers")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1a1a2e;")
        header.addWidget(title)
        header.addStretch()

        search_box = QLineEdit()
        search_box.setPlaceholderText("Search customers...")
        search_box.setFixedWidth(250)
        search_box.textChanged.connect(self._search)
        header.addWidget(search_box)

        add_btn = QPushButton("+ New Customer")
        add_btn.setStyleSheet("""
            QPushButton { padding: 8px 16px; background: #e94560; color: white;
                          border: none; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #d63851; }
        """)
        add_btn.clicked.connect(self._add_customer)
        header.addWidget(add_btn)

        layout.addLayout(header)

        # Splitter: customer list + details
        splitter = QSplitter(Qt.Horizontal)

        # Left: customer list
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        self.customer_table = QTableWidget()
        self.customer_table.setColumnCount(5)
        self.customer_table.setHorizontalHeaderLabels(["Name", "Phone", "IC Number", "Policies", "Language"])
        self.customer_table.horizontalHeader().setStretchLastSection(True)
        self.customer_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.customer_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.customer_table.setSelectionMode(QTableWidget.SingleSelection)
        self.customer_table.itemSelectionChanged.connect(self._on_customer_selected)
        self.customer_table.setAlternatingRowColors(True)
        list_layout.addWidget(self.customer_table)

        splitter.addWidget(list_widget)

        # Right: customer details
        self.details_widget = CustomerDetailsWidget(app)
        splitter.addWidget(self.details_widget)

        splitter.setSizes([400, 500])
        layout.addWidget(splitter)

        self._refresh_list()

    def _refresh_list(self):
        customers = self.app.customer_repo.list_all()
        self.customer_table.setRowCount(len(customers))
        for row, c in enumerate(customers):
            policies = self.app.customer_repo.get_policies(c.id)
            self.customer_table.setItem(row, 0, QTableWidgetItem(c.name))
            self.customer_table.setItem(row, 1, QTableWidgetItem(c.phone))
            self.customer_table.setItem(row, 2, QTableWidgetItem(c.ic_number))
            self.customer_table.setItem(row, 3, QTableWidgetItem(str(len(policies))))
            lang_map = {"en": "English", "ms": "Bahasa", "zh": "中文"}
            self.customer_table.setItem(row, 4, QTableWidgetItem(lang_map.get(c.language, c.language)))

            # Store customer ID in first column
            self.customer_table.item(row, 0).setData(Qt.UserRole, c.id)

    def _search(self, query: str):
        if not query.strip():
            self._refresh_list()
            return
        customers = self.app.customer_repo.search(query)
        self.customer_table.setRowCount(len(customers))
        for row, c in enumerate(customers):
            policies = self.app.customer_repo.get_policies(c.id)
            self.customer_table.setItem(row, 0, QTableWidgetItem(c.name))
            self.customer_table.setItem(row, 1, QTableWidgetItem(c.phone))
            self.customer_table.setItem(row, 2, QTableWidgetItem(c.ic_number))
            self.customer_table.setItem(row, 3, QTableWidgetItem(str(len(policies))))
            self.customer_table.item(row, 0).setData(Qt.UserRole, c.id)

    def _on_customer_selected(self):
        rows = self.customer_table.selectedItems()
        if not rows:
            return
        row = rows[0].row()
        item = self.customer_table.item(row, 0)
        if item:
            customer_id = item.data(Qt.UserRole)
            self.current_customer_id = customer_id
            self.details_widget.show_customer(customer_id)

    def _add_customer(self):
        dialog = CustomerDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            self.app.customer_repo.create(data)
            self._refresh_list()


class CustomerDetailsWidget(QWidget):
    """Right panel showing customer details, policies, and documents."""

    def __init__(self, app: InsureDeskWindow):
        super().__init__()
        self.app = app
        self.current_customer_id = None
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        self.info_tab = QWidget()
        self.policies_tab = QWidget()
        self.docs_tab = QWidget()

        tabs.addTab(self.info_tab, "Info")
        tabs.addTab(self.policies_tab, "Policies")
        tabs.addTab(self.docs_tab, "Documents")

        # Policy Intelligence tab (powered by UIP-AI)
        self.policy_intel_tab = QWidget()
        tabs.addTab(self.policy_intel_tab, "Policy Intel")
        intel_layout = QVBoxLayout(self.policy_intel_tab)

        # Upload & Parse button
        upload_parse_btn = QPushButton("📤 Upload PDF to UIP-AI for Parsing")
        upload_parse_btn.setStyleSheet(
            "QPushButton { background-color: #2563eb; color: white; padding: 10px; "
            "font-size: 14px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
        )
        upload_parse_btn.clicked.connect(self._upload_to_uipai)
        intel_layout.addWidget(upload_parse_btn)

        # Parse status
        self.parse_status_label = QLabel("No policy parsed yet. Upload a PDF to get started.")
        self.parse_status_label.setStyleSheet("color: #666; padding: 8px;")
        intel_layout.addWidget(self.parse_status_label)

        # Parsed policies list
        intel_layout.addWidget(QLabel("Parsed Policies:"))
        self.parsed_table = QTableWidget()
        self.parsed_table.setColumnCount(5)
        self.parsed_table.setHorizontalHeaderLabels(["Company", "Policy #", "Type", "Status", "Premium"])
        self.parsed_table.horizontalHeader().setStretchLastSection(True)
        intel_layout.addWidget(self.parsed_table)

        # Coverage detail section
        self.parse_detail_area = QTextEdit()
        self.parse_detail_area.setReadOnly(True)
        intel_layout.addWidget(QLabel("Coverage Details (from UIP-AI):"))
        intel_layout.addWidget(self.parse_detail_area, 1)

        # Info tab
        info_layout = QFormLayout(self.info_tab)
        self.name_label = QLabel("")
        self.phone_label = QLabel("")
        self.ic_label = QLabel("")
        self.email_label = QLabel("")
        self.notes_label = QLabel("")
        self.notes_label.setWordWrap(True)

        info_layout.addRow("Name:", self.name_label)
        info_layout.addRow("Phone:", self.phone_label)
        info_layout.addRow("IC:", self.ic_label)
        info_layout.addRow("Email:", self.email_label)
        info_layout.addRow("Notes:", self.notes_label)

        # Policies tab
        policies_layout = QVBoxLayout(self.policies_tab)
        self.policies_table = QTableWidget()
        self.policies_table.setColumnCount(5)
        self.policies_table.setHorizontalHeaderLabels(["Company", "Policy #", "Type", "Status", "Premium"])
        self.policies_table.horizontalHeader().setStretchLastSection(True)
        policies_layout.addWidget(self.policies_table)

        add_policy_btn = QPushButton("+ Add Policy")
        add_policy_btn.clicked.connect(self._add_policy)
        policies_layout.addWidget(add_policy_btn)

        # Documents tab
        docs_layout = QVBoxLayout(self.docs_tab)
        self.docs_table = QTableWidget()
        self.docs_table.setColumnCount(4)
        self.docs_table.setHorizontalHeaderLabels(["File", "Type", "Size", "Date"])
        self.docs_table.horizontalHeader().setStretchLastSection(True)
        docs_layout.addWidget(self.docs_table)

        upload_btn = QPushButton("+ Upload Document")
        upload_btn.clicked.connect(self._upload_doc)
        docs_layout.addWidget(upload_btn)

        # ── Portfolio tab (PI-6) ───────────────────────────────────
        self.portfolio_tab = QWidget()
        tabs.addTab(self.portfolio_tab, "Portfolio")
        portfolio_layout = QVBoxLayout(self.portfolio_tab)

        # Build Portfolio button
        build_portfolio_btn = QPushButton("📊 Build Portfolio from Parsed Policies")
        build_portfolio_btn.setStyleSheet(
            "QPushButton { background-color: #059669; color: white; padding: 10px; "
            "font-size: 14px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #047857; }"
        )
        build_portfolio_btn.clicked.connect(self._build_portfolio)
        portfolio_layout.addWidget(build_portfolio_btn)

        # Portfolio status
        self.portfolio_status = QLabel("Build portfolio to see customer's insurance summary.")
        self.portfolio_status.setStyleSheet("color: #666; padding: 8px;")
        portfolio_layout.addWidget(self.portfolio_status)

        # Portfolio summary area
        self.portfolio_summary = QTextEdit()
        self.portfolio_summary.setReadOnly(True)
        self.portfolio_summary.setPlaceholderText("Portfolio summary will appear here...")
        portfolio_layout.addWidget(QLabel("Portfolio Summary:"))
        portfolio_layout.addWidget(self.portfolio_summary, 1)

        # Gap analysis section
        gap_btn = QPushButton("🔍 Analyze Coverage Gaps")
        gap_btn.setStyleSheet(
            "QPushButton { background-color: #d97706; color: white; padding: 8px; "
            "font-size: 13px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #b45309; }"
        )
        gap_btn.clicked.connect(self._analyze_gaps)
        portfolio_layout.addWidget(gap_btn)

        self.gap_area = QTextEdit()
        self.gap_area.setReadOnly(True)
        self.gap_area.setPlaceholderText("Gap analysis results will appear here...")
        portfolio_layout.addWidget(QLabel("Coverage Gaps:"))
        portfolio_layout.addWidget(self.gap_area)

        # Portfolio query
        portfolio_layout.addWidget(QLabel("Ask about Portfolio:"))
        query_layout = QHBoxLayout()
        self.portfolio_query_input = QLineEdit()
        self.portfolio_query_input.setPlaceholderText("e.g. 我的保险怎么样？")
        self.portfolio_query_input.returnPressed.connect(self._query_portfolio)
        query_layout.addWidget(self.portfolio_query_input)
        query_send_btn = QPushButton("Ask")
        query_send_btn.clicked.connect(self._query_portfolio)
        query_layout.addWidget(query_send_btn)
        portfolio_layout.addLayout(query_layout)

        self.portfolio_query_result = QLabel("")
        self.portfolio_query_result.setWordWrap(True)
        self.portfolio_query_result.setStyleSheet("padding: 8px; background: #f0fdf4; border: 1px solid #86efac; border-radius: 4px;")
        portfolio_layout.addWidget(self.portfolio_query_result)

        layout.addWidget(tabs)

    def show_customer(self, customer_id: str):
        self.current_customer_id = customer_id
        c = self.app.customer_repo.get_by_id(customer_id)
        if not c:
            return

        self.name_label.setText(c.name)
        self.phone_label.setText(c.phone)
        self.ic_label.setText(c.ic_number)
        self.email_label.setText(c.email)
        self.notes_label.setText(c.notes)

        # Refresh policies
        policies = self.app.customer_repo.get_policies(customer_id)
        self.policies_table.setRowCount(len(policies))
        for row, p in enumerate(policies):
            self.policies_table.setItem(row, 0, QTableWidgetItem(p.company))
            self.policies_table.setItem(row, 1, QTableWidgetItem(p.policy_number))
            self.policies_table.setItem(row, 2, QTableWidgetItem(p.policy_type))
            self.policies_table.setItem(row, 3, QTableWidgetItem(p.status))
            self.policies_table.setItem(row, 4, QTableWidgetItem(p.premium))

        # Refresh documents
        docs = self.app.document_vault.list_by_customer(customer_id)
        self.docs_table.setRowCount(len(docs))
        for row, d in enumerate(docs):
            self.docs_table.setItem(row, 0, QTableWidgetItem(d.filename))
            self.docs_table.setItem(row, 1, QTableWidgetItem(d.doc_type))
            size_str = f"{d.file_size / 1024:.1f} KB" if d.file_size else ""
            self.docs_table.setItem(row, 2, QTableWidgetItem(size_str))
            self.docs_table.setItem(row, 3, QTableWidgetItem(d.created_at[:10] if d.created_at else ""))

        # Refresh Policy Intelligence
        self._refresh_parsed_policies(customer_id)

    def _refresh_parsed_policies(self, customer_id: str):
        """Refresh the Policy Intel tab — display UIP-AI parsed results from DB."""
        from src.database.models import PolicyParseRecord

        records = (
            self.app.session.query(PolicyParseRecord)
            .filter(PolicyParseRecord.customer_id == customer_id)
            .order_by(PolicyParseRecord.created_at.desc())
            .all()
        )

        # Parsed policies table
        self.parsed_table.setRowCount(len(records))
        for row, r in enumerate(records):
            self.parsed_table.setItem(row, 0, QTableWidgetItem(r.company or r.policy_number))
            self.parsed_table.setItem(row, 1, QTableWidgetItem(r.policy_number or ""))
            self.parsed_table.setItem(row, 2, QTableWidgetItem(r.policy_type or ""))
            status_display = "✅ " + r.status if r.parse_status == "done" else f"⏳ {r.parse_status}"
            self.parsed_table.setItem(row, 3, QTableWidgetItem(status_display))
            self.parsed_table.setItem(row, 4, QTableWidgetItem(r.premium or ""))

        # Show latest parse details
        if records:
            latest = records[0]
            if latest.parse_status == "done" and latest.raw_json:
                try:
                    coverages = json.loads(latest.coverages_json) if latest.coverages_json else []
                    exclusions = json.loads(latest.exclusions_json) if latest.exclusions_json else []
                    detail = f"Company: {latest.company or '—'}\n"
                    detail += f"Policy No: {latest.policy_number or '—'}\n"
                    detail += f"Type: {latest.policy_type or '—'}\n"
                    detail += f"Status: {latest.status}\n"
                    detail += f"Premium: {latest.premium or '—'}\n"
                    detail += f"Period: {latest.start_date or '?'} → {latest.end_date or '?'}\n\n"
                    detail += "Coverages:\n"
                    for c in coverages:
                        amt = c.get("amount", c.get("limit", "—"))
                        note = f" ({c.get('note', '')})" if c.get("note") else ""
                        detail += f"  • {c.get('name', '?')}: {amt}{note}\n"
                    detail += "\nExclusions:\n"
                    for e in exclusions:
                        detail += f"  • {e if isinstance(e, str) else e.get('description', str(e))}\n"
                    if latest.summary:
                        detail += f"\nSummary: {latest.summary}"
                    self.parse_detail_area.setPlainText(detail)
                    self.parse_status_label.setText(f"✅ Parsed v{latest.version} — {latest.created_at[:10] if latest.created_at else ''}")
                    self.parse_status_label.setStyleSheet("color: #16a34a; padding: 8px;")
                except Exception:
                    self.parse_detail_area.setPlainText("Unable to display parsed data. Raw response stored.")
                    self.parse_status_label.setText("⚠️ Parse data format issue")
            elif latest.parse_status == "error":
                self.parse_status_label.setText(f"❌ Parse failed: {latest.error_message or 'Unknown error'}")
                self.parse_status_label.setStyleSheet("color: #dc2626; padding: 8px;")
            else:
                self.parse_status_label.setText(f"⏳ Parsing... (status: {latest.parse_status})")
                self.parse_status_label.setStyleSheet("color: #ca8a04; padding: 8px;")
        else:
            self.parse_detail_area.setPlainText("Upload a PDF policy document and UIP-AI will parse it automatically.")
            self.parse_status_label.setText("No policy parsed yet. Upload a PDF to get started.")

    def _upload_to_uipai(self):
        """Upload a PDF to UIP-AI for OCR + LLM parsing."""
        if not self.current_customer_id:
            QMessageBox.warning(self, "No Customer", "Select a customer first.")
            return

        if not self.app.bridge_client.connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to UIP-AI first (Settings).")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Policy Document", "",
            "PDF Files (*.pdf);;Images (*.png *.jpg *.jpeg);;All Files (*)"
        )
        if not file_path:
            return

        self.parse_status_label.setText("⏳ Uploading to UIP-AI for OCR + parsing...")
        self.parse_status_label.setStyleSheet("color: #ca8a04; padding: 8px;")
        QMessageBox.information(self, "Uploading", "Policy PDF uploaded to UIP-AI. Results will appear here when parsing is complete.")

        # Upload PDF to UIP-AI via Bridge
        result = self.app.bridge_client.upload_policy(file_path, self.current_customer_id)

        if result:
            from src.database.models import PolicyParseRecord

            # Save UIP-AI parsed result to database
            record = PolicyParseRecord(
                customer_id=self.current_customer_id,
                company=result.get("company", ""),
                policy_number=result.get("policy_number", ""),
                policy_type=result.get("policy_type", ""),
                status=result.get("status", "active"),
                premium=result.get("premium", ""),
                start_date=result.get("start_date", ""),
                end_date=result.get("end_date", ""),
                coverages_json=json.dumps(result.get("coverages", [])),
                exclusions_json=json.dumps(result.get("exclusions", [])),
                summary=result.get("summary", ""),
                raw_json=json.dumps(result),
                parse_status="done",
            )
            self.app.session.add(record)
            self.app.session.commit()

            self._refresh_parsed_policies(self.current_customer_id)
        else:
            self.parse_status_label.setText("❌ Failed to parse policy. Check UIP-AI connection.")
            self.parse_status_label.setStyleSheet("color: #dc2626; padding: 8px;")

    # ── Portfolio methods (PI-6) ──────────────────────────────────

    def _get_parsed_policies_for_portfolio(self) -> list:
        """Get parsed policies from DB in portfolio format."""
        if not self.current_customer_id:
            return []
        from src.database.models import PolicyParseRecord
        records = (
            self.app.session.query(PolicyParseRecord)
            .filter(PolicyParseRecord.customer_id == self.current_customer_id)
            .all()
        )
        policies = []
        for r in records:
            policies.append({
                "parse_result": {
                    "policy": {
                        "company": r.company or "",
                        "product_name": r.policy_number or "",
                        "premium": float(r.premium) if r.premium else None,
                    },
                    "coverage": json.loads(r.coverages_json) if r.coverages_json else [],
                    "exclusions": json.loads(r.exclusions_json) if r.exclusions_json else [],
                    "summary": r.summary or "",
                },
                "metadata": {
                    "policy_id": r.id or "",
                    "source": "agent_upload",
                    "relationship": "sold_by_agent",
                },
            })
        return policies

    def _build_portfolio(self):
        """Build customer portfolio via UIP-AI and display it."""
        if not self.current_customer_id:
            QMessageBox.warning(self, "No Customer", "Select a customer first.")
            return
        if not self.app.bridge_client.connected:
            QMessageBox.warning(self, "Not Connected", "Connect to UIP-AI first.")
            return

        customer = self.app.customer_repo.get_by_id(self.current_customer_id)
        if not customer:
            return

        policies = self._get_parsed_policies_for_portfolio()
        if not policies:
            self.portfolio_status.setText("⚠️ No parsed policies found. Upload policies via Policy Intel tab first.")
            self.portfolio_status.setStyleSheet("color: #ca8a04; padding: 8px;")
            return

        self.portfolio_status.setText("⏳ Building portfolio...")
        self.portfolio_status.setStyleSheet("color: #ca8a04; padding: 8px;")

        result = self.app.bridge_client.build_portfolio(
            customer_id=self.current_customer_id,
            customer_name=customer.name,
            policies=policies,
        )

        if result:
            self._display_portfolio(result)
            self.portfolio_status.setText("✅ Portfolio built successfully!")
            self.portfolio_status.setStyleSheet("color: #059669; padding: 8px;")
            # Store for further use
            self._last_portfolio_data = result
        else:
            self.portfolio_status.setText("❌ Failed to build portfolio.")
            self.portfolio_status.setStyleSheet("color: #dc2626; padding: 8px;")

    def _display_portfolio(self, portfolio: dict):
        """Display portfolio data in the UI."""
        lines = []
        lines.append(f"Customer: {portfolio.get('customer_name', 'N/A')}")
        lines.append(f"Total Policies: {portfolio.get('total_policies', 0)}")
        lines.append(f"Total Premium: RM{portfolio.get('total_premium', 0):,.2f}/year")
        lines.append("")

        groups = [
            ("Medical", "medical_policies"),
            ("Life", "life_policies"),
            ("Motor", "motor_policies"),
            ("Personal Accident", "pa_policies"),
            ("Travel", "travel_policies"),
            ("Home", "home_policies"),
            ("Other", "other_policies"),
        ]

        for label, key in groups:
            policies = portfolio.get(key, [])
            if not policies:
                continue
            lines.append(f"── {label} ──")
            for p in policies:
                lines.append(f"  {p.get('company', '')} - {p.get('product_name', '')}")
                prem = p.get('premium')
                if prem:
                    lines.append(f"    Premium: RM{float(prem):,.2f}/year")
                src = p.get('source', '')
                rel = p.get('relationship', '')
                if src or rel:
                    lines.append(f"    Source: {src} | Relationship: {rel}")
                coverages = p.get('key_coverages', [])
                if coverages:
                    lines.append(f"    Key: {', '.join(coverages[:3])}")
                lines.append("")

        self.portfolio_summary.setText("\n".join(lines))

    def _analyze_gaps(self):
        """Analyze coverage gaps via UIP-AI."""
        if not hasattr(self, '_last_portfolio_data') or not self._last_portfolio_data:
            QMessageBox.warning(self, "No Portfolio", "Build the portfolio first.")
            return

        customer = self.app.customer_repo.get_by_id(self.current_customer_id)
        if not customer:
            return

        policies = self._get_parsed_policies_for_portfolio()
        self.gap_area.setText("⏳ Analyzing gaps...")

        gaps = self.app.bridge_client.analyze_gaps(
            customer_id=self.current_customer_id,
            customer_name=customer.name,
            policies=policies,
            customer_age=0,  # Could be extended with actual age
        )

        if gaps is None:
            self.gap_area.setText("❌ Failed to analyze gaps.")
            return

        if not gaps:
            self.gap_area.setText("✅ No significant coverage gaps found.")
            return

        lines = []
        for g in gaps:
            level_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            icon = level_icon.get(g.get("gap_level", "medium"), "⚪")
            lines.append(f"{icon} {g.get('category', '')} ({g.get('gap_level', '')})")
            lines.append(f"   {g.get('description', '')}")
            lines.append(f"   Current: {g.get('current_coverage', 'N/A')}")
            lines.append(f"   Suggestion: {g.get('suggestion', '')}")
            lines.append("")

        self.gap_area.setText("\n".join(lines))

    def _query_portfolio(self):
        """Send a portfolio query to UIP-AI."""
        text = self.portfolio_query_input.text().strip()
        if not text:
            return
        if not hasattr(self, '_last_portfolio_data') or not self._last_portfolio_data:
            self.portfolio_query_result.setText("⚠️ Build the portfolio first.")
            return

        customer = self.app.customer_repo.get_by_id(self.current_customer_id)
        if not customer:
            return

        policies = self._get_parsed_policies_for_portfolio()
        self.portfolio_query_result.setText("⏳ Asking UIP-AI...")

        answer = self.app.bridge_client.query_portfolio(
            customer_id=self.current_customer_id,
            customer_name=customer.name,
            policies=policies,
            question=text,
        )

        if answer:
            self.portfolio_query_result.setText(f"🤖 {answer}")
        else:
            self.portfolio_query_result.setText("❌ Failed to get answer.")

    def _add_policy(self):
        if not self.current_customer_id:
            return
        # Get companies from DB
        companies = self.app.session.query(Company).filter(Company.is_active == True).all()
        company_names = [c.name for c in companies]

        dialog = PolicyDialog(self, company_names)
        if dialog.exec():
            data = dialog.get_data()
            data.customer_id = self.current_customer_id
            self.app.policy_repo.create(data)
            self.show_customer(self.current_customer_id)

    def _upload_doc(self):
        if not self.current_customer_id:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Document", "",
            "All Files (*);;PDF (*.pdf);;Images (*.png *.jpg *.jpeg)"
        )
        if file_path:
            doc = self.app.document_vault.import_file(
                file_path, self.current_customer_id,
                doc_type="other",
                tags=[],
            )
            if doc:
                self.show_customer(self.current_customer_id)


class DocumentsWidget(QWidget):
    """Document Vault view."""

    def __init__(self, app: InsureDeskWindow):
        super().__init__()
        self.app = app
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📄  Document Vault")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1a1a2e;")
        layout.addWidget(title)

        # Search + filter
        search_layout = QHBoxLayout()
        search = QLineEdit()
        search.setPlaceholderText("Search documents...")
        search_layout.addWidget(search)

        type_filter = QComboBox()
        type_filter.addItems(["All", "policy", "ic", "photo", "police_report", "claim", "other"])
        search_layout.addWidget(type_filter)

        upload_btn = QPushButton("+ Upload")
        upload_btn.clicked.connect(self._upload)
        search_layout.addWidget(upload_btn)
        layout.addLayout(search_layout)

        # Document table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["File", "Type", "Customer", "Tags", "Size", "Date"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self._refresh()

    def _refresh(self):
        from src.database.models import Document as DocModel
        docs = self.app.session.query(DocModel).order_by(DocModel.created_at.desc()).all()
        self.table.setRowCount(len(docs))
        for row, d in enumerate(docs):
            self.table.setItem(row, 0, QTableWidgetItem(d.filename))
            self.table.setItem(row, 1, QTableWidgetItem(d.doc_type))
            # Get customer name
            from src.database.models import Customer
            customer = self.app.session.query(Customer).filter(Customer.id == d.customer_id).first()
            self.table.setItem(row, 2, QTableWidgetItem(customer.name if customer else "Unknown"))
            tags_str = ", ".join(d.tags) if d.tags else ""
            self.table.setItem(row, 3, QTableWidgetItem(tags_str))
            size_str = f"{d.file_size / 1024:.1f} KB" if d.file_size else ""
            self.table.setItem(row, 4, QTableWidgetItem(size_str))
            self.table.setItem(row, 5, QTableWidgetItem(d.created_at.strftime("%Y-%m-%d") if d.created_at else ""))

    def _upload(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Document")
        if not file_path:
            return
        # Ask which customer
        customers = self.app.customer_repo.list_all()
        names = [c.name for c in customers]
        if not names:
            QMessageBox.warning(self, "No Customers", "Add a customer first.")
            return
        name, ok = QInputDialog.getItem(self, "Select Customer", "Customer:", names, 0, False)
        if not ok:
            return
        customer = next((c for c in customers if c.name == name), None)
        if customer:
            doc = self.app.document_vault.import_file(file_path, customer.id)
            if doc:
                self._refresh()


class CompaniesWidget(QWidget):
    """Insurance company management and portal adapters."""

    def __init__(self, app: InsureDeskWindow):
        super().__init__()
        self.app = app
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header row with title + Add button
        header = QHBoxLayout()
        title = QLabel("🌐  Insurance Companies")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1a1a2e;")
        header.addWidget(title)
        header.addStretch()

        self.add_btn = QPushButton("➕ Add Company")
        self.add_btn.clicked.connect(self._add_company)
        self.add_btn.setStyleSheet("""
            QPushButton { background: #1a1a2e; color: white; padding: 8px 20px;
                          border-radius: 6px; font-size: 13px; font-weight: bold; }
            QPushButton:hover { background: #16213e; }
        """)
        header.addWidget(self.add_btn)
        layout.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Company", "Short Name", "Website", "Adapter", "Status", "Last Sync"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self._refresh()

    def _refresh(self):
        companies = self.app.session.query(Company).order_by(Company.name).all()
        self.table.setRowCount(len(companies))
        for row, c in enumerate(companies):
            self.table.setItem(row, 0, QTableWidgetItem(c.name))
            self.table.setItem(row, 1, QTableWidgetItem(c.short_name))
            self.table.setItem(row, 2, QTableWidgetItem(c.portal_url or "—"))
            self.table.setItem(row, 3, QTableWidgetItem(c.adapter_name or "—"))
            status = "✅ Active" if c.is_active else "❌ Inactive"
            self.table.setItem(row, 4, QTableWidgetItem(status))
            sync = c.last_sync.strftime("%Y-%m-%d %H:%M") if c.last_sync else "Never"
            self.table.setItem(row, 5, QTableWidgetItem(sync))

    def _add_company(self):
        """Open dialog to add a new insurance company."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Insurance Company")
        dialog.setMinimumWidth(450)
        layout = QFormLayout(dialog)

        name_input = QLineEdit()
        name_input.setPlaceholderText("e.g. Great Eastern")
        layout.addRow("Company Name:", name_input)

        short_input = QLineEdit()
        short_input.setPlaceholderText("e.g. GE")
        layout.addRow("Short Name:", short_input)

        url_input = QLineEdit()
        url_input.setPlaceholderText("e.g. https://www.greateasternlife.com/my")
        layout.addRow("Official Website:", url_input)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        cancel_btn.setStyleSheet("padding: 6px 16px;")
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet("""
            QPushButton { background: #1a1a2e; color: white; padding: 6px 20px;
                          border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #16213e; }
        """)
        save_btn.clicked.connect(lambda: self._save_company(dialog, name_input, short_input, url_input))
        btn_layout.addWidget(save_btn)
        layout.addRow(btn_layout)

        dialog.exec()

    def _save_company(self, dialog, name_input, short_input, url_input):
        name = name_input.text().strip()
        short = short_input.text().strip()
        url = url_input.text().strip()

        if not name:
            QMessageBox.warning(dialog, "Missing Info", "Company name is required.")
            return
        if not short:
            QMessageBox.warning(dialog, "Missing Info", "Short name is required.")
            return

        # Check for duplicate
        existing = self.app.session.query(Company).filter(
            Company.short_name == short
        ).first()
        if existing:
            QMessageBox.warning(dialog, "Duplicate", f"Short name '{short}' already exists.")
            return

        company = Company(
            name=name,
            short_name=short,
            portal_url=url if url else None,
            is_active=True,
        )
        self.app.session.add(company)
        self.app.session.commit()
        self._refresh()
        dialog.accept()


class AssistantWidget(QWidget):
    """AI Assistant chat view with customer context."""

    def __init__(self, app: InsureDeskWindow):
        super().__init__()
        self.app = app
        self.current_customer_id = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"🤖  {app.assistant_name}")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1a1a2e;")
        layout.addWidget(title)

        # Chat area
        self.chat_area = QTextEdit()
        self.chat_area.setReadOnly(True)
        self.chat_area.setStyleSheet("""
            QTextEdit { background: #f5f5f5; border: 1px solid #ddd;
                        border-radius: 8px; padding: 10px;
                        font-size: 13px; }
        """)
        layout.addWidget(self.chat_area, 1)

        # Input area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText(f"Ask {app.assistant_name} something...")
        self.input_field.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.input_field)

        send_btn = QPushButton("Send")
        send_btn.setStyleSheet("""
            QPushButton { padding: 8px 20px; background: #e94560; color: white;
                          border: none; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #d63851; }
        """)
        send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(send_btn)
        layout.addLayout(input_layout)

    def _send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return

        self.chat_area.append(f"<b>You:</b> {text}")
        self.input_field.clear()

        # Check UIP-AI connection
        if not self.app.bridge_client.connected:
            self.chat_area.append(
                f"<b>{self.app.assistant_name}:</b> Not connected to UIP-AI. "
                "Go to Settings to connect."
            )
            return

        # Get customer context from the main window
        customer_id = self.current_customer_id
        customer_name = ""
        if customer_id:
            customer = self.app.customer_repo.get_by_id(customer_id)
            if customer:
                customer_name = customer.name

        # Include customer context in the message
        context_text = text
        if customer_name:
            context_text = f"[Customer: {customer_name}]\n{text}"

        # Send via bridge
        message = BridgeMessage(text=context_text, customer_id=customer_id)
        response = self.app.bridge_client.send_message(message)

        if response:
            self.chat_area.append(f"<b>{self.app.assistant_name}:</b> {response.text}")
        else:
            self.chat_area.append(
                f"<b>{self.app.assistant_name}:</b> Sorry, I couldn't reach UIP-AI."
            )


class SettingsWidget(QWidget):
    """Settings view with Portal Credential management."""

    PORTALS = [
        ("great_eastern", "Great Eastern", "🏛️"),
        ("allianz", "Allianz", "🔵"),
        ("aia", "AIA", "🔴"),
        ("etiqa", "Etiqa", "🟢"),
        ("tokio_marine", "Tokio Marine", "⚪"),
    ]

    def __init__(self, app: InsureDeskWindow, credential_service: CredentialService):
        super().__init__()
        self.app = app
        self.credential_service = credential_service
        # Cache company lookups: adapter_name → display name
        self._company_names: dict[str, str] = {}
        self._refresh_company_names()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Scroll area for all settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("⚙  Settings")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1a1a2e;")
        scroll_layout.addWidget(title)

        # ── Portal Credentials Vault ──
        cred_group = QGroupBox("🔑  Portal Credentials Vault")
        cred_group.setStyleSheet("""
            QGroupBox { font-size: 14px; font-weight: bold; border: 1px solid #e0e0e0;
                        border-radius: 8px; margin-top: 12px; padding-top: 24px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
        """)
        cred_layout = QVBoxLayout(cred_group)

        # Description
        desc = QLabel(
            "Store your insurance portal login credentials securely. "
            "Credentials are encrypted with AES-256-GCM before storage. "
            "The master key is kept in your operating system's secret store, "
            "not in the database."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-size: 11px; padding: 4px 0 12px;")
        cred_layout.addWidget(desc)

        # Refresh button
        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        self.cred_refresh_btn = QPushButton("🔄 Refresh")
        self.cred_refresh_btn.clicked.connect(self._refresh_credentials)
        self.cred_refresh_btn.setStyleSheet("""
            QPushButton { background: #f0f0f0; padding: 6px 16px; border-radius: 4px;
                          font-size: 11px; }
            QPushButton:hover { background: #e0e0e0; }
        """)
        refresh_row.addWidget(self.cred_refresh_btn)
        cred_layout.addLayout(refresh_row)

        # Credential cards container
        self.cred_cards = QVBoxLayout()
        cred_layout.addLayout(self.cred_cards)

        scroll_layout.addWidget(cred_group)

        # ── UIP-AI Connection ──
        conn_group = QGroupBox("UIP-AI Connection")
        conn_group.setStyleSheet("""
            QGroupBox { font-size: 14px; font-weight: bold; border: 1px solid #e0e0e0;
                        border-radius: 8px; margin-top: 12px; padding-top: 24px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
        """)
        conn_layout = QFormLayout(conn_group)

        self.url_input = QLineEdit("http://localhost:8000")
        conn_layout.addRow("Server URL:", self.url_input)

        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.Password)
        conn_layout.addRow("API Token:", self.token_input)

        conn_btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._connect)
        conn_btn_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self._disconnect)
        conn_btn_layout.addWidget(self.disconnect_btn)
        conn_layout.addRow(conn_btn_layout)

        self.conn_status = QLabel("Status: Not connected")
        conn_layout.addRow(self.conn_status)

        scroll_layout.addWidget(conn_group)

        # ── Assistant settings ──
        asst_group = QGroupBox("AI Assistant")
        asst_group.setStyleSheet("""
            QGroupBox { font-size: 14px; font-weight: bold; border: 1px solid #e0e0e0;
                        border-radius: 8px; margin-top: 12px; padding-top: 24px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
        """)
        asst_layout = QFormLayout(asst_group)

        self.assistant_name_input = QLineEdit(app.assistant_name)
        save_name_btn = QPushButton("Save Name")
        save_name_btn.clicked.connect(self._save_assistant_name)
        name_layout = QHBoxLayout()
        name_layout.addWidget(self.assistant_name_input)
        name_layout.addWidget(save_name_btn)
        asst_layout.addRow("Assistant Name:", name_layout)

        scroll_layout.addWidget(asst_group)

        # ── Browser settings ──
        browser_group = QGroupBox("Browser Automation")
        browser_group.setStyleSheet("""
            QGroupBox { font-size: 14px; font-weight: bold; border: 1px solid #e0e0e0;
                        border-radius: 8px; margin-top: 12px; padding-top: 24px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
        """)
        browser_layout = QFormLayout(browser_group)

        self.headless_check = QCheckBox("Run headless (no visible browser)")
        browser_layout.addRow(self.headless_check)

        self.slow_slider = QSpinBox()
        self.slow_slider.setRange(0, 2000)
        self.slow_slider.setValue(100)
        self.slow_slider.setSuffix(" ms")
        browser_layout.addRow("Slow Mo:", self.slow_slider)

        scroll_layout.addWidget(browser_group)

        # ── Integrations ──
        integrations_group = QGroupBox("🔌  Integrations")
        integrations_group.setStyleSheet("""
            QGroupBox { font-size: 14px; font-weight: bold; border: 1px solid #e0e0e0;
                        border-radius: 8px; margin-top: 12px; padding-top: 24px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
        """)
        integrations_layout = QVBoxLayout(integrations_group)

        # Overview
        self.integrations_status = QLabel("Loading...")
        self.integrations_status.setStyleSheet("color: #666; padding: 4px 0;")
        self.integrations_status.setWordWrap(True)
        integrations_layout.addWidget(self.integrations_status)

        # Available connectors
        avail_label = QLabel("Available Connectors:")
        avail_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        integrations_layout.addWidget(avail_label)

        self.connector_grid = QVBoxLayout()
        for conn in ConnectorRegistry.list_available():
            row = QHBoxLayout()
            name_label = QLabel(f"{conn['display_name']}  ({conn['type']})")
            name_label.setStyleSheet("color: #333;")
            row.addWidget(name_label)
            row.addStretch()
            connect_btn = QPushButton("Connect")
            connect_btn.setStyleSheet("""
                QPushButton { background: #1a73e8; color: white; padding: 4px 12px;
                              border-radius: 4px; font-size: 11px; }
                QPushButton:hover { background: #1557b0; }
            """)
            connect_btn.clicked.connect(lambda checked, p=conn["name"]: self._show_connect_dialog(p))
            row.addWidget(connect_btn)
            self.connector_grid.addLayout(row)

        integrations_layout.addLayout(self.connector_grid)

        # Connected integrations table
        conns_label = QLabel("Connected Systems:")
        conns_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        integrations_layout.addWidget(conns_label)

        self.connected_table = QTableWidget()
        self.connected_table.setColumnCount(4)
        self.connected_table.setHorizontalHeaderLabels(["Name", "Type", "Status", "Last Sync"])
        self.connected_table.horizontalHeader().setStretchLastSection(True)
        self.connected_table.setMaximumHeight(150)
        self.connected_table.setSelectionBehavior(QTableWidget.SelectRows)
        integrations_layout.addWidget(self.connected_table)

        refresh_int_btn = QPushButton("🔄 Refresh Integrations")
        refresh_int_btn.setStyleSheet("""
            QPushButton { background: #f0f0f0; color: #333; padding: 6px 16px;
                          border-radius: 4px; font-size: 11px; border: 1px solid #ddd; }
        """)
        refresh_int_btn.clicked.connect(self._refresh_integrations)
        integrations_layout.addWidget(refresh_int_btn)

        scroll_layout.addWidget(integrations_group)

        scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Load credential status
        self._refresh_credentials()

    def _refresh_company_names(self):
        """Rebuild the adapter_name → display name cache from DB companies."""
        self._company_names = {}
        try:
            from src.database.models import Company
            companies = self.app.session.query(Company).all()
            for c in companies:
                if c.adapter_name:
                    self._company_names[c.adapter_name.lower()] = c.name
                # Also index by short_name for flexibility
                self._company_names[c.short_name.lower()] = c.name
        except Exception:
            # Fallback if DB not ready
            pass

    def _portal_display_name(self, portal_key: str) -> str:
        """Get a display name for a portal key from the DB companies."""
        return self._company_names.get(portal_key.lower(), portal_key.replace("_", " ").title())

    def _refresh_credentials(self):
        """Refresh credential cards — only show portals with saved credentials."""
        # Clear existing cards
        while self.cred_cards.count():
            item = self.cred_cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Refresh company name cache
        self._refresh_company_names()

        # Get configured portals from credential service
        configured = self.credential_service.list_portals()

        if configured:
            for portal_key in configured:
                portal_name = self._portal_display_name(portal_key)
                card = self._build_portal_card(portal_key, portal_name, "🏛️", True)
                self.cred_cards.addWidget(card)
        else:
            # Empty state
            empty_label = QLabel("No portal credentials saved yet. Click '➕ Add New' below to get started.")
            empty_label.setStyleSheet("color: #999; font-size: 12px; padding: 12px;")
            empty_label.setWordWrap(True)
            self.cred_cards.addWidget(empty_label)

        # "Add New" card at the bottom
        add_card = self._build_add_credential_card()
        self.cred_cards.addWidget(add_card)

    def _build_portal_card(self, portal_key: str, portal_name: str,
                           icon: str, is_configured: bool) -> QWidget:
        """Build a single portal credential card."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame { background: white; border: 1px solid #e8e8e8;
                     border-radius: 8px; margin: 2px 0; }
            QFrame:hover { border-color: #1a73e8; }
        """)
        card.setFixedHeight(80)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)

        # Portal icon + name
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 24px;")
        layout.addWidget(icon_label)

        name_label = QLabel(portal_name)
        name_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        layout.addWidget(name_label)

        # Status badge
        status_label = QLabel("✅ Configured" if is_configured else "⬜ Not configured")
        status_label.setStyleSheet(
            f"font-size: 11px; color: {'#2e7d32' if is_configured else '#999'}; "
            f"background: {'#e8f5e9' if is_configured else '#f5f5f5'}; "
            f"padding: 2px 10px; border-radius: 10px;"
        )
        layout.addWidget(status_label)

        layout.addStretch()

        # Credentials list if configured
        if is_configured:
            creds = self.credential_service.list(portal=portal_key)
            for c in creds:
                acct_label = QLabel(f"📋 {c['account_name']}")
                acct_label.setStyleSheet("color: #666; font-size: 11px;")
                layout.addWidget(acct_label)
                if c.get("last_verified"):
                    verified = QLabel(f"✓ {c['last_verified'][:10]}")
                    verified.setStyleSheet("color: #888; font-size: 10px;")
                    layout.addWidget(verified)

        # Action buttons
        if is_configured:
            edit_btn = QPushButton("✏️ Edit")
            edit_btn.setStyleSheet("""
                QPushButton { background: #e3f2fd; color: #1565c0; padding: 4px 12px;
                              border-radius: 4px; font-size: 11px; border: none; }
                QPushButton:hover { background: #bbdefb; }
            """)
            edit_btn.clicked.connect(lambda checked, p=portal_key: self._edit_credentials(p))
            layout.addWidget(edit_btn)

            test_btn = QPushButton("🔍 Test")
            test_btn.setStyleSheet("""
                QPushButton { background: #e8f5e9; color: #2e7d32; padding: 4px 12px;
                              border-radius: 4px; font-size: 11px; border: none; }
                QPushButton:hover { background: #c8e6c9; }
            """)
            test_btn.clicked.connect(lambda checked, p=portal_key: self._test_credentials(p))
            layout.addWidget(test_btn)

            delete_btn = QPushButton("🗑️")
            delete_btn.setFixedWidth(32)
            delete_btn.setStyleSheet("""
                QPushButton { background: #fce4ec; color: #c62828; padding: 4px;
                              border-radius: 4px; font-size: 11px; border: none; }
                QPushButton:hover { background: #f8bbd0; }
            """)
            delete_btn.clicked.connect(lambda checked, p=portal_key: self._delete_credentials(p))
            layout.addWidget(delete_btn)
        else:
            add_btn = QPushButton("+ Add Credentials")
            add_btn.setStyleSheet("""
                QPushButton { background: #1a73e8; color: white; padding: 6px 16px;
                              border-radius: 4px; font-size: 11px; border: none; }
                QPushButton:hover { background: #1557b0; }
            """)
            add_btn.clicked.connect(lambda checked, p=portal_key, n=portal_name: self._add_credentials(p, n))
            layout.addWidget(add_btn)

        return card

    def _build_add_credential_card(self) -> QWidget:
        """Build a card with an 'Add New' button to add credentials for any company."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame { background: #f8f9ff; border: 2px dashed #c0c8e0;
                     border-radius: 8px; margin: 2px 0; }
            QFrame:hover { border-color: #1a73e8; background: #eef1ff; }
        """)
        card.setFixedHeight(60)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addStretch()

        add_btn = QPushButton("➕ Add New Portal Credential")
        add_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #1a73e8; padding: 8px 24px;
                          border-radius: 6px; font-size: 13px; font-weight: bold; border: none; }
            QPushButton:hover { background: rgba(26,115,232,0.08); }
        """)
        add_btn.clicked.connect(self._show_add_credential_dialog)
        layout.addWidget(add_btn)
        layout.addStretch()
        return card

    def _show_add_credential_dialog(self):
        """Show dialog to add credentials — pick a company from the full DB list."""
        self._refresh_company_names()

        dialog = QDialog(self)
        dialog.setWindowTitle("Add Portal Credential")
        dialog.setMinimumWidth(480)
        form = QFormLayout(dialog)

        # Company picker from DB
        company_combo = QComboBox()
        company_combo.setEditable(True)
        company_combo.setPlaceholderText("Search or select an insurance company...")
        try:
            from src.database.models import Company as Co
            companies = self.app.session.query(Co).order_by(Co.name).all()
            for c in companies:
                display = c.name
                if c.portal_url:
                    display += f" ({c.portal_url})"
                company_combo.addItem(display, c.adapter_name or c.short_name.lower())
        except Exception:
            # Fallback list
            for key in ["great_eastern", "allianz", "aia", "etiqa", "tokio_marine"]:
                company_combo.addItem(key.replace("_", " ").title(), key)
        form.addRow("Company:", company_combo)

        account_input = QLineEdit()
        account_input.setPlaceholderText("Default")
        form.addRow("Account Name:", account_input)

        username_input = QLineEdit()
        username_input.setPlaceholderText("Username / Email")
        form.addRow("Username:", username_input)

        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.Password)
        password_input.setPlaceholderText("Password")
        form.addRow("Password:", password_input)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        cancel_btn.setStyleSheet("padding: 6px 16px;")
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet("""
            QPushButton { background: #1a1a2e; color: white; padding: 6px 20px;
                          border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #16213e; }
        """)
        save_btn.clicked.connect(lambda: self._save_new_credential(
            dialog, company_combo, account_input, username_input, password_input))
        btn_layout.addWidget(save_btn)
        form.addRow(btn_layout)

        dialog.exec()

    def _save_new_credential(self, dialog, company_combo, account_input,
                             username_input, password_input):
        """Save a new credential from the add dialog."""
        portal_key = company_combo.currentData()
        portal_name = company_combo.currentText().split(" (")[0]  # Remove URL suffix
        account_name = account_input.text().strip() or "Default"
        username = username_input.text().strip()
        password = password_input.text().strip()

        if not portal_key:
            QMessageBox.warning(dialog, "Missing Info", "Please select a company.")
            return
        if not username or not password:
            QMessageBox.warning(dialog, "Missing Info", "Username and password are required.")
            return

        try:
            self.credential_service.store(
                portal=portal_key,
                account_name=account_name,
                username=username,
                password=password,
            )
            QMessageBox.information(
                self, "Saved",
                f"✅ {portal_name} credentials saved securely!"
            )
            self._refresh_credentials()
            dialog.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save credentials: {e}")

    def _add_credentials(self, portal_key: str, portal_name: str):
        """Show dialog to add credentials for a portal."""
        dialog = CredentialDialog(self, portal_key, portal_name)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            try:
                self.credential_service.store(
                    portal=portal_key,
                    account_name=data["account_name"],
                    username=data["username"],
                    password=data["password"],
                )
                QMessageBox.information(
                    self, "Saved",
                    f"✅ {portal_name} credentials saved securely!"
                )
                self._refresh_credentials()
            except Exception as e:
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to save credentials: {e}"
                )

    def _edit_credentials(self, portal_key: str):
        """Show dialog to edit credentials for a portal."""
        creds = self.credential_service.list(portal=portal_key)
        if not creds:
            return
        # Edit the first/default account
        c = creds[0]
        dialog = CredentialDialog(self, portal_key, portal_key, edit_mode=True)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            try:
                self.credential_service.store(
                    portal=portal_key,
                    account_name=c["account_name"],
                    username=data["username"],
                    password=data["password"],
                )
                QMessageBox.information(
                    self, "Updated",
                    f"✅ {portal_key} credentials updated!"
                )
                self._refresh_credentials()
            except Exception as e:
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to update credentials: {e}"
                )

    def _test_credentials(self, portal_key: str):
        """Test that credentials can be decrypted."""
        ok = self.credential_service.verify(portal_key)
        if ok:
            QMessageBox.information(
                self, "Verification",
                f"✅ {portal_key} credentials verified (decryption successful).\n\n"
                "Note: This does NOT test portal login — that requires "
                "connecting to the actual portal."
            )
        else:
            QMessageBox.warning(
                self, "Verification Failed",
                f"❌ Could not decrypt {portal_key} credentials.\n"
                "The master key may have changed or data is corrupted."
            )

    def _delete_credentials(self, portal_key: str):
        """Delete all credentials for a portal."""
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete all saved credentials for {portal_key}?\n\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            creds = self.credential_service.list(portal=portal_key)
            for c in creds:
                self.credential_service.delete(c["id"])
            self._refresh_credentials()
            QMessageBox.information(
                self, "Deleted",
                f"✅ {portal_key} credentials removed."
            )

    # ── Settings helpers (UIP-AI, Assistant, Integrations) ──

    def _connect(self):
        token = self.token_input.text().strip()
        if not token:
            QMessageBox.warning(self, "Error", "Please enter an API token.")
            return
        self.app.bridge_client.connect(token)
        self.app._update_connection_status()
        self.app._set_setting("uip_ai_token", token)
        saved_url = self.url_input.text().strip()
        self.app._set_setting("uip_ai_url", saved_url)
        self.conn_status.setText(f"Status: Connected to {saved_url}")
        QMessageBox.information(self, "Connected", "✅ Connected to UIP-AI successfully!")

    def _disconnect(self):
        self.app.bridge_client.disconnect()
        self.app._update_connection_status()
        self.app._set_setting("uip_ai_token", "")
        self.conn_status.setText("Status: Disconnected")
        QMessageBox.information(self, "Disconnected", "Disconnected from UIP-AI.")

    def _save_assistant_name(self):
        name = self.assistant_name_input.text().strip()
        if name:
            self.app.assistant_name = name
            self.app._set_setting("assistant_name", name)
            # Update window title/assistant view
            self.app.assistant_view.input_field.setPlaceholderText(f"Ask {name} something...")
            QMessageBox.information(self, "Saved", f"Assistant name changed to '{name}'")

    def _refresh_integrations(self):
        try:
            conns = self.app.integration_repo.list_all()
            self.integrations_status.setText(
                f"✅ Connected to {len(conns)} external system(s)."
            )
            self.connected_table.setRowCount(len(conns))
            for i, c in enumerate(conns):
                self.connected_table.setItem(i, 0, QTableWidgetItem(c.get("name", "?")))
                self.connected_table.setItem(i, 1, QTableWidgetItem(c.get("provider", "?")))
                self.connected_table.setItem(i, 2, QTableWidgetItem(c.get("status", "?")))
                self.connected_table.setItem(i, 3, QTableWidgetItem(
                    str(c.get("last_sync", ""))[:19]
                ))
        except Exception as e:
            self.integrations_status.setText(f"❌ Error loading integrations: {e}")

    def _show_connect_dialog(self, provider_name):
        dialog = IntegrationDialog(self, provider_name)
        if dialog.exec() == QDialog.Accepted:
            try:
                data = dialog.get_data()
                self.app.integration_service.create_connection(
                    name=dialog.connection_name.text() or f"{provider_name} Connection",
                    provider=data.provider,
                    credentials=data.credentials,
                )
                QMessageBox.information(
                    self, "Connected",
                    f"✅ {provider_name} connected successfully!"
                )
                self._refresh_integrations()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to connect: {e}")


class CredentialDialog(QDialog):
    """Dialog for entering portal credentials."""

    def __init__(self, parent=None, portal_key="", portal_name="", edit_mode=False):
        super().__init__(parent)
        self.setWindowTitle(f"{'Edit' if edit_mode else 'Add'} Credentials — {portal_name or portal_key}")
        self.setMinimumWidth(420)
        self.setMinimumHeight(320)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        form = QFormLayout()

        # Account name (hidden for single-account mode)
        self.account_input = QLineEdit("default")
        form.addRow("Account Name:", self.account_input)

        # Username
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("e.g. agent01@greateasternlife.com")
        form.addRow("Username / Email:", self.username_input)

        # Password
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Portal login password")
        form.addRow("Password:", self.password_input)

        # Show password toggle
        show_pw = QCheckBox("Show password")
        show_pw.toggled.connect(
            lambda checked: self.password_input.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        form.addRow(show_pw)

        main_layout.addLayout(form)

        # Push everything below to the bottom
        main_layout.addStretch()

        # Note
        note = QLabel(
            "🔒 Credentials will be encrypted before storage.\n"
            "The master key is stored in your OS secret store."
        )
        note.setStyleSheet("color: #666; font-size: 10px; padding: 4px 0;")
        note.setWordWrap(True)
        main_layout.addWidget(note)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        ok_btn.setText("Save Credentials")
        ok_btn.setStyleSheet(
            "QPushButton { background: #1976D2; color: white; font-weight: bold; "
            "padding: 8px 24px; border-radius: 4px; border: none; }"
            "QPushButton:hover { background: #1565C0; }"
        )
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        cancel_btn.setText("Cancel")
        cancel_btn.setStyleSheet("padding: 8px 24px;")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def get_data(self) -> dict:
        return {
            "account_name": self.account_input.text().strip() or "default",
            "username": self.username_input.text().strip(),
            "password": self.password_input.text(),
        }

class CustomerDialog(QDialog):
    """Dialog for adding/editing a customer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Customer")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        self.name_input = QLineEdit()
        layout.addRow("Name *:", self.name_input)

        self.phone_input = QLineEdit()
        layout.addRow("Phone:", self.phone_input)

        self.ic_input = QLineEdit()
        layout.addRow("IC Number:", self.ic_input)

        self.email_input = QLineEdit()
        layout.addRow("Email:", self.email_input)

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["English", "Bahasa Malaysia", "中文"])
        layout.addRow("Language:", self.lang_combo)

        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(80)
        layout.addRow("Notes:", self.notes_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_data(self) -> CustomerData:
        lang_map = {"English": "en", "Bahasa Malaysia": "ms", "中文": "zh"}
        return CustomerData(
            name=self.name_input.text().strip(),
            phone=self.phone_input.text().strip(),
            ic_number=self.ic_input.text().strip(),
            email=self.email_input.text().strip(),
            language=lang_map.get(self.lang_combo.currentText(), "en"),
            notes=self.notes_input.toPlainText().strip(),
        )


class PolicyDialog(QDialog):
    """Dialog for adding a policy."""

    def __init__(self, parent=None, company_names=None):
        super().__init__(parent)
        self.setWindowTitle("Add Policy")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        self.company_combo = QComboBox()
        if company_names:
            self.company_combo.addItems(company_names)
        layout.addRow("Company:", self.company_combo)

        self.policy_no_input = QLineEdit()
        layout.addRow("Policy # *:", self.policy_no_input)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["life", "general", "medical", "motor", "travel", "other"])
        layout.addRow("Type:", self.type_combo)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["active", "lapsed", "claim", "expired"])
        layout.addRow("Status:", self.status_combo)

        self.premium_input = QLineEdit()
        layout.addRow("Premium:", self.premium_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_data(self) -> PolicyData:
        return PolicyData(
            company=self.company_combo.currentText(),
            policy_number=self.policy_no_input.text().strip(),
            policy_type=self.type_combo.currentText(),
            status=self.status_combo.currentText(),
            premium=self.premium_input.text().strip(),
        )
# ── PI-16: Team Widget ──────────────────────────────────────────

class TeamWidget(QWidget):
    """🏢 Team — Agency Collaboration workspace (PI-16).

    Features:
    - Team Overview (manager dashboard)
    - Members management (add/remove, roles)
    - Assignment and workload balancing
    - Knowledge sharing
    - Marry assistant integration (agent + manager mode)
    """

    def __init__(self, app: InsureDeskWindow):
        super().__init__()
        self.app = app
        self.current_team_id = None
        self.user_role = "manager"
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(20, 20, 20, 20)
        header_row = QHBoxLayout()
        title = QLabel("🏢  Team")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1a1a2e;")
        header_row.addWidget(title)
        header_row.addStretch()
        self.role_label = QLabel("👤 Role: Manager")
        self.role_label.setStyleSheet("color: #666; font-size: 12px; padding: 4px 12px; background: #f0f0f0; border-radius: 10px;")
        header_row.addWidget(self.role_label)
        self._main_layout.addLayout(header_row)
        subtitle = QLabel("Team intelligence, assignment management, and knowledge sharing. Ask Marry your daily plan.")
        subtitle.setStyleSheet("color: #888; font-size: 12px; margin-bottom: 12px;")
        subtitle.setWordWrap(True)
        self._main_layout.addWidget(subtitle)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; }
            QTabBar::tab { padding: 8px 16px; font-size: 13px; }
            QTabBar::tab:selected { font-weight: bold; color: #e94560; }
        """)
        self._main_layout.addWidget(self.tabs)
        self.overview_tab = self._build_overview_tab()
        self.tabs.addTab(self.overview_tab, "📊  Overview")
        self.members_tab = self._build_members_tab()
        self.tabs.addTab(self.members_tab, "👥  Members")
        self.assignments_tab = self._build_assignments_tab()
        self.tabs.addTab(self.assignments_tab, "📋  Assignments")
        self.knowledge_tab = self._build_knowledge_tab()
        self.tabs.addTab(self.knowledge_tab, "📚  Knowledge")
        self.marry_tab = self._build_marry_tab()
        self.tabs.addTab(self.marry_tab, "🤖  Ask Marry")
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("""
            QPushButton { background: #1a1a2e; color: white; padding: 8px 20px;
                          border-radius: 6px; font-weight: bold; }
            QPushButton:hover { background: #0f3460; }
        """)
        refresh_btn.clicked.connect(self._load_data)
        self._main_layout.addWidget(refresh_btn)

    def _build_overview_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        cards = QHBoxLayout()
        self.member_card = self._make_card("👥 Members", "\u2014", "#1a73e8")
        self.customer_card = self._make_card("👤 Customers", "\u2014", "#34a853")
        self.task_card = self._make_card("📋 Tasks", "\u2014", "#fbbc04")
        self.rate_card = self._make_card("✅ Renewal Rate", "\u2014", "#e94560")
        cards.addWidget(self.member_card)
        cards.addWidget(self.customer_card)
        cards.addWidget(self.task_card)
        cards.addWidget(self.rate_card)
        layout.addLayout(cards)
        attention_group = QGroupBox("🚨  Attention")
        attention_group.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 14px; padding-top: 12px;
                        border: 1px solid #e0e0e0; border-radius: 8px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
        """)
        attention_layout = QVBoxLayout(attention_group)
        self.attention_label = QLabel("No items requiring attention.")
        self.attention_label.setStyleSheet("color: #888; padding: 8px;")
        self.attention_label.setWordWrap(True)
        attention_layout.addWidget(self.attention_label)
        layout.addWidget(attention_group)
        perf_group = QGroupBox("📈  Team Performance")
        perf_group.setStyleSheet("""
            QGroupBox { font-weight: bold; font-size: 14px; padding-top: 12px;
                        border: 1px solid #e0e0e0; border-radius: 8px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
        """)
        perf_layout = QVBoxLayout(perf_group)
        self.perf_label = QLabel("Loading team metrics...")
        self.perf_label.setStyleSheet("color: #555; padding: 8px;")
        self.perf_label.setWordWrap(True)
        perf_layout.addWidget(self.perf_label)
        layout.addWidget(perf_group)
        layout.addStretch()
        return tab

    def _build_members_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        self.member_name_input = QLineEdit()
        self.member_name_input.setPlaceholderText("Member name...")
        controls.addWidget(self.member_name_input)
        self.member_role_combo = QComboBox()
        self.member_role_combo.addItems(["agent", "manager", "admin"])
        controls.addWidget(QLabel("Role:"))
        controls.addWidget(self.member_role_combo)
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_member)
        controls.addWidget(add_btn)
        layout.addLayout(controls)
        self.member_table = QTableWidget()
        self.member_table.setColumnCount(6)
        self.member_table.setHorizontalHeaderLabels(["Name", "Role", "Email", "Specialties", "Active Tasks", "Actions"])
        self.member_table.horizontalHeader().setStretchLastSection(False)
        self.member_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.member_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.member_table)
        return tab

    def _build_assignments_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        assign_label = QLabel("Assign to:")
        controls.addWidget(assign_label)
        self.assign_agent_combo = QComboBox()
        controls.addWidget(self.assign_agent_combo)
        controls.addStretch()
        balance_btn = QPushButton("⚖  Check Balance")
        balance_btn.clicked.connect(self._check_workload_balance)
        controls.addWidget(balance_btn)
        layout.addLayout(controls)
        self.workload_label = QLabel("Team workload analysis will appear here.")
        self.workload_label.setStyleSheet("color: #666; padding: 8px;")
        self.workload_label.setWordWrap(True)
        layout.addWidget(self.workload_label)
        task_group = QGroupBox("Team Tasks")
        task_layout = QVBoxLayout(task_group)
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(6)
        self.task_table.setHorizontalHeaderLabels(["Title", "Type", "Priority", "Assignee", "Status", "Due"])
        self.task_table.horizontalHeader().setStretchLastSection(False)
        self.task_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        task_layout.addWidget(self.task_table)
        layout.addWidget(task_group)
        return tab

    def _build_knowledge_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        self.knowledge_search = QLineEdit()
        self.knowledge_search.setPlaceholderText("Search knowledge base...")
        controls.addWidget(self.knowledge_search)
        search_btn = QPushButton("🔍 Search")
        search_btn.clicked.connect(self._search_knowledge)
        controls.addWidget(search_btn)
        add_k_btn = QPushButton("+ Add Entry")
        add_k_btn.clicked.connect(self._add_knowledge)
        controls.addWidget(add_k_btn)
        layout.addLayout(controls)
        self.knowledge_list = QTableWidget()
        self.knowledge_list.setColumnCount(4)
        self.knowledge_list.setHorizontalHeaderLabels(["Title", "Tags", "Visibility", "Updated"])
        self.knowledge_list.horizontalHeader().setStretchLastSection(False)
        self.knowledge_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.knowledge_list.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.knowledge_list)
        preview_group = QGroupBox("Content Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.knowledge_preview = QLabel("Select an entry to preview.")
        self.knowledge_preview.setStyleSheet("color: #666; padding: 8px;")
        self.knowledge_preview.setWordWrap(True)
        preview_layout.addWidget(self.knowledge_preview)
        layout.addWidget(preview_group)
        return tab

    def _build_marry_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))
        self.marry_mode = QComboBox()
        self.marry_mode.addItems(["Agent Mode", "Manager Mode"])
        mode_layout.addWidget(self.marry_mode)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        self.mode_desc = QLabel("Agent: task plan. Manager: team performance.")
        self.mode_desc.setStyleSheet("color: #888; font-size: 12px; padding: 8px; background: #f9f9f9; border-radius: 6px;")
        self.mode_desc.setWordWrap(True)
        layout.addWidget(self.mode_desc)
        query_layout = QHBoxLayout()
        self.marry_query = QLineEdit()
        self.marry_query.setPlaceholderText("Ask Marry about your team...")
        query_layout.addWidget(self.marry_query)
        ask_btn = QPushButton("Ask Marry")
        ask_btn.setStyleSheet("""
            QPushButton { background: #e94560; color: white; padding: 8px 20px;
                          border-radius: 6px; font-weight: bold; }
            QPushButton:hover { background: #d6415a; }
        """)
        ask_btn.clicked.connect(self._ask_marry)
        query_layout.addWidget(ask_btn)
        layout.addLayout(query_layout)
        quick_row = QHBoxLayout()
        for q in ["What should I do today?", "How is my team?", "Who needs help?"]:
            btn = QPushButton(q)
            btn.setStyleSheet("""
                QPushButton { background: #f0f0f0; color: #333; padding: 6px 12px;
                              border-radius: 14px; font-size: 11px; border: 1px solid #ddd; }
                QPushButton:hover { background: #e0e0e0; }
            """)
            btn.clicked.connect(lambda checked, q=q: self._quick_ask(q))
            quick_row.addWidget(btn)
        quick_row.addStretch()
        layout.addLayout(quick_row)
        self.marry_response = QLabel("Ask Marry a question to get started.")
        self.marry_response.setStyleSheet("""
            QLabel { background: #f5f5f5; border: 1px solid #e0e0e0;
                     border-radius: 8px; padding: 16px; color: #333;
                     font-size: 13px; margin-top: 12px; }
        """)
        self.marry_response.setWordWrap(True)
        self.marry_response.setMinimumHeight(150)
        layout.addWidget(self.marry_response)
        layout.addStretch()
        return tab

    def _make_card(self, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{ background: white; border: 1px solid #e0e0e0;
                      border-radius: 10px; border-top: 3px solid {color}; }}
        """)
        card.setMinimumHeight(100)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 12px; color: #888;")
        cl.addWidget(title_lbl)
        value_lbl = QLabel(value)
        value_lbl.setObjectName(f"card_{title.lower().replace(' ', '_')}")
        value_lbl.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color};")
        cl.addWidget(value_lbl)
        cl.addStretch()
        return card

    def _load_data(self):
        teams = self.app.team_repo.list_all()
        if not teams:
            team_data = TeamData(name="My Agency", description="Default agency team")
            self.app.team_repo.create(team_data)
            teams = self.app.team_repo.list_all()
        if not teams:
            self.attention_label.setText("⚠ No teams found.")
            return
        self.current_team_id = teams[0].id
        self._refresh_overview()
        self._refresh_members()
        self._refresh_assignments()
        self._refresh_knowledge()

    def _refresh_overview(self):
        if not self.current_team_id:
            return
        overview = self.app.team_dashboard.get_overview(self.current_team_id)
        workload = self.app.team_repo.get_workload_balance(self.current_team_id)
        for child in self.member_card.findChildren(QLabel):
            if child.objectName() == "card_members":
                child.setText(str(overview["total_members"]))
        for child in self.customer_card.findChildren(QLabel):
            if child.objectName() == "card_customers":
                child.setText(str(overview["total_customers"]))
        for child in self.task_card.findChildren(QLabel):
            if child.objectName() == "card_tasks":
                child.setText(str(overview["pending_tasks"] + overview["in_progress_tasks"]))
        for child in self.rate_card.findChildren(QLabel):
            if child.objectName() == "card_renewal_rate":
                child.setText(f"{overview['renewal_rate']}%")
        items = []
        if overview.get("needs_support", {}).get("name"):
            ns = overview["needs_support"]
            items.append(f"🔴 {ns['name']} has {ns['pending']} pending tasks")
        if not workload.get("balanced", True):
            items.append(f"⚠ Workload imbalance")
        self.attention_label.setText("\n".join(items) if items else "✅ Team running smoothly.")
        perf = [f"🏆 Top: {overview['top_performer'].get('name', 'N/A')} ({overview['top_performer'].get('completed', 0)})"]
        perf.append(f"📊 Tasks: {overview['total_tasks']} ({overview['pending_tasks']}p/{overview['in_progress_tasks']}a/{overview['completed_tasks']}d)")
        self.perf_label.setText("\n".join(perf))

    def _refresh_members(self):
        if not self.current_team_id:
            return
        members = self.app.team_repo.list_members(self.current_team_id)
        workloads = {w["member_id"]: w["active_tasks"] for w in self.app.team_repo.get_workload(self.current_team_id)}
        self.member_table.setRowCount(len(members))
        for i, m in enumerate(members):
            self.member_table.setItem(i, 0, QTableWidgetItem(m.name))
            self.member_table.setItem(i, 1, QTableWidgetItem(m.role))
            self.member_table.setItem(i, 2, QTableWidgetItem(m.email))
            self.member_table.setItem(i, 3, QTableWidgetItem(", ".join(m.specialties)))
            self.member_table.setItem(i, 4, QTableWidgetItem(str(workloads.get(m.id, 0))))
            remove_btn = QPushButton("✕")
            remove_btn.setFixedSize(30, 30)
            remove_btn.setStyleSheet("background: #ff4444; color: white; border-radius: 15px;")
            remove_btn.clicked.connect(lambda checked, mid=m.id: self._remove_member(mid))
            self.member_table.setCellWidget(i, 5, remove_btn)
        self.assign_agent_combo.clear()
        for m in members:
            if m.role in ("agent", "manager"):
                self.assign_agent_combo.addItem(f"{m.name} ({m.role})", m.id)

    def _refresh_assignments(self):
        if not self.current_team_id:
            return
        tasks = self.app.team_repo.list_tasks(self.current_team_id)
        members = {m.id: m.name for m in self.app.team_repo.list_members(self.current_team_id)}
        self.task_table.setRowCount(len(tasks))
        for i, t in enumerate(tasks):
            self.task_table.setItem(i, 0, QTableWidgetItem(t.title))
            self.task_table.setItem(i, 1, QTableWidgetItem(t.task_type))
            self.task_table.setItem(i, 2, QTableWidgetItem(t.priority))
            self.task_table.setItem(i, 3, QTableWidgetItem(members.get(t.assignee_id, "Unassigned")))
            self.task_table.setItem(i, 4, QTableWidgetItem(t.status))
            self.task_table.setItem(i, 5, QTableWidgetItem(t.due_date[:10] if t.due_date else ""))
        balance = self.app.team_repo.get_workload_balance(self.current_team_id)
        self.workload_label.setText(balance.get("message", ""))

    def _refresh_knowledge(self):
        if not self.current_team_id:
            return
        entries = self.app.knowledge_repo.search(self.current_team_id)
        self.knowledge_list.setRowCount(len(entries))
        for i, e in enumerate(entries):
            self.knowledge_list.setItem(i, 0, QTableWidgetItem(e.title))
            self.knowledge_list.setItem(i, 1, QTableWidgetItem(", ".join(e.tags)))
            self.knowledge_list.setItem(i, 2, QTableWidgetItem(e.visibility))
            self.knowledge_list.setItem(i, 3, QTableWidgetItem(e.updated_at[:16] if e.updated_at else ""))

    def _add_member(self):
        if not self.current_team_id:
            return
        name = self.member_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Input Required", "Please enter a member name.")
            return
        data = TeamMemberData(team_id=self.current_team_id, name=name, role=self.member_role_combo.currentText())
        self.app.team_repo.add_member(data)
        self.member_name_input.clear()
        self._load_data()

    def _remove_member(self, member_id):
        if QMessageBox.question(self, "Confirm", "Remove this member?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.app.team_repo.remove_member(member_id)
            self._load_data()

    def _check_workload_balance(self):
        if not self.current_team_id:
            return
        workloads = self.app.team_repo.get_workload(self.current_team_id)
        lines = ["⚖ Workload Summary:", ""]
        for w in workloads:
            indicator = "🔴" if w["active_tasks"] >= 5 else "🟡" if w["active_tasks"] >= 3 else "🟢"
            lines.append(f"  {indicator} {w['name']} ({w['role']}) \u2014 {w['active_tasks']} active")
        balance = self.app.team_repo.get_workload_balance(self.current_team_id)
        lines.append("")
        lines.append(f"📊 Balance: {'✅ Balanced' if balance.get('balanced') else '⚠ ' + balance.get('message', '')}")
        self.workload_label.setText("\n".join(lines))

    def _search_knowledge(self):
        if not self.current_team_id:
            return
        query = self.knowledge_search.text().strip()
        entries = self.app.knowledge_repo.search(self.current_team_id, query)
        self.knowledge_list.setRowCount(len(entries))
        for i, e in enumerate(entries):
            self.knowledge_list.setItem(i, 0, QTableWidgetItem(e.title))
            self.knowledge_list.setItem(i, 1, QTableWidgetItem(", ".join(e.tags)))
            self.knowledge_list.setItem(i, 2, QTableWidgetItem(e.visibility))
            self.knowledge_list.setItem(i, 3, QTableWidgetItem(e.updated_at[:16] if e.updated_at else ""))
        self.knowledge_list.clicked.connect(self._show_knowledge_preview)

    def _show_knowledge_preview(self, index):
        row = index.row()
        entries = self.app.knowledge_repo.search(self.current_team_id)
        if row < len(entries):
            e = entries[row]
            self.knowledge_preview.setText(f"**{e.title}**\n\n{e.content[:500]}")

    def _add_knowledge(self):
        dialog = KnowledgeDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            data.team_id = self.current_team_id
            self.app.knowledge_repo.create(data)
            self._refresh_knowledge()

    def _ask_marry(self):
        question = self.marry_query.text().strip()
        if not question:
            return
        self._process_marry_question(question)

    def _quick_ask(self, question):
        self.marry_query.setText(question)
        self._process_marry_question(question)

    def _process_marry_question(self, question):
        self.marry_response.setText("🤔 Thinking...")
        QApplication.processEvents()
        mode = self.marry_mode.currentText()
        if "Manager" in mode:
            response = self._answer_manager_question(question)
        else:
            response = self._answer_agent_question(question)
        if self.app.bridge_client.connected and self.current_team_id:
            try:
                ai_resp = self.app.bridge_client.query_team_performance(team_id=self.current_team_id, question=question)
                if ai_resp and "text" in ai_resp:
                    response += f"\n\n🤖 Marry (AI):\n{ai_resp['text']}"
            except Exception:
                pass
        self.marry_response.setText(response)

    def _answer_agent_question(self, question):
        if not self.current_team_id:
            return "⚠ No team configured."
        members = self.app.team_repo.list_members(self.current_team_id)
        agents = [m for m in members if m.role in ("agent", "manager") and m.is_active]
        if not agents:
            return "⚠ No active agents found."
        agent = agents[0]
        d = self.app.team_dashboard.get_agent_dashboard(agent.id)
        lines = [f"👋 Good day, {agent.name}!", ""]
        if d["total_pending"] == 0:
            lines.append("✅ No pending tasks.")
        else:
            lines.append(f"📋 You have {d['total_pending']} tasks:")
            for task in d["tasks"][:5]:
                due = f" (due: {task['due_date'][:10]})" if task['due_date'] else ""
                lines.append(f"  \u2022 {task['title']} [{task['priority']}]{due}")
        return "\n".join(lines)

    def _answer_manager_question(self, question):
        if not self.current_team_id:
            return "⚠ No team configured."
        o = self.app.team_dashboard.get_overview(self.current_team_id)
        wl = self.app.team_repo.get_workload_balance(self.current_team_id)
        lines = ["📊 Team Performance", ""]
        lines.append(f"👥 {o['agents']} agents, {o['managers']} managers")
        lines.append(f"👤 Customers: {o['total_customers']}")
        lines.append(f"📋 Tasks: {o['total_tasks']} ({o['pending_tasks']}p/{o['in_progress_tasks']}a/{o['completed_tasks']}d)")
        lines.append(f"✅ Renewal Rate: {o['renewal_rate']}%")
        if o.get("top_performer", {}).get("name"):
            lines.append(f"🏆 Top: {o['top_performer']['name']} ({o['top_performer']['completed']})")
        if not wl.get("balanced", True):
            lines.append(f"⚠ {wl.get('message', '')}")
        return "\n".join(lines)


class KnowledgeDialog(QDialog):
    """Dialog for adding a knowledge entry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Knowledge Entry")
        self.setMinimumWidth(500)
        layout = QFormLayout(self)
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Entry title...")
        layout.addRow("Title *:", self.title_input)
        self.content_input = QTextEdit()
        self.content_input.setPlaceholderText("Write your knowledge content here...")
        self.content_input.setMinimumHeight(200)
        layout.addRow("Content:", self.content_input)
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("Comma-separated tags")
        layout.addRow("Tags:", self.tags_input)
        self.visibility_combo = QComboBox()
        self.visibility_combo.addItems(["team", "public"])
        layout.addRow("Visibility:", self.visibility_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_data(self):
        from src.teams.repository import KnowledgeEntryData
        tags = [t.strip() for t in self.tags_input.text().split(",") if t.strip()]
        return KnowledgeEntryData(
            title=self.title_input.text().strip(),
            content=self.content_input.toPlainText().strip(),
            tags=tags,
            visibility=self.visibility_combo.currentText(),
        )

# ── PI-17: Integration Dialog ──────────────────────────────────

class IntegrationDialog(QDialog):
    """Dialog for configuring an external integration."""

    def __init__(self, parent=None, provider: str = ""):
        super().__init__(parent)
        self.provider = provider
        self.setWindowTitle(f"Connect {provider.replace('_', ' ').title()}")
        self.setMinimumWidth(450)
        layout = QFormLayout(self)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(f"My {provider.replace('_', ' ').title()}")
        layout.addRow("Connection Name:", self.name_input)

        # Provider-specific fields
        if provider == "csv":
            self.path_input = QLineEdit()
            self.path_input.setPlaceholderText("/path/to/customers.csv")
            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(self._browse_csv)
            path_layout = QHBoxLayout()
            path_layout.addWidget(self.path_input)
            path_layout.addWidget(browse_btn)
            layout.addRow("CSV File Path:", path_layout)
            self.field_delimiter = QLineEdit(",")
            layout.addRow("Delimiter:", self.field_delimiter)
        elif provider == "google_sheets":
            self.sheet_id_input = QLineEdit()
            self.sheet_id_input.setPlaceholderText("Google Sheet ID")
            layout.addRow("Sheet ID:", self.sheet_id_input)
        elif provider == "google_calendar":
            self.calendar_id_input = QLineEdit()
            self.calendar_id_input.setPlaceholderText("primary")
            layout.addRow("Calendar ID:", self.calendar_id_input)
        else:
            self.config_input = QTextEdit()
            self.config_input.setPlaceholderText("JSON config...")
            self.config_input.setMaximumHeight(100)
            layout.addRow("Config (JSON):", self.config_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _browse_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv);;All Files (*)"
        )
        if file_path:
            self.path_input.setText(file_path)

    def get_data(self) -> dict:
        data = {"name": self.name_input.text().strip() or self.provider}
        if self.provider == "csv":
            data["credentials_ref"] = self.path_input.text().strip()
            data["config"] = {"delimiter": self.field_delimiter.text().strip()}
        elif self.provider == "google_sheets":
            data["config"] = {"sheet_id": self.sheet_id_input.text().strip()}
        elif self.provider == "google_calendar":
            data["config"] = {"calendar_id": self.calendar_id_input.text().strip()}
        return data

# ── PI-17: Integration Dialog ──────────────────────────────────

class IntegrationDialog(QDialog):
    """Dialog for configuring an external integration."""

    def __init__(self, parent=None, provider: str = ""):
        super().__init__(parent)
        self.provider = provider
        self.setWindowTitle(f"Connect {provider.replace('_', ' ').title()}")
        self.setMinimumWidth(450)
        layout = QFormLayout(self)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(f"My {provider.replace('_', ' ').title()}")
        layout.addRow("Connection Name:", self.name_input)

        # Provider-specific fields
        if provider == "csv":
            self.path_input = QLineEdit()
            self.path_input.setPlaceholderText("/path/to/customers.csv")
            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(self._browse_csv)
            path_layout = QHBoxLayout()
            path_layout.addWidget(self.path_input)
            path_layout.addWidget(browse_btn)
            layout.addRow("CSV File Path:", path_layout)
            self.field_delimiter = QLineEdit(",")
            layout.addRow("Delimiter:", self.field_delimiter)
        elif provider == "google_sheets":
            self.sheet_id_input = QLineEdit()
            self.sheet_id_input.setPlaceholderText("Google Sheet ID")
            layout.addRow("Sheet ID:", self.sheet_id_input)
        elif provider == "google_calendar":
            self.calendar_id_input = QLineEdit()
            self.calendar_id_input.setPlaceholderText("primary")
            layout.addRow("Calendar ID:", self.calendar_id_input)
        else:
            self.config_input = QTextEdit()
            self.config_input.setPlaceholderText("JSON config...")
            self.config_input.setMaximumHeight(100)
            layout.addRow("Config (JSON):", self.config_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _browse_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv);;All Files (*)"
        )
        if file_path:
            self.path_input.setText(file_path)

    def get_data(self) -> dict:
        data = {"name": self.name_input.text().strip() or self.provider}
        if self.provider == "csv":
            data["credentials_ref"] = self.path_input.text().strip()
            data["config"] = {"delimiter": self.field_delimiter.text().strip()}
        elif self.provider == "google_sheets":
            data["config"] = {"sheet_id": self.sheet_id_input.text().strip()}
        elif self.provider == "google_calendar":
            data["config"] = {"calendar_id": self.calendar_id_input.text().strip()}
        return data
