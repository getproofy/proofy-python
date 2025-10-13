# Proofy Commons

Shared components for Proofy Python testing framework integrations.

## Overview

`proofy-commons` provides the foundational components used by all Proofy framework adapters.

Only the functions re-exported from `proofy` are part of the public API. Everything else is considered internal and may change without notice.

## Installation

```bash
pip install proofy
```

## Public API (from `proofy`)

These are the only supported, stable entry points:

```python
from proofy import (
    # Metadata
    set_name, set_description, set_severity,
    add_tag, add_tags, add_attributes,
    set_run_name,

    # Run-level metadata
    set_run_attribute, add_run_attributes, get_run_attributes,

    # Attachments
    add_attachment, add_data

    # Context info
    get_current_run_id, get_current_test_id,

    # Decorators
    name, title, description, severity, tags, attributes,
)
```

### Examples

#### Runtime usage

```python
from proofy import add_attachment, set_description, add_attributes

def test_example():
    set_description("This test validates user authentication")
    add_attributes(severity="critical", component="auth")
    # ... your test ...
    add_attachment("screenshot.png", name="success_screenshot")
```

#### Decorators

```python
from proofy import name, description, severity, tags, attributes

@name("User Authentication Test")
@description("Validates login functionality with various scenarios")
@severity("critical")
@tags("auth", "smoke")
@attributes(component="auth", area="login")
def test_user_authentication():
    pass
```

#### Run Attributes

Run attributes allow you to add metadata to the entire test run (not individual tests):

```python
import proofy

# Set individual run attribute
proofy.set_run_attribute("environment", "production")

# Set multiple run attributes at once
proofy.add_run_attributes(
    version="1.2.3",
    build_number="456",
    branch="main",
    tested_by="CI"
)

# Get all run attributes
attrs = proofy.get_run_attributes()
print(attrs)  # {'environment': 'production', 'version': '1.2.3', ...}
```

**Note:** Run attributes should be set before or during session start (e.g., in `conftest.py` for pytest). The system also automatically collects system information like Python version, OS, and framework version.

## Architecture

Internal structure includes clients, models, hooks, context, I/O, and export utilities that support the public API. These are subject to change and are not part of the stable surface.

## Notes

- The HTTP client, models, hooks, and other internals are intentionally undocumented here.
- Use the framework plugins (e.g., `pytest-proofy`) for integration and configuration options.

### Runtime API

#### Metadata Functions

```python
def set_name(name: str, test_id: Optional[str] = None) -> None
def set_description(description: str, test_id: Optional[str] = None) -> None
def set_severity(severity: str, test_id: Optional[str] = None) -> None
def add_attributes(test_id: Optional[str] = None, **kwargs: Any) -> None
def add_tag(tag: str, test_id: Optional[str] = None) -> None
def add_tags(tags: List[str], test_id: Optional[str] = None) -> None
```

#### Attachment Functions

```python
def add_attachment(
    file: Union[str, Path],
    *,
    name: str,
    mime_type: Optional[str] = None,
    test_id: Optional[str] = None,
) -> None
```

```python
def add_data(
    data: str | bytes | bytearray | dict[str, Any],
    *,
    name: str,
    mime_type: Optional[str] = None,
    extension: Optional[str] = None,
    artifact_type: ArtifactType | int = ArtifactType.ATTACHMENT,
    encoding: str = "utf-8",
) -> None
```

## Development

### Setup

```bash
git clone <repository>
cd proofy-python/proofy-commons
uv venv .venv
source .venv/bin/activate
uv pip install -e '.[dev]'
```

### Testing

```bash
# Run tests
uv run -q pytest

# Run with coverage
uv run -q pytest --cov=proofy --cov-report=html

# Type checking
uv run -q mypy proofy

# Linting and formatting
uv run -q ruff check --fix
uv run -q ruff format
```

## License

Apache-2.0 — see [LICENSE](../LICENSE) file for details.
