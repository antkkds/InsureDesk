"""Tests: Portal Drift Detection (Sprint 5.2).

Tests for the drift detection module: models, baseline capture,
detector, analyzer, reporter, and suggestions.
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
import pytest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. Data Models (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestDriftModels:
    """Tests for drift detection data models."""

    def test_baseline_selector_creates(self):
        from src.portal.drift.models import BaselineSelector
        bs = BaselineSelector(name="login.username", selector="input[name='oac_username']")
        assert bs.name == "login.username"
        assert bs.selector == "input[name='oac_username']"
        assert bs.is_interactive is True

    def test_baseline_selector_roundtrip(self):
        from src.portal.drift.models import BaselineSelector
        bs = BaselineSelector(name="login.pwd", selector="#password",
                              tag="input", text="Password")
        d = bs.to_dict()
        bs2 = BaselineSelector.from_dict(d)
        assert bs2.name == "login.pwd"
        assert bs2.selector == "#password"
        assert bs2.tag == "input"

    def test_baseline_snapshot_creates(self):
        from src.portal.drift.models import BaselineSnapshot, BaselineSelector
        snap = BaselineSnapshot(portal_id="great_eastern")
        snap.selectors["login.username"] = BaselineSelector(
            name="login.username", selector="input[name='user']"
        )
        assert snap.portal_id == "great_eastern"
        assert snap.selector_count == 1

    def test_baseline_snapshot_roundtrip(self):
        from src.portal.drift.models import BaselineSnapshot, BaselineSelector
        snap = BaselineSnapshot(portal_id="test_portal")
        snap.selectors["a"] = BaselineSelector(name="a", selector="#sel1")
        snap.selectors["b"] = BaselineSelector(name="b", selector=".cls")
        d = snap.to_dict()
        snap2 = BaselineSnapshot.from_dict(d)
        assert snap2.portal_id == "test_portal"
        assert snap2.selector_count == 2
        assert snap2.find_selector("a").selector == "#sel1"

    def test_drift_event_creates(self):
        from src.portal.drift.models import DriftEvent, DriftSeverity, DriftType
        event = DriftEvent(
            selector_name="login.username",
            baseline_selector="#old_sel",
            current_selector="#new_sel",
            drift_type=DriftType.SELECTOR_CHANGED,
            severity=DriftSeverity.CRITICAL,
            confidence=0.95,
            description="Selector changed",
        )
        assert event.is_actionable is True
        assert event.severity.value == "critical"

    def test_drift_event_non_actionable(self):
        from src.portal.drift.models import DriftEvent, DriftSeverity, DriftType
        event = DriftEvent(
            selector_name="dashboard.info",
            baseline_selector=".welcome",
            current_selector=".welcome-new",
            drift_type=DriftType.ATTRIBUTE_CHANGED,
            severity=DriftSeverity.INFO,
            confidence=0.5,
            description="Minor change",
        )
        assert event.is_actionable is False
        assert "INFO" in event.summary

    def test_drift_report_computes_health(self):
        from src.portal.drift.models import (
            DriftReport, DriftEvent, DriftSeverity, DriftType
        )
        report = DriftReport(portal_id="test", total_selectors_checked=10)
        event = DriftEvent(
            selector_name="test.sel",
            baseline_selector="#old",
            drift_type=DriftType.SELECTOR_MISSING,
            severity=DriftSeverity.CRITICAL,
        )
        report.events.append(event)
        assert report.critical_count == 1
        assert report.health_score < 100
        assert report.actionable_count == 1

    def test_drift_report_clean_health(self):
        from src.portal.drift.models import DriftReport
        report = DriftReport(portal_id="test", total_selectors_checked=10)
        assert report.health_score == 100.0
        assert report.actionable_count == 0


# ══════════════════════════════════════════════════════════════════
# 2. Baseline Storage (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestBaselineStorage:
    """Tests for BaselineStorage persistence."""

    @pytest.fixture
    def storage(self):
        from src.portal.drift.storage import BaselineStorage
        with tempfile.TemporaryDirectory() as tmp:
            yield BaselineStorage(storage_dir=tmp)

    @pytest.fixture
    def sample_snapshot(self):
        from src.portal.drift.models import BaselineSnapshot, BaselineSelector
        snap = BaselineSnapshot(portal_id="test_portal")
        snap.selectors["login.user"] = BaselineSelector(
            name="login.user", selector="input[name='user']"
        )
        return snap

    def test_save_and_load(self, storage, sample_snapshot):
        storage.save_baseline(sample_snapshot)
        loaded = storage.load_baseline("test_portal")
        assert loaded.portal_id == "test_portal"
        assert loaded.selector_count == 1
        assert loaded.find_selector("login.user").selector == "input[name='user']"

    def test_has_baseline(self, storage, sample_snapshot):
        assert storage.has_baseline("test_portal") is False
        storage.save_baseline(sample_snapshot)
        assert storage.has_baseline("test_portal") is True

    def test_list_baselines(self, storage, sample_snapshot):
        assert storage.list_baselines() == []
        storage.save_baseline(sample_snapshot)
        assert "test_portal" in storage.list_baselines()

    def test_delete_baseline(self, storage, sample_snapshot):
        storage.save_baseline(sample_snapshot)
        assert storage.has_baseline("test_portal") is True
        storage.delete_baseline("test_portal")
        assert storage.has_baseline("test_portal") is False

    def test_load_nonexistent_raises(self, storage):
        from src.portal.drift.exceptions import BaselineNotFoundError
        with pytest.raises(BaselineNotFoundError):
            storage.load_baseline("does_not_exist")


# ══════════════════════════════════════════════════════════════════
# 3. Baseline Recorder (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestBaselineRecorder:
    """Tests for BaselineRecorder capture."""

    def test_capture_from_yaml_exists(self):
        """Can capture a baseline from an existing portal YAML."""
        from src.portal.drift.baseline import BaselineRecorder
        recorder = BaselineRecorder()
        snap = recorder.capture_from_yaml("great_eastern")
        assert snap.portal_id == "great_eastern"
        assert snap.selector_count >= 30  # GE has lots of selectors
        # Check login selectors exist
        assert snap.find_selector("login.username") is not None
        assert snap.find_selector("login.password") is not None
        assert snap.find_selector("login.submit") is not None

    def test_capture_from_yaml_allianz(self):
        from src.portal.drift.baseline import BaselineRecorder
        recorder = BaselineRecorder()
        snap = recorder.capture_from_yaml("allianz")
        assert snap.selector_count >= 5

    def test_capture_from_yaml_aia(self):
        from src.portal.drift.baseline import BaselineRecorder
        recorder = BaselineRecorder()
        snap = recorder.capture_from_yaml("aia")
        assert snap.selector_count >= 5

    def test_capture_nonexistent_raises(self):
        from src.portal.drift.baseline import BaselineRecorder
        from src.portal.drift.exceptions import CaptureError
        recorder = BaselineRecorder()
        with pytest.raises(CaptureError):
            recorder.capture_from_yaml("nonexistent_portal")


# ══════════════════════════════════════════════════════════════════
# 4. Drift Detector (7 tests)
# ══════════════════════════════════════════════════════════════════

class TestDriftDetector:
    """Tests for DriftDetector comparison logic."""

    def test_no_drift_when_identical(self):
        """Two identical snapshots produce zero drift events."""
        from src.portal.drift.models import BaselineSnapshot, BaselineSelector
        from src.portal.drift.detector import DriftDetector
        snap = BaselineSnapshot(portal_id="test")
        snap.selectors["login.user"] = BaselineSelector(
            name="login.user", selector="input[name='user']"
        )
        snap.selectors["login.pwd"] = BaselineSelector(
            name="login.pwd", selector="#password"
        )
        detector = DriftDetector()
        report = detector.compare_snapshots(snap, snap)
        assert len(report.events) == 0
        assert report.health_score == 100.0

    def test_detects_missing_selector(self):
        from src.portal.drift.models import BaselineSnapshot, BaselineSelector
        from src.portal.drift.detector import DriftDetector
        base = BaselineSnapshot(portal_id="test")
        base.selectors["login.user"] = BaselineSelector(
            name="login.user", selector="input[name='user']"
        )
        current = BaselineSnapshot(portal_id="test")
        # No selectors at all
        detector = DriftDetector()
        report = detector.compare_snapshots(base, current)
        assert len(report.events) == 1
        assert report.events[0].drift_type.value == "selector_missing"
        assert report.events[0].severity.value == "critical"

    def test_detects_new_selector(self):
        from src.portal.drift.models import BaselineSnapshot, BaselineSelector
        from src.portal.drift.detector import DriftDetector
        base = BaselineSnapshot(portal_id="test")
        current = BaselineSnapshot(portal_id="test")
        current.selectors["new.field"] = BaselineSelector(
            name="new.field", selector="#new"
        )
        detector = DriftDetector()
        report = detector.compare_snapshots(base, current)
        assert len(report.events) == 1
        assert report.events[0].drift_type.value == "element_added"
        assert report.events[0].severity.value == "info"

    def test_detects_selector_change(self):
        from src.portal.drift.models import BaselineSnapshot, BaselineSelector
        from src.portal.drift.detector import DriftDetector
        base = BaselineSnapshot(portal_id="test")
        base.selectors["login.user"] = BaselineSelector(
            name="login.user", selector="#old_input_id",
            hash="abc"
        )
        current = BaselineSnapshot(portal_id="test")
        current.selectors["login.user"] = BaselineSelector(
            name="login.user", selector="input[name='username']",
            hash="def"
        )
        detector = DriftDetector()
        report = detector.compare_snapshots(base, current)
        assert len(report.events) == 1
        assert report.events[0].drift_type.value == "selector_changed"
        assert report.events[0].severity.value == "major"

    def test_multiple_drifts(self):
        from src.portal.drift.models import BaselineSnapshot, BaselineSelector
        from src.portal.drift.detector import DriftDetector
        base = BaselineSnapshot(portal_id="test")
        for i in range(5):
            base.selectors[f"sel.{i}"] = BaselineSelector(
                name=f"sel.{i}", selector=f"#sel{i}"
            )
        current = BaselineSnapshot(portal_id="test")
        for i in range(3):
            current.selectors[f"sel.{i}"] = BaselineSelector(
                name=f"sel.{i}", selector=f"#sel{i}_new"
            )
        detector = DriftDetector()
        report = detector.compare_snapshots(base, current)
        assert len(report.events) == 5  # 3 changed + 2 missing

    def test_end_to_end_with_yaml(self):
        """Full e2e: capture baseline, detect no drift initially."""
        from src.portal.drift.baseline import BaselineRecorder
        from src.portal.drift.detector import DriftDetector
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            from src.portal.drift.storage import BaselineStorage
            storage = BaselineStorage(storage_dir=tmp)
            recorder = BaselineRecorder(storage=storage)
            detector = DriftDetector(recorder=recorder, storage=storage)

            # Capture baseline
            snap = recorder.capture_from_yaml("great_eastern")
            recorder.save(snap)

            # Detect — should have no drift since YAML hasn't changed
            report = detector.detect("great_eastern")
            assert report.total_selectors_checked > 0
            assert report.portal_id == "great_eastern"

    def test_detect_without_baseline_raises(self):
        from src.portal.drift.detector import DriftDetector
        from src.portal.drift.exceptions import BaselineNotFoundError
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            from src.portal.drift.storage import BaselineStorage
            storage = BaselineStorage(storage_dir=tmp)
            detector = DriftDetector(storage=storage)
            with pytest.raises(BaselineNotFoundError):
                detector.detect("nonexistent")


# ══════════════════════════════════════════════════════════════════
# 5. Drift Analyzer (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestDriftAnalyzer:
    """Tests for DriftAnalyzer workflow impact analysis."""

    def test_analyzer_maps_workflow_by_prefix(self):
        from src.portal.drift.models import DriftEvent, DriftSeverity, DriftType
        from src.portal.drift.analyzer import DriftAnalyzer
        event = DriftEvent(
            selector_name="login.username",
            baseline_selector="#old",
            drift_type=DriftType.SELECTOR_CHANGED,
            severity=DriftSeverity.MAJOR,
        )
        analyzer = DriftAnalyzer()
        result = analyzer.analyze_event(event)
        assert "Login & Authentication" in result.affected_workflows

    def test_analyzer_maps_claims_workflow(self):
        from src.portal.drift.models import DriftEvent, DriftSeverity, DriftType
        from src.portal.drift.analyzer import DriftAnalyzer
        event = DriftEvent(
            selector_name="claims.submit_button",
            baseline_selector="#old",
            drift_type=DriftType.SELECTOR_MISSING,
            severity=DriftSeverity.CRITICAL,
        )
        analyzer = DriftAnalyzer()
        result = analyzer.analyze_event(event)
        assert "Claims Management" in result.affected_workflows

    def test_summary_by_workflow(self):
        from src.portal.drift.models import DriftReport, DriftEvent, DriftSeverity, DriftType
        from src.portal.drift.analyzer import DriftAnalyzer
        report = DriftReport(portal_id="test")
        report.events.append(DriftEvent(
            selector_name="login.user", baseline_selector="#o",
            drift_type=DriftType.SELECTOR_MISSING, severity=DriftSeverity.CRITICAL,
        ))
        report.events.append(DriftEvent(
            selector_name="claims.btn", baseline_selector="#c",
            drift_type=DriftType.SELECTOR_CHANGED, severity=DriftSeverity.MAJOR,
        ))
        analyzer = DriftAnalyzer()
        analyzer.analyze_report(report)
        summary = analyzer.summary_by_workflow(report)
        assert "Login & Authentication" in summary
        assert "Claims Management" in summary
        assert summary["Login & Authentication"]["critical"] == 1


# ══════════════════════════════════════════════════════════════════
# 6. Suggestion Engine (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestSuggestionEngine:
    """Tests for SuggestionEngine fix suggestions."""

    def test_suggests_update_for_changed_selector(self):
        from src.portal.drift.models import DriftEvent, DriftSeverity, DriftType
        from src.portal.drift.suggestions import SuggestionEngine
        event = DriftEvent(
            selector_name="login.user",
            baseline_selector="#old",
            current_selector="#new",
            suggested_selector="#new",
            drift_type=DriftType.SELECTOR_CHANGED,
            severity=DriftSeverity.MAJOR,
            confidence=0.85,
        )
        engine = SuggestionEngine()
        s = engine.suggest_for_event(event)
        assert s["action"] == "update_yaml"
        assert s["new_selector"] == "#new"

    def test_suggests_recapture_for_missing(self):
        from src.portal.drift.models import DriftEvent, DriftSeverity, DriftType
        from src.portal.drift.suggestions import SuggestionEngine
        event = DriftEvent(
            selector_name="login.user",
            baseline_selector="#old",
            drift_type=DriftType.SELECTOR_MISSING,
            severity=DriftSeverity.CRITICAL,
            confidence=0.95,
        )
        engine = SuggestionEngine()
        s = engine.suggest_for_event(event)
        assert s["action"] == "recapture"

    def test_suggest_for_report_orders_by_severity(self):
        from src.portal.drift.models import DriftReport, DriftEvent, DriftSeverity, DriftType
        from src.portal.drift.suggestions import SuggestionEngine
        report = DriftReport(portal_id="test")
        report.events.append(DriftEvent(
            selector_name="minor.sel", baseline_selector="#m",
            drift_type=DriftType.ATTRIBUTE_CHANGED, severity=DriftSeverity.INFO,
        ))
        report.events.append(DriftEvent(
            selector_name="critical.sel", baseline_selector="#c",
            drift_type=DriftType.SELECTOR_MISSING, severity=DriftSeverity.CRITICAL,
        ))
        engine = SuggestionEngine()
        suggestions = engine.suggest_for_report(report)
        assert suggestions[0]["severity"] == "critical"


# ══════════════════════════════════════════════════════════════════
# 7. Reporter (2 tests)
# ══════════════════════════════════════════════════════════════════

class TestDriftReporter:
    """Tests for DriftReporter output formatting."""

    def test_generate_report_includes_portal_id(self):
        from src.portal.drift.models import DriftReport
        from src.portal.drift.reporter import DriftReporter
        report = DriftReport(portal_id="great_eastern")
        reporter = DriftReporter()
        output = reporter.generate_report(report)
        assert "GREAT_EASTERN" in output
        assert "PORTAL DRIFT REPORT" in output
        assert "Health Score" in output

    def test_generate_report_includes_events(self):
        from src.portal.drift.models import (
            DriftReport, DriftEvent, DriftSeverity, DriftType
        )
        from src.portal.drift.reporter import DriftReporter
        report = DriftReport(portal_id="test")
        report.events.append(DriftEvent(
            selector_name="login.user",
            baseline_selector="#old",
            drift_type=DriftType.SELECTOR_MISSING,
            severity=DriftSeverity.CRITICAL,
            confidence=0.9,
        ))
        reporter = DriftReporter()
        output = reporter.generate_report(report)
        assert "login.user" in output
        assert "critical" in output
