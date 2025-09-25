from datetime import datetime, timezone


def format_datetime_rfc3339(dt: datetime | str) -> str:
    """Format datetime to RFC 3339 format."""
    if isinstance(dt, str):
        return dt  # Already formatted, assume it's correct

    return dt.isoformat().replace("+00:00", "Z")


def now_rfc3339() -> str:
    """Return the current UTC time in RFC 3339 format.

    Uses timezone-aware UTC and emits the canonical 'Z' suffix.
    """
    return format_datetime_rfc3339(datetime.now(timezone.utc))
