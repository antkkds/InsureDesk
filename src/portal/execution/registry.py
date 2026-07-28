"""Portal Execution Engine — Executor Registry.

Maps abstract action names (e.g. "create_quote", "login", "validate")
to concrete executor functions that implement those actions.

This is the key decoupling layer:
- ExecutionEngine does NOT know about QuoteExecutor, NavigationEngine, etc.
- It only knows action names and the Registry
- Each executor is a callable that takes (context, step) and returns a dict
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from src.portal.execution.exceptions import ExecutorNotFoundError
from src.portal.execution.models import ExecutionContext, ExecutionStep

logger = logging.getLogger("insuredesk.execution.registry")

# Type: executor(context, step) → result dict
ExecutorFunc = Callable[[ExecutionContext, ExecutionStep], Dict[str, Any]]


class ExecutorRegistry:
    """Thread-safe registry of action executors.

    Usage:
        registry = ExecutorRegistry()

        # Register an executor
        registry.register("create_quote", my_create_quote_func)

        # Resolve and execute
        executor = registry.resolve("create_quote")
        result = executor(context, step)
    """

    def __init__(self) -> None:
        self._executors: Dict[str, ExecutorFunc] = {}

    def register(
        self,
        action: str,
        executor: ExecutorFunc,
        overwrite: bool = False,
    ) -> None:
        """Register an executor for an action.

        Args:
            action: Action name (e.g. "create_quote", "login")
            executor: Callable that implements the action
            overwrite: If True, replace an existing registration

        Raises:
            ValueError: If action is already registered and overwrite=False
        """
        if action in self._executors and not overwrite:
            raise ValueError(
                f"Executor for action '{action}' is already registered. "
                "Use overwrite=True to replace."
            )
        self._executors[action] = executor
        logger.debug("Registered executor for action '%s'", action)

    def resolve(self, action: str) -> ExecutorFunc:
        """Resolve an executor by action name.

        Args:
            action: The action name to look up

        Returns:
            The registered executor function

        Raises:
            ExecutorNotFoundError: If no executor is registered for this action
        """
        executor = self._executors.get(action)
        if executor is None:
            raise ExecutorNotFoundError(
                f"No executor registered for action '{action}'. "
                f"Available: {list(self._executors.keys())}"
            )
        return executor

    def unregister(self, action: str) -> None:
        """Remove an executor registration."""
        self._executors.pop(action, None)
        logger.debug("Unregistered executor for action '%s'", action)

    def list_actions(self) -> list[str]:
        """Return all registered action names."""
        return list(self._executors.keys())

    def has_action(self, action: str) -> bool:
        """Check if an action is registered."""
        return action in self._executors

    def clear(self) -> None:
        """Remove all registrations."""
        self._executors.clear()

    def __len__(self) -> int:
        return len(self._executors)
