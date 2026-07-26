"""InsureDesk Runtime — Dynamic Adapter Registry.

Extends the static adapter_registry.py with:
- register() / unregister() at runtime
- discover() — scan for new adapter classes
- find_by_capability() — query adapters by capability
- stats tracking across all registered adapters

Usage:
    from src.runtime.registry import adapter_registry

    # Get an adapter (auto-instantiated)
    ge = adapter_registry.get("great_eastern")
    p = ge.extract_policy({...})

    # Register a custom adapter at runtime
    adapter_registry.register("tokio_marine", TokioMarineAdapter,
                               capabilities={AdapterCapability.FETCH_POLICY})

    # Find all adapters that can submit claims
    claim_adapters = adapter_registry.find_by_capability("submit_claim")
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Type, Any, TYPE_CHECKING

from src.models.adapter_base import ModelAdapter
from src.models.adapter_ge import GreatEasternAdapter, GreatEasternPDFAdapter
from src.models.adapter_allianz import AllianzAdapter
from src.models.adapter_aia import AIAAdapter
from src.runtime.capabilities import (
    AdapterCapability,
    get_adapter_capabilities,
    register_adapter_capabilities,
    supports_capability,
)

if TYPE_CHECKING:
    from src.runtime.selector import DetectionResult


class AdapterRegistry:
    """Dynamic, extensible registry of ModelAdapters.

    Thread-safe for read operations. Register/unregister should be
    called during application startup or when plugins are loaded.
    """

    def __init__(self):
        self._adapters: Dict[str, Type[ModelAdapter]] = {}
        self._instances: Dict[str, ModelAdapter] = {}
        # Aliases (short names → canonical key)
        self._aliases: Dict[str, str] = {}
        self._builtin_loaded = False

    # ── Registration ──

    def register(
        self,
        key: str,
        adapter_cls: Type[ModelAdapter],
        capabilities: Optional[Set[AdapterCapability]] = None,
        aliases: Optional[List[str]] = None,
    ) -> ModelAdapter:
        """Register a new adapter class.

        Args:
            key: Canonical registry key (e.g. 'great_eastern')
            adapter_cls: The adapter class (must be a ModelAdapter subclass)
            capabilities: Optional set of capabilities (defaults to CORE_CAPABILITIES)
            aliases: Optional short aliases (e.g. ['ge'])

        Returns:
            An instance of the registered adapter
        """
        key = key.lower().replace(" ", "_")

        # Store the class
        self._adapters[key] = adapter_cls

        # Store capabilities if provided
        if capabilities is not None:
            register_adapter_capabilities(key, capabilities)

        # Register aliases
        if aliases:
            for alias in aliases:
                self._aliases[alias.lower().replace(" ", "_")] = key

        # Clear cached instance so next get() creates fresh
        self._instances.pop(key, None)

        return self.get(key)

    def unregister(self, key: str) -> bool:
        """Remove an adapter from the registry.

        Args:
            key: Canonical key, alias, or portal name

        Returns:
            True if an adapter was removed
        """
        key = self._resolve_key(key)
        if key in self._adapters:
            del self._adapters[key]
            self._instances.pop(key, None)
            # Remove aliases pointing to this key
            self._aliases = {a: k for a, k in self._aliases.items() if k != key}
            return True
        return False

    # ── Retrieval ──

    def get(self, key: str) -> Optional[ModelAdapter]:
        """Get a ModelAdapter instance by key or alias.

        Args:
            key: Canonical key, alias, or portal name

        Returns:
            ModelAdapter instance, or None if not found
        """
        if not self._builtin_loaded:
            self._load_builtins()

        resolved = self._resolve_key(key)
        if not resolved:
            return None

        # Return cached instance or create new one
        if resolved not in self._instances:
            cls = self._adapters[resolved]
            self._instances[resolved] = cls()
        return self._instances[resolved]

    def get_adapter_for_data(
        self,
        raw_data: Dict[str, Any],
        portal_hint: Optional[str] = None,
    ) -> "DetectionResult":
        """Get the best matching adapter for raw portal data.

        Returns a DetectionResult with confidence scores and alternatives.

        Args:
            raw_data: Raw portal data as a dict
            portal_hint: Optional portal name hint (skips detection if provided)

        Returns:
            DetectionResult with the selected adapter info
        """
        from src.runtime.selector import select_adapter
        return select_adapter(raw_data, portal_hint=portal_hint, registry=self)

    # ── Query ──

    def list(self) -> List[Dict[str, Any]]:
        """List all registered adapters with metadata.

        Returns:
            List of dicts with keys: name, key, type, capabilities, aliases
        """
        if not self._builtin_loaded:
            self._load_builtins()

        results = []
        seen_cls = set()
        for key, cls in self._adapters.items():
            if cls not in seen_cls:
                seen_cls.add(cls)
                # Get short-lived instance for name
                inst = cls()
                caps = get_adapter_capabilities(key)
                aliases = [a for a, k in self._aliases.items() if k == key]
                results.append({
                    "name": inst.name,
                    "key": key,
                    "type": "pdf" if "pdf" in key else "portal",
                    "capabilities": sorted(c.value for c in caps),
                    "aliases": aliases,
                    "class": cls.__name__,
                })
        return results

    def find_by_capability(self, capability: AdapterCapability) -> List[Dict[str, Any]]:
        """Find all adapters that support a given capability.

        Args:
            capability: The capability to search for

        Returns:
            List of adapter metadata dicts
        """
        return [
            a for a in self.list()
            if capability.value in a["capabilities"]
        ]

    def has_adapter(self, key: str) -> bool:
        """Check if an adapter is registered.

        Args:
            key: Canonical key, alias, or portal name
        """
        if not self._builtin_loaded:
            self._load_builtins()
        resolved = self._resolve_key(key)
        return resolved is not None

    # ── Stats ──

    def stats(self) -> Dict[str, Any]:
        """Aggregate stats across all instantiated adapters."""
        total = {"extracted": 0, "validated": 0, "errors": 0}
        per_adapter = {}
        for key, inst in self._instances.items():
            s = inst.stats
            per_adapter[key] = dict(s)
            for k in total:
                total[k] += s.get(k, 0)
        return {
            "total": total,
            "per_adapter": per_adapter,
            "adapter_count": len(self._adapters),
        }

    # ── Internal ──

    def _resolve_key(self, key: str) -> Optional[str]:
        """Resolve a key/alias/name to a canonical adapter key."""
        key = key.lower().replace(" ", "_")

        # Direct match
        if key in self._adapters:
            return key

        # Alias match
        if key in self._aliases:
            return self._aliases[key]

        # Try appending _pdf for pdf keys
        if not key.endswith("_pdf"):
            pdf_key = f"{key}_pdf"
            if pdf_key in self._adapters:
                return pdf_key

        return None

    def _load_builtins(self):
        """Load built-in adapters on first access."""
        if self._builtin_loaded:
            return
        self._builtin_loaded = True

        # Register built-in adapters with their capabilities
        self.register("great_eastern", GreatEasternAdapter,
                      aliases=["ge"])
        self.register("great_eastern_pdf", GreatEasternPDFAdapter,
                      aliases=["ge_pdf"])
        self.register("allianz", AllianzAdapter)
        self.register("aia", AIAAdapter)


# ── Singleton instance ──
adapter_registry = AdapterRegistry()
"""Global adapter registry singleton.

Usage:
    from src.runtime.registry import adapter_registry
    ge = adapter_registry.get("great_eastern")
"""
