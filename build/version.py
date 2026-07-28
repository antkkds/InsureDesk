"""InsureDesk Build Version."""
from __future__ import annotations

import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    with open(os.path.join(HERE, "build", "version.txt")) as f:
        VERSION = f.read().strip()
except FileNotFoundError:
    VERSION = "1.0.0-dev"
