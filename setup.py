"""InsureDesk — Package setup for PyInstaller."""
from __future__ import annotations

import os
from setuptools import setup, find_packages

HERE = os.path.dirname(os.path.abspath(__file__))


def get_version() -> str:
    version_file = os.path.join(HERE, "build", "version.txt")
    if os.path.exists(version_file):
        with open(version_file) as f:
            return f.read().strip()
    return "1.0.0"


setup(
    name="insuredesk",
    version=get_version(),
    description="InsureDesk — Insurance Agent's AI-Powered Desktop Workspace",
    author="UIP-AI",
    packages=find_packages(include=["src", "src.*"]),
    include_package_data=True,
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "insuredesk=main:main",
        ],
    },
    install_requires=[
        "PySide6>=6.5",
        "playwright>=1.40",
        "requests>=2.31",
        "pyyaml>=6.0",
        "cryptography>=41.0",
        "keyring>=24.0",
        "sqlalchemy>=2.0",
        "alembic>=1.12",
        "python-dateutil>=2.8",
    ],
)
