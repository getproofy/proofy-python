"""Plugin manager for Proofy hook system."""

from __future__ import annotations

import threading

from pluggy import PluginManager

from .specs import ProofyHookSpecs

# Global plugin manager instance
_plugin_manager: PluginManager | None = None
_manager_lock = threading.Lock()


def get_plugin_manager() -> PluginManager:
    """Get the global Proofy plugin manager instance.

    This is a thread-safe singleton that ensures only one plugin manager
    exists across the entire application.

    Returns:
        PluginManager: The global plugin manager instance
    """
    global _plugin_manager

    if _plugin_manager is None:
        with _manager_lock:
            # Double-check locking pattern
            if _plugin_manager is None:
                _plugin_manager = PluginManager("proofy")
                _plugin_manager.add_hookspecs(ProofyHookSpecs)

    return _plugin_manager


def reset_plugin_manager() -> None:
    """Reset the plugin manager (primarily for testing).

    This will clear the global plugin manager instance, causing the next
    call to get_plugin_manager() to create a fresh instance.
    """
    global _plugin_manager

    with _manager_lock:
        if _plugin_manager is not None:
            # Unregister all plugins
            for plugin in list(_plugin_manager.get_plugins()):
                _plugin_manager.unregister(plugin)
        _plugin_manager = None


class ProofyPluginManager:
    """High-level wrapper around the pluggy PluginManager.

    Provides convenience methods for common plugin operations and
    maintains consistency across different framework adapters.
    """

    def __init__(self) -> None:
        self._pm = get_plugin_manager()

    @property
    def hook(self):
        """Access to the hook calling interface."""
        return self._pm.hook

    def register_plugin(self, plugin: object, name: str | None = None) -> None:
        """Register a plugin with the manager.

        Args:
            plugin: Plugin instance with hook implementations
            name: Optional name for the plugin
        """
        self._pm.register(plugin, name)

    def unregister_plugin(self, plugin: object) -> None:
        """Unregister a plugin from the manager.

        Args:
            plugin: Plugin instance to unregister
        """
        self._pm.unregister(plugin)

    def get_plugins(self) -> list:
        """Get all registered plugins.

        Returns:
            List of registered plugin instances
        """
        return self._pm.get_plugins()  # type: ignore[return-value]

    def has_plugin(self, name: str) -> bool:
        """Check if a plugin is registered by name.

        Args:
            name: Plugin name to check

        Returns:
            True if plugin is registered, False otherwise
        """
        return self._pm.has_plugin(name)

    def call_hook(self, hook_name: str, **kwargs) -> list:
        """Call a hook by name with keyword arguments.

        Args:
            hook_name: Name of the hook to call
            **kwargs: Arguments to pass to the hook

        Returns:
            List of results from hook implementations
        """
        hook = getattr(self.hook, hook_name, None)
        if hook is None:
            raise ValueError(f"Unknown hook: {hook_name}")
        return hook(**kwargs)

    def call_hook_first_result(self, hook_name: str, **kwargs):
        """Call a hook and return the first non-None result.

        Args:
            hook_name: Name of the hook to call
            **kwargs: Arguments to pass to the hook

        Returns:
            First non-None result, or None if all results are None
        """
        results = self.call_hook(hook_name, **kwargs)
        for result in results:
            if result is not None:
                return result
        return None
