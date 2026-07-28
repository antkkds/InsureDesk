"""InsureDesk — Plugin System: Registry.

Central registry for discovering and loading plugins.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.plugins.base import Plugin, PluginContext

logger = logging.getLogger("insuredesk.plugins.registry")


class PluginRegistry:
    """Registry for all loaded plugins.

    Usage:
        registry = PluginRegistry()
        registry.register(DocumentIntelligencePlugin())
        registry.initialize_all(context)

        # Find by capability
        plugins = registry.find_capability('document.parse')

        # Get by ID
        plugin = registry.get('document_intelligence')
    """

    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._initialized = False

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance.

        Args:
            plugin: Plugin instance to register.

        Raises:
            ValueError: If a plugin with the same ID is already registered.
        """
        if plugin.id in self._plugins:
            raise ValueError(f"Plugin '{plugin.id}' is already registered")
        self._plugins[plugin.id] = plugin
        logger.info(f"Registered plugin: {plugin.id} v{plugin.version}")

    def initialize_all(self, context: PluginContext) -> None:
        """Initialize all registered plugins with shared context."""
        for plugin_id, plugin in self._plugins.items():
            try:
                plugin.initialize(context)
                logger.info(f"Initialized plugin: {plugin_id}")
            except Exception as e:
                logger.error(f"Failed to initialize plugin '{plugin_id}': {e}")
        self._initialized = True

    def shutdown_all(self) -> None:
        """Shut down all plugins gracefully."""
        for plugin_id, plugin in self._plugins.items():
            try:
                plugin.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down plugin '{plugin_id}': {e}")
        self._initialized = False

    def get(self, plugin_id: str) -> Optional[Plugin]:
        """Get a plugin by its ID."""
        return self._plugins.get(plugin_id)

    def find_capability(self, capability: str) -> List[Plugin]:
        """Find all plugins that provide a specific capability.

        Args:
            capability: e.g. 'document.parse', 'portal.execute'

        Returns:
            List of plugins providing this capability.
        """
        return [
            p for p in self._plugins.values()
            if capability in p.capabilities
        ]

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all registered plugins with metadata."""
        return [
            {
                "id": p.id,
                "version": p.version,
                "capabilities": sorted(p.capabilities),
            }
            for p in self._plugins.values()
        ]

    @property
    def count(self) -> int:
        return len(self._plugins)


# Global registry singleton
default_registry = PluginRegistry()
