"""Tests for Portal Workflow Recorder.

Covers:
- Data models (RecordedEvent, RecordedStep, Workflow, WorkflowStep, RecordingSession)
- SelectorGenerator (CSS selector generation, priority order, edge cases)
- CaptureEngine (session management, event capture, error handling)
- Normalizer (event grouping, deduplication, step generation)
- WorkflowSerializer (Workflow conversion, YAML output, file saving)
- ReplayEngine (Workflow → ExecutionPlan, execution, resume)
- RecordingEngine (orchestration, full pipeline)
- Integration (with ExecutionEngine)
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest

from src.portal.recorder.models import (
    EventType,
    RecordedEvent,
    RecordedStep,
    RecordingSession,
    Workflow,
    WorkflowStep,
)
from src.portal.recorder.engine import RecordingEngine
from src.portal.recorder.capture import CaptureEngine
from src.portal.recorder.normalizer import Normalizer
from src.portal.recorder.selector import SelectorGenerator
from src.portal.recorder.serializer import WorkflowSerializer
from src.portal.recorder.replay import ReplayEngine
from src.portal.recorder.exceptions import (
    CaptureError,
    RecordingNotFoundError,
    SelectorGenerationError,
    SerializationError,
    ReplayError,
)
from src.portal.execution.models import ExecutionResult
from src.portal.execution.engine import ExecutionEngine
from src.portal.execution.registry import ExecutorRegistry


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def selector_gen() -> SelectorGenerator:
    return SelectorGenerator()


@pytest.fixture
def capture_engine() -> CaptureEngine:
    return CaptureEngine()


@pytest.fixture
def normalizer() -> Normalizer:
    return Normalizer()


@pytest.fixture
def serializer() -> WorkflowSerializer:
    return WorkflowSerializer()


@pytest.fixture
def executor_registry() -> ExecutorRegistry:
    reg = ExecutorRegistry()

    def passthrough(ctx, step):
        return {"status": "ok", "action": step.action}

    for action in ("navigate", "fill", "click", "select", "submit", "wait"):
        reg.register(action, passthrough)
    return reg


@pytest.fixture
def execution_engine(executor_registry: ExecutorRegistry) -> ExecutionEngine:
    return ExecutionEngine(executor_registry)


@pytest.fixture
def recording_engine(execution_engine: ExecutionEngine) -> RecordingEngine:
    return RecordingEngine(execution_engine)


# =============================================================================
# Data Models
# =============================================================================


class TestEventType:
    def test_all_includes_common(self):
        types = EventType.all()
        assert "click" in types
        assert "input" in types
        assert "navigate" in types


class TestRecordedEvent:
    def test_auto_id(self):
        e1 = RecordedEvent(type="click")
        e2 = RecordedEvent(type="click")
        assert e1.id != e2.id

    def test_to_dict(self):
        e = RecordedEvent(type="click", url="https://example.com",
                           selector="#btn")
        d = e.to_dict()
        assert d["type"] == "click"
        assert d["selector"] == "#btn"


class TestRecordingSession:
    def test_start_stop(self):
        s = RecordingSession(portal="ge")
        assert s.is_active is False
        s.start()
        assert s.is_active is True
        assert s.started_at is not None
        s.stop()
        assert s.is_active is False
        assert s.stopped_at is not None

    def test_add_event(self):
        s = RecordingSession(portal="ge")
        s.add_event(RecordedEvent(type="click"))
        assert s.event_count == 1


class TestWorkflow:
    def test_add_step(self):
        w = Workflow(name="test", portal="ge")
        w.add_step(WorkflowStep(action="navigate"))
        assert w.step_count == 1

    def test_to_dict(self):
        w = Workflow(name="ge_quote", portal="great_eastern")
        w.add_step(WorkflowStep(action="navigate",
                                parameters={"url": "https://ge.com"}))
        d = w.to_dict()
        assert d["workflow"]["name"] == "ge_quote"
        assert len(d["workflow"]["steps"]) == 1


# =============================================================================
# SelectorGenerator
# =============================================================================


class TestSelectorGenerator:
    def test_by_id(self, selector_gen: SelectorGenerator):
        sel = selector_gen.generate(tag="input", attributes={"id": "username"})
        assert sel == "#username"

    def test_by_name(self, selector_gen: SelectorGenerator):
        sel = selector_gen.generate(tag="input", attributes={"name": "email"})
        assert sel == "input[name='email']"

    def test_by_data_testid(self, selector_gen: SelectorGenerator):
        sel = selector_gen.generate(tag="button",
                                     attributes={"data-testid": "submit-btn"})
        assert "[data-testid='submit-btn']" in sel

    def test_by_placeholder(self, selector_gen: SelectorGenerator):
        sel = selector_gen.generate(tag="input",
                                     attributes={"placeholder": "Enter name"})
        assert "placeholder" in sel

    def test_by_aria_label(self, selector_gen: SelectorGenerator):
        sel = selector_gen.generate(tag="button",
                                     attributes={"aria-label": "Close"})
        assert "aria-label" in sel

    def test_by_class(self, selector_gen: SelectorGenerator):
        sel = selector_gen.generate(tag="button",
                                     attributes={"class": "btn-primary"})
        assert sel == "button.btn-primary"

    def test_by_tag_type(self, selector_gen: SelectorGenerator):
        sel = selector_gen.generate(tag="input", attributes={"type": "submit"})
        assert sel == "input[type='submit']"

    def test_fallback_tag_only(self, selector_gen: SelectorGenerator):
        sel = selector_gen.generate(tag="button", attributes={})
        assert sel == "button"

    def test_raises_on_no_stable_selector(self, selector_gen: SelectorGenerator):
        with pytest.raises(SelectorGenerationError):
            selector_gen.generate(tag="div", attributes={"style": "color: red"})

    def test_escape_special_chars(self, selector_gen: SelectorGenerator):
        sel = selector_gen.generate(tag="input",
                                     attributes={"name": "user's_name"})
        assert "user" in sel


# =============================================================================
# CaptureEngine
# =============================================================================


class TestCaptureEngine:
    def test_start_session(self, capture_engine: CaptureEngine):
        session = capture_engine.start_session("great_eastern")
        assert session.is_active is True
        assert session.portal == "great_eastern"

    def test_capture_event(self, capture_engine: CaptureEngine):
        session = capture_engine.start_session("ge")
        event = capture_engine.capture_event(
            session.id,
            {"type": "click", "tag_name": "button",
             "attributes": {"id": "submit"}},
        )
        assert event.type == "click"
        assert event.selector == "#submit"

    def test_capture_invalid_type(self, capture_engine: CaptureEngine):
        session = capture_engine.start_session("ge")
        with pytest.raises(CaptureError):
            capture_engine.capture_event(
                session.id, {"type": "invalid_type"}
            )

    def test_capture_invalid_session(self, capture_engine: CaptureEngine):
        with pytest.raises(CaptureError):
            capture_engine.capture_event("nonexistent", {"type": "click"})

    def test_stop_session(self, capture_engine: CaptureEngine):
        session = capture_engine.start_session("ge")
        capture_engine.capture_event(session.id, {"type": "click"})
        stopped = capture_engine.stop_session(session.id)
        assert stopped.is_active is False
        assert stopped.event_count == 1

    def test_get_session(self, capture_engine: CaptureEngine):
        session = capture_engine.start_session("ge")
        assert capture_engine.get_session(session.id) is session
        assert capture_engine.get_session("nonexistent") is None

    def test_event_listener(self, capture_engine: CaptureEngine):
        events = []

        def listener(event):
            events.append(event)

        capture_engine.add_event_listener(listener)
        session = capture_engine.start_session("ge")
        capture_engine.capture_event(session.id, {"type": "click"})
        assert len(events) == 1

    def test_capture_on_inactive_session(self, capture_engine: CaptureEngine):
        session = capture_engine.start_session("ge")
        capture_engine.stop_session(session.id)
        with pytest.raises(CaptureError):
            capture_engine.capture_event(session.id, {"type": "click"})


# =============================================================================
# Normalizer
# =============================================================================


class TestNormalizer:
    def test_empty_events(self, normalizer: Normalizer):
        steps = normalizer.normalize([])
        assert steps == []

    def test_single_click(self, normalizer: Normalizer):
        events = [RecordedEvent(type="click", selector="#btn")]
        steps = normalizer.normalize(events)
        assert len(steps) == 1
        assert steps[0].action == "click"

    def test_input_event(self, normalizer: Normalizer):
        events = [RecordedEvent(type="input", selector="#name", value="John")]
        steps = normalizer.normalize(events)
        assert len(steps) == 1
        assert steps[0].action == "fill"
        assert steps[0].value == "John"

    def test_navigate_event(self, normalizer: Normalizer):
        events = [RecordedEvent(type="navigate", url="https://ge.com/quote")]
        steps = normalizer.normalize(events)
        assert len(steps) == 1
        assert steps[0].action == "navigate"

    def test_filters_hover(self, normalizer: Normalizer):
        events = [
            RecordedEvent(type="hover"),
            RecordedEvent(type="click", selector="#btn"),
        ]
        steps = normalizer.normalize(events)
        assert len(steps) == 1
        assert steps[0].action == "click"

    def test_consecutive_inputs_deduplicated(self, normalizer: Normalizer):
        events = [
            RecordedEvent(type="input", selector="#name", value="Jo"),
            RecordedEvent(type="input", selector="#name", value="John"),
        ]
        steps = normalizer.normalize(events)
        # Deduplication: same selector, keep last value
        assert len(steps) == 1
        assert steps[0].value == "John"

    def test_different_inputs_preserved(self, normalizer: Normalizer):
        events = [
            RecordedEvent(type="input", selector="#name", value="John"),
            RecordedEvent(type="input", selector="#age", value="35"),
        ]
        steps = normalizer.normalize(events)
        assert len(steps) == 2

    def test_select_event(self, normalizer: Normalizer):
        events = [RecordedEvent(type="select", selector="#gender",
                                 value="Male")]
        steps = normalizer.normalize(events)
        assert len(steps) == 1
        assert steps[0].action == "select"

    def test_submit_event(self, normalizer: Normalizer):
        events = [RecordedEvent(type="submit", selector="form")]
        steps = normalizer.normalize(events)
        assert steps[0].action == "submit"
        assert steps[0].wait_after_ms == 2000

    def test_mixed_events(self, normalizer: Normalizer):
        events = [
            RecordedEvent(type="navigate", url="https://ge.com"),
            RecordedEvent(type="input", selector="#user", value="admin"),
            RecordedEvent(type="input", selector="#pass", value="secret"),
            RecordedEvent(type="click", selector="#loginBtn"),
        ]
        steps = normalizer.normalize(events)
        assert len(steps) == 4
        assert steps[0].action == "navigate"
        assert steps[1].action == "fill"
        assert steps[2].action == "fill"
        assert steps[3].action == "click"


# =============================================================================
# WorkflowSerializer
# =============================================================================


class TestWorkflowSerializer:
    def test_to_workflow_basic(self, serializer: WorkflowSerializer):
        steps = [
            RecordedStep(action="navigate", value="https://ge.com"),
            RecordedStep(action="fill", selector="#name", value="John"),
            RecordedStep(action="click", selector="#submit"),
        ]
        workflow = serializer.to_workflow(steps, portal="great_eastern")
        assert workflow.portal == "great_eastern"
        assert workflow.step_count == 3

    def test_to_yaml(self, serializer: WorkflowSerializer):
        workflow = Workflow(name="test", portal="ge")
        workflow.add_step(WorkflowStep(action="navigate",
                                        parameters={"url": "https://ge.com"}))
        workflow.add_step(WorkflowStep(action="fill",
                                        parameters={"selector": "#name",
                                                     "value": "John"}))
        yaml = serializer.to_yaml(workflow)
        assert "name: test" in yaml
        assert "portal: ge" in yaml
        assert "action: navigate" in yaml
        assert "action: fill" in yaml

    def test_save_yaml(self, serializer: WorkflowSerializer):
        workflow = Workflow(name="test", portal="ge")
        workflow.add_step(WorkflowStep(action="navigate",
                                        parameters={"url": "https://ge.com"}))

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            path = f.name

        try:
            saved = serializer.save_yaml(workflow, path)
            assert os.path.exists(saved)
            with open(saved) as f:
                content = f.read()
                assert "action: navigate" in content
        finally:
            os.unlink(path)

    def test_to_dict_structure(self, serializer: WorkflowSerializer):
        steps = [RecordedStep(action="click", selector="#btn")]
        workflow = serializer.to_workflow(steps, portal="ge")
        d = workflow.to_dict()
        assert "workflow" in d
        assert d["workflow"]["portal"] == "ge"


# =============================================================================
# ReplayEngine
# =============================================================================


class TestReplayEngine:
    def test_to_execution_plan(self, execution_engine: ExecutionEngine):
        replay = ReplayEngine(execution_engine)
        workflow = Workflow(name="test", portal="ge")
        workflow.add_step(WorkflowStep(action="navigate",
                                        parameters={"url": "https://ge.com"}))
        workflow.add_step(WorkflowStep(action="fill",
                                        parameters={"selector": "#name",
                                                     "value": "John"}))

        plan = replay.to_execution_plan(workflow)
        assert plan.name == "test"
        assert len(plan.steps) == 2
        assert plan.steps[0].action == "navigate"
        assert plan.steps[1].action == "fill"

    def test_execute_workflow(self, execution_engine: ExecutionEngine):
        replay = ReplayEngine(execution_engine)
        workflow = Workflow(name="test", portal="ge")
        workflow.add_step(WorkflowStep(action="navigate",
                                        parameters={"url": "https://ge.com"}))

        result = replay.execute_workflow(workflow)
        assert result.success is True

    def test_execute_workflow_with_data(self, execution_engine: ExecutionEngine):
        replay = ReplayEngine(execution_engine)
        workflow = Workflow(name="test", portal="ge")
        workflow.add_step(WorkflowStep(action="navigate",
                                        parameters={"url": "https://ge.com"}))

        result = replay.execute_workflow(workflow, data={"key": "value"})
        assert result.success is True


# =============================================================================
# RecordingEngine (Integration)
# =============================================================================


class TestRecordingEngine:
    def test_start_stop_recording(self, recording_engine: RecordingEngine):
        session = recording_engine.start_recording("great_eastern",
                                                    "https://ge.com")
        assert session.is_active
        recording_engine.stop_recording(session.id)
        assert session.is_active is False

    def test_capture_during_recording(self, recording_engine: RecordingEngine):
        session = recording_engine.start_recording("ge")
        recording_engine.capture_event(
            session.id,
            {"type": "click", "tag_name": "button",
             "attributes": {"id": "submit"}},
        )
        assert session.event_count == 1

    def test_to_workflow(self, recording_engine: RecordingEngine):
        session = recording_engine.start_recording("ge")
        recording_engine.capture_event(
            session.id, {"type": "navigate", "url": "https://ge.com"}
        )
        recording_engine.capture_event(
            session.id, {"type": "input", "selector": "#name", "value": "John"}
        )
        recording_engine.stop_recording(session.id)

        workflow = recording_engine.to_workflow(session.id, name="ge_quote")
        assert workflow.name == "ge_quote"
        assert workflow.step_count >= 2

    def test_replay_recorded_workflow(
        self, recording_engine: RecordingEngine
    ):
        session = recording_engine.start_recording("ge")
        recording_engine.capture_event(
            session.id,
            {"type": "click", "tag_name": "button",
             "attributes": {"id": "test-btn"}},
        )
        recording_engine.stop_recording(session.id)

        workflow = recording_engine.to_workflow(session.id, name="test_replay")
        result = recording_engine.replay_workflow(workflow)
        assert result.success is True

    def test_save_workflow(self, recording_engine: RecordingEngine):
        session = recording_engine.start_recording("ge")
        recording_engine.capture_event(
            session.id, {"type": "click", "selector": "#btn"}
        )
        recording_engine.stop_recording(session.id)
        workflow = recording_engine.to_workflow(session.id)

        with tempfile.NamedTemporaryFile(
            suffix=".yaml", delete=False
        ) as f:
            path = f.name

        try:
            saved = recording_engine.save_workflow(workflow, path)
            assert os.path.exists(saved)
        finally:
            os.unlink(path)

    def test_get_session(self, recording_engine: RecordingEngine):
        session = recording_engine.start_recording("ge")
        assert recording_engine.get_session(session.id) is session
        assert recording_engine.get_session("nonexistent") is None

    def test_normalize_events(self, recording_engine: RecordingEngine):
        session = recording_engine.start_recording("ge")
        recording_engine.capture_event(
            session.id, {"type": "click", "selector": "#btn"}
        )
        steps = recording_engine.normalize_events(session.id)
        assert len(steps) == 1

    def test_normalize_nonexistent_session(
        self, recording_engine: RecordingEngine
    ):
        with pytest.raises(RecordingNotFoundError):
            recording_engine.normalize_events("nonexistent")
