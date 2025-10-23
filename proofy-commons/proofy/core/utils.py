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


def generate_test_identifier(test_path: str) -> str:
    """Generate a unique 16-character test identifier from test path using SHA256.

    Each runner should provide a standardized test path in the format:

    - pytest: "tests/test_file.py::TestClass::test_method"

    The important thing is that each test gets a unique, consistent path representation
    that includes the test file and test identifier.

    Args:
        test_path: A standardized test path string that uniquely identifies a test
                  across all test runners (e.g., file path + test name).
                  The format varies by runner but must be unique per test.

    Returns:
        A 16-character hex string derived from SHA256 hash of the test_path.
        This identifier is deterministic - the same test_path always produces
        the same identifier, enabling test tracking across multiple runs.
    """
    import hashlib

    hash_obj = hashlib.sha256(test_path.encode("utf-8"))
    hex_digest = hash_obj.hexdigest()
    # Take first 16 characters of the hex digest
    return hex_digest[:16]
