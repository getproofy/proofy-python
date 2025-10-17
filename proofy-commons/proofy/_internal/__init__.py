"""Private internals for Proofy.

This package's ``__init__`` is intentionally import-light to avoid circular
imports. Import concrete submodules directly, e.g.:

    from proofy._internal.logger import get_logger
    from proofy._internal.context import get_context_service
    from proofy._internal.results import ResultsHandler
    from proofy._internal.artifacts import ArtifactUploader
"""

from __future__ import annotations

# Do not import submodules here. Keep this file minimal.

__all__: list[str] = []
