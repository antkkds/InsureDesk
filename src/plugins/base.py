"""InsureDesk — Plugin System: Base Plugin Interface.

Defines the abstract base class for all InsureDesk plugins.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Set


@dataclass
class PluginContext:
    """Services injected into each plugin on initialization.

    Plugins should NOT import services directly — use this context.
    """
    document_vault: Any = None  # DocumentVault
    bridge: Any = None          # BridgeClient
    db_session: Any = None      # SQLAlchemy session
    settings: Dict[str, Any] = field(default_factory=dict)
    logger: Any = None


class Plugin(ABC):
    """Base class for all InsureDesk plugins.

    A plugin:
    - Registers its capabilities for discovery
    - Receives dependencies via PluginContext (not direct imports)
    - Has a clean lifecycle (initialize → use → shutdown)
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique plugin identifier (e.g. 'document_intelligence')."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version string."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> Set[str]:
        """Set of capability strings this plugin provides.

        Examples: {'document.parse', 'document.extract_policy', 'document.index'}
        """
        ...

    def initialize(self, context: PluginContext) -> None:
        """Called once when the plugin is loaded.

        Args:
            context: Injected services (vault, bridge, db, settings).
        """
        self._ctx = context

    def shutdown(self) -> None:
        """Called when the plugin is unloaded. Clean up resources."""
        pass
