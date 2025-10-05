"""Hook system for Proofy plugin architecture (internal)."""

from __future__ import annotations

from .manager import ProofyPluginManager, get_plugin_manager, reset_plugin_manager
from .specs import ProofyHookSpecs, hookimpl, hookspec

__all__ = [
    "hookspec",
    "hookimpl",
    "ProofyHookSpecs",
    "get_plugin_manager",
    "ProofyPluginManager",
    "reset_plugin_manager",
]
