"""Support for pytest-xdist integration."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

try:
    # Check if xdist is available
    import xdist  # type: ignore # noqa: F401

    XDIST_AVAILABLE = True
except ImportError:
    XDIST_AVAILABLE = False


def register_xdist_hooks(plugin_manager: Any, plugin_instance: Any) -> None:
    """Register xdist hooks if xdist is available."""
    if not XDIST_AVAILABLE:
        return

    # Create a hooks class with proper hookimpl decorators
    class ProofyXdistHooks:
        def __init__(self, plugin_instance: Any) -> None:
            self.plugin_instance = plugin_instance

        def pytest_configure_node(self, node: Any) -> None:
            """Configure pytest-xdist worker nodes."""
            if not hasattr(node, "workerinput"):
                return

            # Transfer essential configuration to worker
            if self.plugin_instance:
                node.workerinput.update(
                    {
                        "proofy_config_dict": self.plugin_instance.config.__dict__,
                        "proofy_run_id": self.plugin_instance.run_id,
                        "proofy_session_id": self.plugin_instance.session_id,
                    }
                )

        def pytest_testnodedown(self, node: Any, error: Any) -> None:
            """Called when an xdist worker node goes down."""
            # Handle worker cleanup if needed
            pass

        def pytest_testnodeready(self, node: Any) -> None:
            """Called when an xdist worker node is ready."""
            # Worker is ready to receive tests
            pass

    # Register the hooks
    try:
        hooks = ProofyXdistHooks(plugin_instance)
        plugin_manager.register(hooks, "proofy_xdist_hooks")
    except Exception:
        # If registration fails, xdist might not be properly installed
        pass


def is_xdist_worker(session: Any) -> bool:
    """Check if running in an xdist worker."""
    return hasattr(session.config, "workerinput")


def get_worker_input(session: Any) -> Any:
    """Get worker input data if available."""
    if hasattr(session.config, "workerinput"):
        return session.config.workerinput
    return None


def setup_worker_plugin(session: Any) -> Any:
    """Set up plugin instance for xdist worker."""
    from .config import ProofyConfig
    from .plugin import ProofyPytestPlugin

    workerinput = get_worker_input(session)
    if not workerinput or "proofy_config_dict" not in workerinput:
        return None

    try:
        # Reconstruct config from dict
        config_dict = workerinput["proofy_config_dict"]
        proofy_config = ProofyConfig(**config_dict)
        plugin = ProofyPytestPlugin(proofy_config)

        # Use shared run_id from master
        plugin.run_id = workerinput.get("proofy_run_id")
        plugin.session_id = workerinput.get("proofy_session_id", str(uuid.uuid4()))

        # Store plugin instance in config for access
        session.config._proofy_plugin = plugin

        return plugin
    except Exception:
        # If worker setup fails, return None to disable plugin for this worker
        return None


def transfer_config_to_workers(plugin_instance: Any) -> dict[str, Any]:
    """Prepare config data for transfer to workers."""
    if not plugin_instance:
        return {}

    return {
        "proofy_config_dict": plugin_instance.config.__dict__,
        "proofy_run_id": plugin_instance.run_id,
        "proofy_session_id": plugin_instance.session_id,
    }
