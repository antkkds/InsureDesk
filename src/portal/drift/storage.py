"""InsureDesk — Portal Drift Detection: Baseline Storage.

Stores and retrieves baseline snapshots as JSON files.
Each portal gets its own baseline file, versioned by timestamp.
"""
from __future__ import annotations

import os
import json
import logging
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from src.portal.drift.models import BaselineSnapshot
from src.portal.drift.exceptions import BaselineNotFoundError, StorageError

logger = logging.getLogger("insuredesk.drift.storage")

# Default storage directory relative to project root
DEFAULT_STORAGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "baselines"


class BaselineStorage:
    """Persistent storage for portal baseline snapshots.

    Stores snapshots as JSON files in a configurable directory.
    Each portal has one current baseline; historical baselines
    are kept with timestamp suffixes.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self._storage_dir = Path(storage_dir or DEFAULT_STORAGE_DIR)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _portal_path(self, portal_id: str) -> Path:
        return self._storage_dir / f"{portal_id}_baseline.json"

    def _portal_history_path(self, portal_id: str) -> Path:
        return self._storage_dir / f"{portal_id}_history"

    def save_baseline(self, snapshot: BaselineSnapshot) -> str:
        """Save a baseline snapshot. Returns the file path."""
        path = self._portal_path(snapshot.portal_id)
        try:
            data = snapshot.to_dict()
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Saved baseline for {snapshot.portal_id} ({snapshot.selector_count} selectors)")
            return str(path)
        except (IOError, OSError) as e:
            raise StorageError(f"Failed to save baseline: {e}")

    def load_baseline(self, portal_id: str) -> BaselineSnapshot:
        """Load the current baseline for a portal.

        Raises:
            BaselineNotFoundError: If no baseline exists.
        """
        path = self._portal_path(portal_id)
        if not path.exists():
            raise BaselineNotFoundError(portal_id)
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return BaselineSnapshot.from_dict(data)
        except (json.JSONDecodeError, IOError) as e:
            raise StorageError(f"Failed to load baseline: {e}")

    def has_baseline(self, portal_id: str) -> bool:
        """Check if a baseline exists for the portal."""
        return self._portal_path(portal_id).exists()

    def list_baselines(self) -> List[str]:
        """List all portal IDs with stored baselines."""
        result = []
        for f in self._storage_dir.glob("*_baseline.json"):
            portal_id = f.stem.replace("_baseline", "")
            result.append(portal_id)
        return sorted(result)

    def delete_baseline(self, portal_id: str) -> bool:
        """Delete the baseline for a portal."""
        path = self._portal_path(portal_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def get_stats(self) -> dict:
        """Get storage statistics."""
        total = 0
        portals = []
        for f in self._storage_dir.glob("*_baseline.json"):
            total += f.stat().st_size
            portal_id = f.stem.replace("_baseline", "")
            portals.append(portal_id)
        return {
            "total_baselines": len(portals),
            "total_size_bytes": total,
            "portals": sorted(portals),
            "storage_dir": str(self._storage_dir),
        }
