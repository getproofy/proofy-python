"""Run lifecycle management component.

This module extracts run-related responsibilities from ResultsHandler,
providing a focused component for managing run creation, updates, and finalization.
"""

from __future__ import annotations

import logging
from typing import Any

from ...core.client import Client
from ...core.models import RunStatus
from ...core.utils import now_rfc3339
from ..context import ContextService

logger = logging.getLogger("ProofyRunManager")


class RunManager:
    """Manages run lifecycle: creation, updates, and finalization.

    This component isolates all run-related API calls and state management,
    making the system easier to test and maintain.
    """

    def __init__(self, client: Client, context: ContextService) -> None:
        """Initialize run manager.

        Args:
            client: API client for run operations
            context: Context service for accessing session state
        """
        self.client = client
        self.context = context
        self.run_id: int | None = None

    def start_run(
        self,
        *,
        project_id: int,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        """Start a new run or update an existing one.

        If run_id is already set in session context, updates that run.
        Otherwise, creates a new run.

        Args:
            project_id: Project ID
            name: Run name
            attributes: Run attributes

        Returns:
            Run ID

        Raises:
            RuntimeError: If run creation/update fails
        """
        session = self.context.session_ctx
        if not session:
            raise RuntimeError("Session not initialized")

        # Check if run already exists in session
        existing_run_id = session.run_id

        if existing_run_id:
            # Update existing run
            try:
                self.client.update_run(
                    run_id=existing_run_id,
                    status=RunStatus.STARTED,
                    attributes=attributes or {},
                )
                self.run_id = existing_run_id
                return existing_run_id
            except Exception as e:
                raise RuntimeError(f"Failed to update run {existing_run_id}: {e}") from e
        else:
            # Create new run
            try:
                response = self.client.create_run(
                    project_id=project_id,
                    name=name,
                    started_at=now_rfc3339(),
                    attributes=attributes or {},
                )
                run_id_raw = response.get("id")
                if not run_id_raw:
                    raise RuntimeError(f"'id' not found in response: {response}")

                # Cast to int for type safety
                run_id = int(run_id_raw)

                # Update session and local state
                session.run_id = run_id
                self.run_id = run_id
                return run_id

            except Exception as e:
                raise RuntimeError(f"Run creation failed for project {project_id}: {e}") from e

    def finish_run(
        self,
        *,
        status: RunStatus = RunStatus.FINISHED,
        error_message: str | None = None,
    ) -> None:
        """Finalize a run with final status and attributes.

        Args:
            status: Final run status
            error_message: Optional error message

        Raises:
            RuntimeError: If run finalization fails
        """
        session = self.context.session_ctx
        if not session:
            logger.error("Cannot finish run: session not initialized")
            return

        run_id = self.run_id or session.run_id
        if not run_id:
            logger.error("Cannot finish run: run_id not found")
            return

        # Merge error message into attributes if provided
        if error_message is not None:
            from ..constants import PredefinedAttribute

            self.context.set_run_attribute(PredefinedAttribute.ERROR_MESSAGE.value, error_message)

        # Get final attributes from session
        final_attrs = self.context.get_run_attributes()
        run_name = self.context.get_run_name()

        try:
            self.client.update_run(
                run_id=run_id,
                name=run_name,
                status=status,
                ended_at=now_rfc3339(),
                attributes=final_attrs,
            )
            logger.info(f"Run {run_id} finalized with status {status.value}")
        except Exception as e:
            raise RuntimeError(f"Failed to finalize run {run_id}: {e}") from e

    def get_run_id(self) -> int | None:
        """Get current run ID.

        Returns:
            Current run ID or None if no run started
        """
        return self.run_id
