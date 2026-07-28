"""InsureDesk — Portal Drift Detection: Core Detector.

Compares current portal state against a baseline snapshot
and generates DriftEvents for every detected change.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Dict, List, Optional, Tuple

from src.portal.drift.models import (
    BaselineSnapshot, BaselineSelector,
    DriftEvent, DriftReport,
    DriftType, DriftSeverity,
)
from src.portal.drift.baseline import BaselineRecorder
from src.portal.drift.storage import BaselineStorage
from src.portal.drift.exceptions import BaselineNotFoundError
from src.portal.mapping import load_portal_mapping, get_selector

logger = logging.getLogger("insuredesk.drift.detector")


class DriftDetector:
    """Detects UI drift by comparing current portal state against baseline.

    Usage:
        detector = DriftDetector()
        report = detector.detect("great_eastern")
        print(report.health_score)
    """

    def __init__(self, recorder: Optional[BaselineRecorder] = None,
                 storage: Optional[BaselineStorage] = None):
        self._recorder = recorder or BaselineRecorder(storage=storage)
        self._storage = storage or BaselineStorage()

    def detect(self, portal_id: str) -> DriftReport:
        """Run full drift detection for a portal.

        Loads the baseline, captures current state from YAML,
        compares them, and returns a DriftReport.

        Args:
            portal_id: Portal identifier.

        Returns:
            DriftReport with all detected drifts.

        Raises:
            BaselineNotFoundError: If no baseline exists.
        """
        if not self._recorder.has_baseline(portal_id):
            raise BaselineNotFoundError(portal_id)

        # Load baseline
        baseline = self._recorder.load(portal_id)

        # Capture current state from YAML
        current = self._recorder.capture_from_yaml(portal_id)

        # Compare
        events = self._compare(baseline, current)

        # Build report
        report = DriftReport(
            portal_id=portal_id,
            events=events,
            baseline_version=baseline.version,
            current_version=current.version,
            total_selectors_checked=baseline.selector_count,
            total_selectors_changed=len(events),
        )

        logger.info(
            f"Drift detection for {portal_id}: "
            f"{len(events)} drifts from {baseline.selector_count} selectors, "
            f"health={report.health_score:.1f}"
        )
        return report

    def detect_all(self) -> Dict[str, DriftReport]:
        """Run drift detection on all portals with baselines."""
        reports = {}
        for portal_id in self._storage.list_baselines():
            try:
                reports[portal_id] = self.detect(portal_id)
            except Exception as e:
                logger.error(f"Drift detection failed for {portal_id}: {e}")
        return reports

    def _compare(self, baseline: BaselineSnapshot,
                 current: BaselineSnapshot) -> List[DriftEvent]:
        """Compare baseline vs current selectors and generate events."""
        events: List[DriftEvent] = []

        baseline_names = set(baseline.selectors.keys())
        current_names = set(current.selectors.keys())

        # 1. Selectors in baseline but not in current (missing/removed)
        missing = baseline_names - current_names
        for name in sorted(missing):
            bl = baseline.selectors[name]
            events.append(DriftEvent(
                selector_name=name,
                baseline_selector=bl.selector,
                current_selector=None,
                drift_type=DriftType.SELECTOR_MISSING,
                severity=DriftSeverity.CRITICAL,
                confidence=0.95,
                description=(
                    f"Selector '{name}' ({bl.selector}) "
                    f"is no longer found in the portal mapping"
                ),
                tag=bl.tag,
            ))

        # 2. Selectors in both — check for changes
        common = baseline_names & current_names
        for name in sorted(common):
            bl = baseline.selectors[name]
            cur = current.selectors[name]
            event = self._compare_selector(name, bl, cur)
            if event:
                events.append(event)

        # 3. Selectors in current but not baseline (new elements)
        added = current_names - baseline_names
        for name in sorted(added):
            cur = current.selectors[name]
            events.append(DriftEvent(
                selector_name=name,
                baseline_selector="",
                current_selector=cur.selector,
                drift_type=DriftType.ELEMENT_ADDED,
                severity=DriftSeverity.INFO,
                confidence=0.9,
                description=(
                    f"New selector '{name}' ({cur.selector}) "
                    f"appeared in portal mapping"
                ),
                tag=cur.tag,
            ))

        return events

    def _compare_selector(self, name: str,
                           bl: BaselineSelector,
                           cur: BaselineSelector) -> Optional[DriftEvent]:
        """Compare a single baseline vs current selector.

        Returns a DriftEvent if a meaningful change is detected,
        or None if the selector is unchanged.
        """
        # Same selector string — no drift
        if bl.selector == cur.selector and bl.hash == cur.hash:
            return None

        # Different selector — this is actionable drift
        severity = DriftSeverity.MAJOR
        confidence = 0.8
        drift_type = DriftType.SELECTOR_CHANGED

        # Check if it's just a minor difference
        if self._is_minor_change(bl.selector, cur.selector):
            severity = DriftSeverity.MINOR
            drift_type = DriftType.ATTRIBUTE_CHANGED
            confidence = 0.6

        # Suggest the new selector as the fix
        suggested = cur.selector if cur.selector != bl.selector else None

        return DriftEvent(
            selector_name=name,
            baseline_selector=bl.selector,
            current_selector=cur.selector,
            drift_type=drift_type,
            severity=severity,
            confidence=confidence,
            description=(
                f"Selector changed from '{bl.selector}' "
                f"to '{cur.selector}'"
            ),
            tag=cur.tag or bl.tag,
            text_before=bl.text,
            text_after=cur.text,
            attributes_before=bl.attributes,
            attributes_after=cur.attributes,
            suggested_selector=suggested,
        )

    def _is_minor_change(self, old_sel: str, new_sel: str) -> bool:
        """Check if a selector change is minor (attribute-level only)."""
        if old_sel == new_sel:
            return True

        # Same tag + attribute structure but different values
        import re
        old_parts = set(re.findall(r'\[(\w+)=', old_sel))
        new_parts = set(re.findall(r'\[(\w+)=', new_sel))

        # Same attributes used — probably just value change
        if old_parts and old_parts == new_parts:
            return True

        # Same tag name but different class/attribute
        old_tag = old_sel.split("[")[0].split(".")[0].split("#")[0] if "[" in old_sel else old_sel.split(".")[0].split("#")[0]
        new_tag = new_sel.split("[")[0].split(".")[0].split("#")[0] if "[" in new_sel else new_sel.split(".")[0].split("#")[0]
        if old_tag == new_tag:
            return True

        return False

    def compare_snapshots(self, baseline: BaselineSnapshot,
                          current: BaselineSnapshot) -> DriftReport:
        """Compare two arbitrary snapshots (for testing/analysis)."""
        events = self._compare(baseline, current)
        return DriftReport(
            portal_id=baseline.portal_id,
            events=events,
            baseline_version=baseline.version,
            current_version=current.version,
            total_selectors_checked=baseline.selector_count,
            total_selectors_changed=len(events),
        )
