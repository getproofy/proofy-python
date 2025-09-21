from datetime import datetime


def format_datetime_rfc3339(dt: datetime | str) -> str:
    """Format datetime to RFC 3339 format."""
    if isinstance(dt, str):
        return dt  # Already formatted, assume it's correct

    return dt.isoformat().replace("+00:00", "Z")
