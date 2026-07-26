#!/usr/bin/env python3
"""InsureDesk — Insurance Agent's AI-Powered Desktop Workspace.

Usage:
    python main.py
    
Or after install:
    insuredesk
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.desktop.app import InsureDeskWindow
from PySide6.QtWidgets import QApplication


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("InsureDesk")
    app.setOrganizationName("UIP-AI")

    # Set global stylesheet
    app.setStyleSheet("""
        QMainWindow { background: #fafafa; }
        QTableWidget { background: white; border: 1px solid #e0e0e0; 
                       border-radius: 4px; gridline-color: #f0f0f0; }
        QTableWidget::item { padding: 6px; }
        QHeaderView::section { background: #f5f5f5; padding: 8px; 
                               border: none; font-weight: bold; }
        QLineEdit { padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        QTextEdit { padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        QComboBox { padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        QGroupBox { font-size: 14px; font-weight: bold; 
                    border: 1px solid #e0e0e0; border-radius: 8px; 
                    margin-top: 10px; padding-top: 20px; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; 
                           padding: 4px 10px; }
    """)

    window = InsureDeskWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
