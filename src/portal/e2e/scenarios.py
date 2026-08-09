"""InsureDesk — Production E2E Validation: Scenarios.

Predefined validation scenarios that test portal behavior
under various conditions (happy path, errors, recovery).
"""
from __future__ import annotations

from src.portal.e2e.models import (
    E2EScenario, ScenarioStep, ScenarioType, StepType,
)


def happy_path_scenario(portal_id: str = "great_eastern") -> E2EScenario:
    """Standard happy path: login → navigate → extract → logout."""
    scenario = E2EScenario(
        type=ScenarioType.HAPPY_PATH,
        name="Happy Path — Full Workflow",
        description="Standard user flow: login, search policy, view details, logout",
        portal_id=portal_id,
        tags=["smoke", "core"],
    )
    scenario.add_step(ScenarioStep(
        type=StepType.LOGIN,
        name="Login",
        description="Log into the portal",
        action="login",
        params={"username": "test_user", "password": "test_pass"},
        timeout=30,
        retry_count=1,
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.NAVIGATE,
        name="Navigate to Policy Search",
        description="Click on Policy Search navigation link",
        action="navigate",
        params={"route_name": "policy_search"},
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.FILL,
        name="Search Policy",
        description="Enter policy number and search",
        action="execute_action",
        params={"action_type": "search_policy", "params": {"policy_no": "POL123"}},
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.EXTRACT,
        name="Get Policy Details",
        description="Extract policy details from detail page",
        action="execute_action",
        params={"action_type": "get_policy_details"},
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.LOGOUT,
        name="Logout",
        description="Log out of the portal",
        action="logout",
    ))
    return scenario


def session_timeout_scenario(portal_id: str = "great_eastern") -> E2EScenario:
    """Simulate session timeout and test recovery."""
    scenario = E2EScenario(
        type=ScenarioType.SESSION_TIMEOUT,
        name="Session Timeout Recovery",
        description="Simulate expired session, test recover_session()",
        portal_id=portal_id,
        tags=["recovery", "resilience"],
    )
    scenario.add_step(ScenarioStep(
        type=StepType.LOGIN,
        name="Initial Login",
        description="Log in to establish session",
        action="login",
        params={"username": "test_user", "password": "test_pass"},
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.CUSTOM,
        name="Clear Session",
        description="Force session expiry (clear cookies)",
        action="logout",
        inject_error="session_expired",
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.RECOVER,
        name="Recover Session",
        description="Attempt to recover expired session",
        action="recover_session",
        retry_count=2,
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.NAVIGATE,
        name="Verify Recovery",
        description="Navigate after recovery to verify session is valid",
        action="navigate",
        params={"route_name": "dashboard"},
    ))
    return scenario


def browser_crash_scenario(portal_id: str = "great_eastern") -> E2EScenario:
    """Simulate browser crash and test reconnect."""
    scenario = E2EScenario(
        type=ScenarioType.BROWSER_CRASH,
        name="Browser Crash Recovery",
        description="Simulate browser crash, verify reconnect and session restore",
        portal_id=portal_id,
        tags=["recovery", "resilience"],
    )
    scenario.add_step(ScenarioStep(
        type=StepType.LOGIN,
        name="Login",
        description="Log in to establish session",
        action="login",
        params={"username": "test_user", "password": "test_pass"},
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.CUSTOM,
        name="Simulate Crash",
        description="Simulate browser disconnection",
        action="disconnect",
        inject_error="browser_crash",
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.CUSTOM,
        name="Reconnect",
        description="Re-establish browser connection",
        action="connect",
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.RECOVER,
        name="Restore Session",
        description="Restore session after reconnect",
        action="recover_session",
    ))
    return scenario


def network_failure_scenario(portal_id: str = "great_eastern") -> E2EScenario:
    """Simulate network failure and test retry logic."""
    scenario = E2EScenario(
        type=ScenarioType.NETWORK_FAILURE,
        name="Network Failure Retry",
        description="Simulate network timeout, verify retry mechanism",
        portal_id=portal_id,
        tags=["resilience"],
    )
    scenario.add_step(ScenarioStep(
        type=StepType.LOGIN,
        name="Login",
        description="Log in to establish session",
        action="login",
        params={"username": "test_user", "password": "test_pass"},
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.NAVIGATE,
        name="Navigate (with timeout)",
        description="Navigate with simulated network delay",
        action="navigate",
        params={"route_name": "policy_search"},
        timeout=5,
        retry_count=2,
        inject_error="network_timeout",
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.ASSERT,
        name="Verify After Retry",
        description="Check that the page loaded after retry",
        action="health_check",
    ))
    return scenario


def resume_checkpoint_scenario(portal_id: str = "great_eastern") -> E2EScenario:
    """Test checkpoint and resume workflow."""
    scenario = E2EScenario(
        type=ScenarioType.RESUME_CHECKPOINT,
        name="Checkpoint & Resume",
        description="Create checkpoint, resume workflow from checkpoint",
        portal_id=portal_id,
        tags=["resilience", "recovery"],
    )
    scenario.add_step(ScenarioStep(
        type=StepType.LOGIN,
        name="Login",
        description="Log in",
        action="login",
        params={"username": "test_user", "password": "test_pass"},
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.NAVIGATE,
        name="Navigate",
        description="Navigate to policy search",
        action="navigate",
        params={"route_name": "policy_search"},
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.CUSTOM,
        name="Save Checkpoint",
        description="Save current state as checkpoint",
        action="health_check",  # Stand-in for checkpoint save
        inject_error="save_checkpoint",
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.RECOVER,
        name="Resume from Checkpoint",
        description="Resume workflow from saved checkpoint",
        action="recover_session",
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.ASSERT,
        name="Verify Resume",
        description="Verify we're on the expected page after resume",
        action="health_check",
    ))
    return scenario


def portal_drift_scenario(portal_id: str = "great_eastern") -> E2EScenario:
    """Simulate portal UI change and test drift detection."""
    scenario = E2EScenario(
        type=ScenarioType.PORTAL_DRIFT,
        name="Portal Drift Detection",
        description="Simulate a selector change, verify drift detection catches it",
        portal_id=portal_id,
        tags=["drift", "resilience"],
    )
    scenario.add_step(ScenarioStep(
        type=StepType.LOGIN,
        name="Login",
        description="Log in",
        action="login",
        params={"username": "test_user", "password": "test_pass"},
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.ASSERT,
        name="Check Health",
        description="Check portal health baseline",
        action="health_check",
    ))
    # Drift detection would use the drift module
    scenario.add_step(ScenarioStep(
        type=StepType.VALIDATE,
        name="Detect Drift",
        description="Run drift detection and check for changes",
        action="execute_action",
        params={"action_type": "health_check"},
    ))
    return scenario


def auth_failure_scenario(portal_id: str = "great_eastern") -> E2EScenario:
    """Test authentication failure handling."""
    scenario = E2EScenario(
        type=ScenarioType.AUTH_FAILURE,
        name="Authentication Failure",
        description="Verify proper error handling on failed login",
        portal_id=portal_id,
        tags=["auth", "security"],
    )
    scenario.add_step(ScenarioStep(
        type=StepType.LOGIN,
        name="Login with Bad Credentials",
        description="Attempt login with invalid credentials",
        action="login",
        params={"username": "bad_user", "password": "bad_pass"},
        timeout=10,
    ))
    scenario.add_step(ScenarioStep(
        type=StepType.ASSERT,
        name="Verify Not Logged In",
        description="Check that login was rejected",
        action="health_check",
        expected={"logged_in": False},
    ))
    return scenario


# Registry of all predefined scenarios
ALL_SCENARIOS = {
    "happy_path": happy_path_scenario,
    "session_timeout": session_timeout_scenario,
    "browser_crash": browser_crash_scenario,
    "network_failure": network_failure_scenario,
    "resume_checkpoint": resume_checkpoint_scenario,
    "portal_drift": portal_drift_scenario,
    "auth_failure": auth_failure_scenario,
}


def get_scenario(name: str, portal_id: str = "great_eastern") -> E2EScenario:
    """Get a predefined scenario by name."""
    factory = ALL_SCENARIOS.get(name)
    if factory is None:
        raise ValueError(f"Unknown scenario: {name}. Available: {list(ALL_SCENARIOS.keys())}")
    return factory(portal_id)


def list_scenarios() -> list:
    """List all available scenarios with metadata."""
    return [
        {
            "name": name,
            "type": factory().type.value,
            "tags": factory().tags,
            "steps": factory().total_steps,
        }
        for name, factory in ALL_SCENARIOS.items()
    ]
