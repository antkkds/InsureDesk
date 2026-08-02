"""InsureDesk — Real E2E Validation Profile (Phase 4.6).

ChatGPT last guard before the real Windows validation:
    Do NOT rely on a human remembering "no Save Draft, no Submit".
    Load a validation profile at startup and ENFORCE it — so a future
    code change cannot accidentally open up the test environment.

    e2e_profile:
      name: real_validation
      execution_policy: {mode: real, permission: readonly}
      allowed: [calculate_quote]
      blocked: [save_draft, submit]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_PROFILE: Dict[str, Any] = {
    "name": "real_validation",
    "execution_policy": {
        "mode": "real",
        "permission": "readonly",
    },
    "allowed": ["calculate_quote", "quote", "calculate", "status", "search"],
    "blocked": ["save_draft", "submit", "save", "issue", "delete", "update"],
}


@dataclass
class E2EProfile:
    """Enforced safety profile for the real (non-simulation) E2E run."""

    name: str = "real_validation"
    mode: str = "real"
    permission: str = "readonly"
    allowed: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "E2EProfile":
        data = data or DEFAULT_PROFILE
        policy = data.get("execution_policy", {})
        return cls(
            name=data.get("name", "real_validation"),
            mode=policy.get("mode", "real"),
            permission=policy.get("permission", "readonly"),
            allowed=list(data.get("allowed", DEFAULT_PROFILE["allowed"])),
            blocked=list(data.get("blocked", DEFAULT_PROFILE["blocked"])),
        )

    def is_action_allowed(self, capability: str, arguments: Optional[Dict[str, Any]] = None) -> bool:
        """Enforce the profile:
        - explicit blocked keyword (capability or arguments) → denied
        - readonly permission + mutating keyword → denied
        - otherwise allowed.
        """
        combined = f"{capability} {str(arguments or {}).lower()}".lower()
        for blocked in self.blocked:
            if blocked in combined:
                return False
        if self.permission == "readonly":
            for mut in ("submit", "save_draft", "save", "issue", "delete", "update"):
                if mut in combined:
                    return False
        # allowed list is advisory in the profile; blocklist is the guard
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "execution_policy": {"mode": self.mode, "permission": self.permission},
            "allowed": list(self.allowed),
            "blocked": list(self.blocked),
        }


class E2EProfileEnforcer:
    """Loads the profile once at startup and guards every capability
    execution during the real E2E run."""

    def __init__(self, profile: Optional[E2EProfile] = None) -> None:
        self.profile = profile or E2EProfile.from_dict(DEFAULT_PROFILE)
        self.blocks: int = 0

    def check(self, capability: str, arguments: Optional[Dict[str, Any]] = None) -> None:
        """Raise PolicyBlockedError if the action is not allowed."""
        if not self.profile.is_action_allowed(capability, arguments):
            self.blocks += 1
            from src.agent.result_reporter import map_error_code

            raise E2EBlockedError(
                capability=capability,
                reason=f"Blocked by e2e profile '{self.profile.name}' (readonly)",
            )


class E2EBlockedError(Exception):
    """Raised when the E2E profile blocks an action."""

    def __init__(self, capability: str, reason: str):
        super().__init__(f"{capability}: {reason}")
        self.capability = capability
        self.reason = reason
        self.error_code = "READ_ONLY_BLOCKED"
