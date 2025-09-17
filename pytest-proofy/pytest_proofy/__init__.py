"""Pytest plugin for Proofy test reporting."""

from .config import ProofyConfig
from .plugin import ProofyPytestPlugin

__version__ = "0.1.0"
__author__ = "Proofy Team"

__all__ = [
    "ProofyConfig",
    "ProofyPytestPlugin",
]
