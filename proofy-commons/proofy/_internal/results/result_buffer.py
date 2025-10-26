"""Result buffering component for batch operations.

This module provides a simple buffer for accumulating result IDs
before batch sending, extracted from ResultsHandler for better separation of concerns.
"""

from __future__ import annotations


class ResultBuffer:
    """Buffer for accumulating results before batch sending.

    This component manages the collection of result IDs and provides
    a simple interface for checking when to flush based on batch size.
    """

    def __init__(self, batch_size: int = 100) -> None:
        """Initialize result buffer.

        Args:
            batch_size: Number of results to accumulate before flushing
        """
        self.batch_size = batch_size
        self.pending: list[str] = []

    def add_result(self, result_id: str) -> None:
        """Add a result ID to the buffer.

        Args:
            result_id: ID of the result to buffer
        """
        self.pending.append(result_id)

    def should_flush(self) -> bool:
        """Check if buffer should be flushed.

        Returns:
            True if buffer has reached batch_size threshold
        """
        return len(self.pending) >= self.batch_size

    def get_pending(self) -> list[str]:
        """Get copy of pending result IDs.

        Returns:
            List of pending result IDs
        """
        return self.pending.copy()

    def clear(self) -> None:
        """Clear the buffer."""
        self.pending = []

    def __len__(self) -> int:
        """Get number of pending results.

        Returns:
            Count of buffered results
        """
        return len(self.pending)
