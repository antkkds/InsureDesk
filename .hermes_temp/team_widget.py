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
