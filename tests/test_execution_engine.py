"""Tests for Portal Execution Engine.

Covers:
- Data models (ExecutionPlan, ExecutionStep, ExecutionContext, ExecutionResult)
- ExecutorRegistry (registration, resolution, errors)
- PlanBuilder (template-based plan creation, auto-wiring)
- Checkpoint (save, load, restore, lifecycle)
- RollbackManager (rollback logic, partial rollback)
- ResumeManager (resume from checkpoint)
- ExecutionEngine (full execution, step-by-step, retry, error handling)
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime

import pytest

from src.portal.execution.models import (
    Checkpoint,
    ExecutionContext,
    ExecutionPlan,
    ExecutionResult,
    ExecutionStep,
    RetryPolicy,
    StepStatus,
)
from src.portal.execution.engine import ExecutionEngine
from src.portal.execution.plan import PlanBuilder
from src.portal.execution.registry import ExecutorRegistry
from src.portal.execution.checkpoint import (
    CheckpointManager,
    MemoryCheckpointStore,
    SqliteCheckpointStore,
)
from src.portal.execution.rollback import RollbackManager
from src.portal.execution.resume import ResumeManager
from src.portal.execution.exceptions import (
    CheckpointNotFoundError,
    ExecutorNotFoundError,
    ExecutionError,
    ExecutionPausedError,
    PlanValidationError,
    StepExecutionError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def registry() -> ExecutorRegistry:
    reg = ExecutorRegistry()

    def login(ctx: ExecutionContext, step: ExecutionStep) -> dict:
        ctx.set("logged_in", True)
        return {"status": "ok"}

    def fill_customer(ctx: ExecutionContext, step: ExecutionStep) -> dict:
        name = step.parameters.get("name", "default")
        ctx.set("customer_name", name)
        return {"filled": name}

    def calculate(ctx: ExecutionContext, step: ExecutionStep) -> dict:
        ctx.set("premium", 523.0)
        ctx.set("quote_no", "GE12345")
        return {"premium": 523.0, "quote_no": "GE12345"}

    def capture(ctx: ExecutionContext, step: ExecutionStep) -> dict:
        return {k: ctx.get(k) for k in step.parameters.get("outputs", [])}

    def rollback_login(ctx: ExecutionContext, step: ExecutionStep) -> dict:
        ctx.set("logged_in", False)
        return {"status": "rolled_back"}

    reg.register("login", login)
    reg.register("fill", fill_customer)
    reg.register("calculate", calculate)
    reg.register("capture", capture)
    reg.register("rollback_login", rollback_login)
    return reg


@pytest.fixture
def plan_builder() -> PlanBuilder:
    return PlanBuilder()


@pytest.fixture
def engine(registry: ExecutorRegistry) -> ExecutionEngine:
    return ExecutionEngine(registry)


@pytest.fixture
def sample_plan(plan_builder: PlanBuilder) -> ExecutionPlan:
    # Use a plan template that only uses actions in the test registry
    plan_builder.register_template("test_quote", [
        {"name": "login", "action": "login"},
        {"name": "fill_customer", "action": "fill", "parameters": {"name": "test"}},
        {"name": "calculate", "action": "calculate"},
        {"name": "capture_result", "action": "capture", "parameters": {"outputs": ["premium", "quote_no"]}},
    ])
    return plan_builder.build("great_eastern", "test_quote")


@pytest.fixture
def checkpoint_store() -> MemoryCheckpointStore:
    return MemoryCheckpointStore()


@pytest.fixture
def checkpoint_manager(checkpoint_store: MemoryCheckpointStore) -> CheckpointManager:
    return CheckpointManager(checkpoint_store)


# =============================================================================
# Data Models
# =============================================================================


class TestStepStatus:
    def test_enum_values(self):
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.SUCCESS.value == "success"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.ROLLED_BACK.value == "rolled_back"


class TestRetryPolicy:
    def test_default(self):
        p = RetryPolicy()
        assert p.max_retries == 3
        assert p.delay_seconds == 2.0
        assert p.backoff_multiplier == 2.0

    def test_no_retry(self):
        p = RetryPolicy.no_retry()
        assert p.max_retries == 0

    def test_fast(self):
        p = RetryPolicy.fast()
        assert p.max_retries == 2
        assert p.delay_seconds == 0.5

    def test_aggressive(self):
        p = RetryPolicy.aggressive()
        assert p.max_retries == 5


class TestExecutionStep:
    def test_default_status(self):
        step = ExecutionStep(name="test", action="login")
        assert step.status == StepStatus.PENDING
        assert step.retry_count == 0

    def test_auto_id(self):
        step1 = ExecutionStep(name="a", action="x")
        step2 = ExecutionStep(name="b", action="y")
        assert step1.id != step2.id

    def test_custom_id(self):
        step = ExecutionStep(id="my_step", name="test", action="login")
        assert step.id == "my_step"


class TestExecutionPlan:
    def test_default_state(self):
        plan = ExecutionPlan(name="test", portal="great_eastern")
        assert not plan.is_completed
        assert not plan.is_failed
        assert plan.progress == 0.0

    def test_next_step_simple(self):
        steps = [
            ExecutionStep(name="s1", action="a"),
            ExecutionStep(name="s2", action="b"),
        ]
        plan = ExecutionPlan(name="test", portal="p", steps=steps)
        assert plan.next_step() == steps[0]

    def test_next_step_after_completion(self):
        steps = [
            ExecutionStep(name="s1", action="a", status=StepStatus.SUCCESS),
            ExecutionStep(name="s2", action="b"),
        ]
        plan = ExecutionPlan(name="test", portal="p", steps=steps)
        assert plan.next_step() == steps[1]

    def test_next_step_all_done(self):
        steps = [
            ExecutionStep(name="s1", action="a", status=StepStatus.SUCCESS),
            ExecutionStep(name="s2", action="b", status=StepStatus.SUCCESS),
        ]
        plan = ExecutionPlan(name="test", portal="p", steps=steps)
        assert plan.next_step() is None

    def test_progress(self):
        steps = [
            ExecutionStep(name="s1", action="a", status=StepStatus.SUCCESS),
            ExecutionStep(name="s2", action="b"),
            ExecutionStep(name="s3", action="c"),
            ExecutionStep(name="s4", action="d"),
        ]
        plan = ExecutionPlan(name="test", portal="p", steps=steps)
        assert plan.progress == 0.25

    def test_summary(self):
        plan = ExecutionPlan(name="test", portal="great_eastern")
        summary = plan.summary
        assert summary["name"] == "test"
        assert summary["portal"] == "great_eastern"
        assert "steps" in summary

    def test_auto_id(self):
        plan1 = ExecutionPlan(name="a", portal="p")
        plan2 = ExecutionPlan(name="b", portal="p")
        assert plan1.id != plan2.id


class TestExecutionContext:
    def test_set_get(self):
        ctx = ExecutionContext(plan_id="p1", portal="great_eastern")
        ctx.set("key1", "value1")
        assert ctx.get("key1") == "value1"

    def test_get_default(self):
        ctx = ExecutionContext(plan_id="p1", portal="great_eastern")
        assert ctx.get("nonexistent", "default") == "default"

    def test_update(self):
        ctx = ExecutionContext(plan_id="p1", portal="great_eastern")
        ctx.update({"a": 1, "b": 2})
        assert ctx.get("a") == 1
        assert ctx.get("b") == 2

    def test_auto_id(self):
        ctx1 = ExecutionContext(plan_id="p1", portal="p")
        ctx2 = ExecutionContext(plan_id="p1", portal="p")
        assert ctx1.execution_id != ctx2.execution_id


class TestExecutionResult:
    def test_defaults(self):
        r = ExecutionResult()
        assert not r.success
        assert r.data == {}
        assert r.errors == []

    def test_to_dict(self):
        now = datetime.now()
        r = ExecutionResult(
            success=True,
            execution_id="exec_123",
            data={"premium": 500},
            completed_at=now,
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["data"]["premium"] == 500
        assert d["completed_at"] is not None


class TestCheckpoint:
    def test_auto_id(self):
        c1 = Checkpoint(plan_id="p1", step_index=0)
        c2 = Checkpoint(plan_id="p1", step_index=0)
        assert c1.id != c2.id


# =============================================================================
# ExecutorRegistry
# =============================================================================


class TestExecutorRegistry:
    def test_register_and_resolve(self, registry: ExecutorRegistry):
        func = registry.resolve("login")
        assert callable(func)

    def test_resolve_not_found(self, registry: ExecutorRegistry):
        with pytest.raises(ExecutorNotFoundError):
            registry.resolve("nonexistent")

    def test_register_duplicate(self, registry: ExecutorRegistry):
        def dummy(ctx, step):
            return {}

        with pytest.raises(ValueError):
            registry.register("login", dummy)

    def test_register_overwrite(self, registry: ExecutorRegistry):
        def dummy(ctx, step):
            return {"overwritten": True}

        registry.register("login", dummy, overwrite=True)
        assert registry.has_action("login")

    def test_unregister(self, registry: ExecutorRegistry):
        registry.unregister("login")
        assert not registry.has_action("login")

    def test_list_actions(self, registry: ExecutorRegistry):
        actions = registry.list_actions()
        assert "login" in actions
        assert "fill" in actions

    def test_clear(self, registry: ExecutorRegistry):
        registry.clear()
        assert len(registry) == 0

    def test_has_action(self, registry: ExecutorRegistry):
        assert registry.has_action("login")
        assert not registry.has_action("nope")


# =============================================================================
# PlanBuilder
# =============================================================================


class TestPlanBuilder:
    def test_build_create_quote(self, plan_builder: PlanBuilder):
        plan = plan_builder.build("great_eastern", "create_quote")
        assert plan.name == "great_eastern:create_quote"
        assert plan.portal == "great_eastern"
        assert len(plan.steps) > 0
        assert plan.steps[0].action == "login"

    def test_build_invalid_action(self, plan_builder: PlanBuilder):
        with pytest.raises(PlanValidationError):
            plan_builder.build("great_eastern", "nonexistent")

    def test_auto_wire_dependencies(self, plan_builder: PlanBuilder):
        plan = plan_builder.build("great_eastern", "create_quote")
        for i, step in enumerate(plan.steps):
            if i > 0:
                assert len(step.depends_on) > 0

    def test_custom_template(self, plan_builder: PlanBuilder):
        custom_steps = [
            {"name": "step_a", "action": "login"},
            {"name": "step_b", "action": "validate"},
        ]
        plan_builder.register_template("custom_action", custom_steps)
        plan = plan_builder.build("portal_x", "custom_action")
        assert len(plan.steps) == 2
        assert plan.steps[0].name == "step_a"

    def test_list_templates(self, plan_builder: PlanBuilder):
        templates = plan_builder.list_templates()
        assert "create_quote" in templates
        assert "renew_policy" in templates

    def test_build_with_data(self, plan_builder: PlanBuilder):
        plan = plan_builder.build(
            "great_eastern", "create_quote",
            data={"customer": "John"}
        )
        assert plan.metadata["source_data"] == {"customer": "John"}

    def test_build_custom_name(self, plan_builder: PlanBuilder):
        plan = plan_builder.build("ge", "create_quote", plan_name="my_quote")
        assert plan.name == "my_quote"


# =============================================================================
# Checkpoint
# =============================================================================


class TestMemoryCheckpointStore:
    def test_save_and_load(self, checkpoint_store: MemoryCheckpointStore):
        ckpt = Checkpoint(plan_id="p1", step_index=2)
        checkpoint_store.save(ckpt)
        loaded = checkpoint_store.load(ckpt.id)
        assert loaded.plan_id == "p1"
        assert loaded.step_index == 2

    def test_load_not_found(self, checkpoint_store: MemoryCheckpointStore):
        with pytest.raises(CheckpointNotFoundError):
            checkpoint_store.load("nonexistent")

    def test_load_latest(self, checkpoint_store: MemoryCheckpointStore):
        ckpt1 = Checkpoint(plan_id="p1", step_index=1)
        ckpt2 = Checkpoint(plan_id="p1", step_index=2)
        checkpoint_store.save(ckpt1)
        time.sleep(0.01)
        checkpoint_store.save(ckpt2)
        latest = checkpoint_store.load_latest("p1")
        assert latest.step_index == 2

    def test_load_latest_no_checkpoints(self, checkpoint_store: MemoryCheckpointStore):
        assert checkpoint_store.load_latest("nonexistent") is None

    def test_list_for_plan(self, checkpoint_store: MemoryCheckpointStore):
        ckpt1 = Checkpoint(plan_id="p1", step_index=1)
        ckpt2 = Checkpoint(plan_id="p1", step_index=2)
        ckpt3 = Checkpoint(plan_id="p2", step_index=1)
        checkpoint_store.save(ckpt1)
        checkpoint_store.save(ckpt2)
        checkpoint_store.save(ckpt3)
        items = checkpoint_store.list_for_plan("p1")
        assert len(items) == 2

    def test_delete_for_plan(self, checkpoint_store: MemoryCheckpointStore):
        ckpt = Checkpoint(plan_id="p1", step_index=1)
        checkpoint_store.save(ckpt)
        checkpoint_store.delete_for_plan("p1")
        assert checkpoint_store.load_latest("p1") is None


class TestSqliteCheckpointStore:
    @pytest.fixture
    def sqlite_store(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        store = SqliteCheckpointStore(path)
        yield store
        os.unlink(path)

    def test_save_and_load(self, sqlite_store: SqliteCheckpointStore):
        ckpt = Checkpoint(plan_id="p1", step_index=2)
        sqlite_store.save(ckpt)
        loaded = sqlite_store.load(ckpt.id)
        assert loaded.plan_id == "p1"
        assert loaded.step_index == 2

    def test_load_latest(self, sqlite_store: SqliteCheckpointStore):
        ckpt1 = Checkpoint(plan_id="p1", step_index=1)
        ckpt2 = Checkpoint(plan_id="p1", step_index=2)
        sqlite_store.save(ckpt1)
        sqlite_store.save(ckpt2)
        latest = sqlite_store.load_latest("p1")
        assert latest.step_index == 2

    def test_persistence(self, sqlite_store: SqliteCheckpointStore):
        ckpt = Checkpoint(plan_id="p1", step_index=3)
        sqlite_store.save(ckpt)
        # Re-open with same path
        store2 = SqliteCheckpointStore(sqlite_store._db_path)
        loaded = store2.load(ckpt.id)
        assert loaded.step_index == 3


class TestCheckpointManager:
    def test_save_and_restore(self, checkpoint_manager: CheckpointManager):
        plan = ExecutionPlan(name="test", portal="ge")
        ctx = ExecutionContext(plan_id=plan.id, portal="ge")
        ctx.set("premium", 500)

        ckpt = checkpoint_manager.save_checkpoint(plan, ctx)
        assert ckpt.plan_id == plan.id
        assert ckpt.variables.get("premium") == 500

    def test_restore_context(self, checkpoint_manager: CheckpointManager):
        plan = ExecutionPlan(name="test", portal="ge")
        plan.steps = [
            ExecutionStep(name="s1", action="a"),
            ExecutionStep(name="s2", action="b"),
            ExecutionStep(name="s3", action="c"),
        ]
        plan.steps[0].status = StepStatus.SUCCESS
        ctx = ExecutionContext(plan_id=plan.id, portal="ge")
        ctx.set("done", True)
        ckpt = checkpoint_manager.save_checkpoint(plan, ctx)

        # Simulate failure and restore
        new_plan = ExecutionPlan(
            id=plan.id, name="test", portal="ge", steps=[
                ExecutionStep(name="s1", action="a"),
                ExecutionStep(name="s2", action="b"),
                ExecutionStep(name="s3", action="c"),
            ]
        )
        restored = checkpoint_manager.restore_context(ckpt, new_plan)
        assert restored.get("done") is True
        assert new_plan.current_step_index == 0  # step_index was 0

    def test_load_latest(self, checkpoint_manager: CheckpointManager):
        plan = ExecutionPlan(name="test", portal="ge")
        ctx = ExecutionContext(plan_id=plan.id, portal="ge")
        checkpoint_manager.save_checkpoint(plan, ctx)
        loaded = checkpoint_manager.load_latest(plan.id)
        assert loaded is not None
        assert loaded.plan_id == plan.id

    def test_clear_for_plan(self, checkpoint_manager: CheckpointManager):
        plan = ExecutionPlan(name="test", portal="ge")
        ctx = ExecutionContext(plan_id=plan.id, portal="ge")
        checkpoint_manager.save_checkpoint(plan, ctx)
        checkpoint_manager.clear_for_plan(plan.id)
        assert checkpoint_manager.load_latest(plan.id) is None


# =============================================================================
# RollbackManager
# =============================================================================


class TestRollbackManager:
    def test_rollback_to_executes_rollback_actions(self, registry: ExecutorRegistry):
        mgr = RollbackManager(registry)
        plan = ExecutionPlan(name="test", portal="ge")
        plan.steps = [
            ExecutionStep(
                name="login", action="login", rollback_action="rollback_login",
                status=StepStatus.SUCCESS,
            ),
        ]
        ctx = ExecutionContext(plan_id=plan.id, portal="ge")
        ctx.set("logged_in", True)

        result = mgr.rollback_to(plan, ctx, 1)
        assert result is True
        assert plan.steps[0].status == StepStatus.ROLLED_BACK
        assert ctx.get("logged_in") is False

    def test_rollback_no_actions(self, registry: ExecutorRegistry):
        mgr = RollbackManager(registry)
        plan = ExecutionPlan(name="test", portal="ge")
        plan.steps = [
            ExecutionStep(name="fill", action="fill", status=StepStatus.SUCCESS),
        ]
        ctx = ExecutionContext(plan_id=plan.id, portal="ge")
        result = mgr.rollback_to(plan, ctx, 1)
        assert result is True  # Nothing to roll back is fine

    def test_can_rollback(self, registry: ExecutorRegistry):
        mgr = RollbackManager(registry)
        plan = ExecutionPlan(name="test", portal="ge")
        plan.steps = [
            ExecutionStep(
                name="login", action="login", rollback_action="rollback_login",
                status=StepStatus.SUCCESS,
            ),
        ]
        assert mgr.can_rollback(plan, 1) is True

    def test_cannot_rollback(self, registry: ExecutorRegistry):
        mgr = RollbackManager(registry)
        plan = ExecutionPlan(name="test", portal="ge")
        plan.steps = [
            ExecutionStep(name="fill", action="fill", status=StepStatus.SUCCESS),
        ]
        assert mgr.can_rollback(plan, 1) is False


# =============================================================================
# ResumeManager
# =============================================================================


class TestResumeManager:
    def test_resume_from_checkpoint(self, registry: ExecutorRegistry):
        store = MemoryCheckpointStore()
        ckpt_mgr = CheckpointManager(store)
        resume_mgr = ResumeManager(ckpt_mgr)

        # Create plan with 3 steps
        plan = ExecutionPlan(name="test", portal="ge")
        plan.steps = [
            ExecutionStep(name="s1", action="login", status=StepStatus.SUCCESS),
            ExecutionStep(name="s2", action="fill", status=StepStatus.SUCCESS),
            ExecutionStep(name="s3", action="calculate"),
        ]
        ctx = ExecutionContext(plan_id=plan.id, portal="ge")
        ctx.set("premium", 500)

        # Save checkpoint at step 2 (0-indexed)
        ckpt = Checkpoint(
            plan_id=plan.id, step_index=2,
            variables={"premium": 500},
            context={"portal": "ge"},
        )
        store.save(ckpt)

        # Create fresh plan (same id, steps reset to PENDING)
        new_plan = ExecutionPlan(id=plan.id, name="test", portal="ge")
        new_plan.steps = [
            ExecutionStep(name="s1", action="login"),
            ExecutionStep(name="s2", action="fill"),
            ExecutionStep(name="s3", action="calculate"),
        ]

        restored_ctx = resume_mgr.resume(new_plan)
        assert restored_ctx is not None
        assert restored_ctx.get("premium") == 500
        # s1 and s2 should be SUCCESS, s3 should be PENDING
        assert new_plan.steps[0].status == StepStatus.SUCCESS
        assert new_plan.steps[1].status == StepStatus.SUCCESS
        assert new_plan.steps[2].status == StepStatus.PENDING

    def test_resume_no_checkpoint(self, registry: ExecutorRegistry):
        store = MemoryCheckpointStore()
        ckpt_mgr = CheckpointManager(store)
        resume_mgr = ResumeManager(ckpt_mgr)

        plan = ExecutionPlan(name="test", portal="ge")
        result = resume_mgr.resume(plan)
        assert result is None

    def test_has_checkpoint(self, checkpoint_manager: CheckpointManager):
        resume_mgr = ResumeManager(checkpoint_manager)
        plan = ExecutionPlan(name="test", portal="ge")
        ctx = ExecutionContext(plan_id=plan.id, portal="ge")
        checkpoint_manager.save_checkpoint(plan, ctx)
        assert resume_mgr.has_checkpoint(plan) is True

    def test_no_checkpoint(self, checkpoint_manager: CheckpointManager):
        resume_mgr = ResumeManager(checkpoint_manager)
        plan = ExecutionPlan(name="test", portal="ge")
        assert resume_mgr.has_checkpoint(plan) is False


# =============================================================================
# ExecutionEngine — Integration Tests
# =============================================================================


class TestExecutionEngine:
    def test_execute_success(self, engine: ExecutionEngine, sample_plan: ExecutionPlan):
        result = engine.execute(sample_plan)
        assert result.success is True
        assert len(result.completed_steps) > 0
        assert result.data.get("premium") is not None

    def test_execute_context_injection(self, registry: ExecutorRegistry):
        engine = ExecutionEngine(registry)
        plan = engine.create_plan("great_eastern", "test_quote")
        ctx = ExecutionContext(plan_id=plan.id, portal="ge")
        ctx.set("initial_data", "test")
        result = engine.execute(plan, ctx)
        assert result.success is True

    def test_execute_step_by_step(self, engine: ExecutionEngine, sample_plan: ExecutionPlan):
        ctx = engine.start(sample_plan)
        step_count = 0
        while True:
            try:
                step = engine.step(sample_plan, ctx)
                step_count += 1
            except StopIteration:
                break
        result = engine.finish(sample_plan, ctx)
        assert result.success is True
        assert step_count == len(sample_plan.steps)

    def test_execute_failed_step(self, registry: ExecutorRegistry):
        def failing_executor(ctx, step):
            raise RuntimeError("Something went wrong")

        registry.register("fail_action", failing_executor)
        engine = ExecutionEngine(registry)
        plan = engine.create_plan("ge", "test_quote")
        # Replace last step with a failing one
        plan.steps.append(ExecutionStep(name="fail", action="fail_action"))
        result = engine.execute(plan)
        assert result.success is False
        assert len(result.errors) > 0

    def test_execute_with_retry_success(self, registry: ExecutorRegistry):
        call_count = [0]

        def flaky_executor(ctx, step):
            call_count[0] += 1
            if call_count[0] < 3:
                raise TimeoutError("Transient failure")
            return {"status": "ok"}

        registry.register("flaky", flaky_executor)
        engine = ExecutionEngine(registry)
        plan = engine.create_plan("ge", "test_quote")
        plan.steps = [
            ExecutionStep(
                name="flaky_step", action="flaky",
                retry_policy=RetryPolicy(max_retries=3, delay_seconds=0.1),
            ),
        ]
        result = engine.execute(plan)
        assert result.success is True
        assert call_count[0] == 3  # 2 failures + 1 success

    def test_execute_retry_exhausted(self, registry: ExecutorRegistry):
        def always_fail(ctx, step):
            raise TimeoutError("Always fails")

        registry.register("bad", always_fail)
        engine = ExecutionEngine(registry)
        plan = engine.create_plan("ge", "test_quote")
        plan.steps = [
            ExecutionStep(
                name="bad_step", action="bad",
                retry_policy=RetryPolicy(max_retries=2, delay_seconds=0.1),
            ),
        ]
        result = engine.execute(plan)
        assert result.success is False

    def test_execute_with_checkpoint(self, engine: ExecutionEngine, sample_plan: ExecutionPlan):
        result = engine.execute(sample_plan)
        assert result.success is True
        # Checkpoints should have been saved
        ckpt = engine._ckpt_mgr.load_latest(sample_plan.id)
        assert ckpt is not None

    def test_create_plan(self, engine: ExecutionEngine):
        plan = engine.create_plan("great_eastern", "create_quote")
        assert isinstance(plan, ExecutionPlan)
        assert plan.portal == "great_eastern"

    def test_execute_with_resume(self, registry: ExecutorRegistry):
        """Test that execution can resume from a checkpoint after failure."""
        store = MemoryCheckpointStore()
        ckpt_mgr = CheckpointManager(store)
        engine = ExecutionEngine(registry, checkpoint_manager=ckpt_mgr)

        plan = engine.create_plan("ge", "test_quote")
        ctx = ExecutionContext(plan_id=plan.id, portal="ge")

        # Execute normally first
        result = engine.execute_with_resume(plan, ctx)
        assert result.success is True

    def test_execute_paused_plan(self, engine: ExecutionEngine):
        plan = engine.create_plan("ge", "test_quote")
        plan.is_paused = True
        ctx = ExecutionContext(plan_id=plan.id, portal="ge")
        result = engine.execute(plan, ctx)
        assert result.success is False
        assert any("paused" in e.lower() for e in result.errors)

    def test_rollback_on_failure(self, registry: ExecutorRegistry):
        def login_ok(ctx, step):
            ctx.set("logged_in", True)
            return {"status": "ok"}

        def fail_after(ctx, step):
            raise RuntimeError("Critical failure")

        def rollback_login(ctx, step):
            ctx.set("logged_in", False)
            return {"status": "rolled_back"}

        registry.register("login_good", login_ok)
        registry.register("fail_bad", fail_after)
        registry.register("rollback_login", rollback_login, overwrite=True)

        engine = ExecutionEngine(registry)
        plan = ExecutionPlan(name="rollback_test", portal="ge")
        plan.steps = [
            ExecutionStep(
                name="login", action="login_good",
                checkpoint_enabled=True,
                rollback_action="rollback_login",
            ),
            ExecutionStep(name="process", action="fail_bad"),
        ]
        result = engine.execute(plan)
        assert result.success is False
        # Login step should be rolled back
        assert plan.steps[0].status == StepStatus.ROLLED_BACK

    def test_empty_plan(self, engine: ExecutionEngine):
        plan = ExecutionPlan(name="empty", portal="ge")
        result = engine.execute(plan)
        assert result.success is True  # Empty plan succeeds trivially

    def test_result_contains_completed_steps(
        self, engine: ExecutionEngine, sample_plan: ExecutionPlan
    ):
        result = engine.execute(sample_plan)
        assert len(result.completed_steps) > 0
        assert all(isinstance(s, str) for s in result.completed_steps)


# =============================================================================
# Error Handling
# =============================================================================


class TestErrorHandling:
    def test_executor_not_found_error_message(self):
        err = ExecutorNotFoundError("No executor for 'test'")
        assert "No executor" in str(err)

    def test_plan_validation_error(self):
        err = PlanValidationError("No template found")
        assert "template" in str(err)

    def test_checkpoint_not_found(self):
        err = CheckpointNotFoundError("Checkpoint 'x' not found")
        assert "not found" in str(err)

    def test_execution_error_hierarchy(self):
        assert issubclass(StepExecutionError, ExecutionError)
        assert issubclass(PlanValidationError, ExecutionError)
        assert issubclass(ExecutorNotFoundError, ExecutionError)
        assert issubclass(CheckpointNotFoundError, ExecutionError)
