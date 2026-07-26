
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
