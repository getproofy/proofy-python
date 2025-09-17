# Proofy Commons

Shared components for Proofy Python testing framework integrations.

## Overview

`proofy-commons` provides the foundational components used by all Proofy framework adapters:

- **Core**: API client, data models, and enums
- **Hooks**: Plugin system based on pluggy for extensibility
- **Runtime**: Context management, decorators, and runtime API
- **Config**: Configuration management (future)
- **Export**: Result export utilities (future)

## Installation

```bash
pip install proofy-commons
```

## Quick Start

### Basic Usage

```python
from proofy import ProofyClient, TestResult, ResultStatus

# Create client
client = ProofyClient(
    base_url="https://api.proofy.io",
    token="your-token-here"
)

# Create test result
result = TestResult(
    id="test_example",
    name="Example Test",
    path="/tests/test_example.py",
    outcome="passed"
)

# Send result
response = client.send_test_result(result)
```

### Runtime API

```python
from proofy.runtime import (
    add_attachment,
    set_description,
    set_severity,
    add_tag
)

def test_example():
    # Set test metadata
    set_description("This test validates user authentication")
    set_severity("critical")
    add_tag("auth")

    # Your test code here
    assert user.login("valid_user", "valid_pass")

    # Add attachment
    add_attachment("screenshot.png", name="success_screenshot")
```

### Decorators

```python
from proofy.decorators import name, description, severity, tags

@name("User Authentication Test")
@description("Validates login functionality with various scenarios")
@severity("critical")
@tags("auth", "smoke")
def test_user_authentication():
    # Test implementation
    pass
```

### Hook System

```python
from proofy import hookimpl, get_plugin_manager

class MyPlugin:
    @hookimpl
    def proofy_test_start(self, test_id, test_name, test_path):
        print(f"Starting test: {test_name}")

    @hookimpl
    def proofy_test_finish(self, test_result):
        print(f"Finished test: {test_result.name} -> {test_result.outcome}")

# Register plugin
pm = get_plugin_manager()
pm.register_plugin(MyPlugin())
```

## Architecture

### Core Components

- **ProofyClient**: Unified API client supporting both sync and async patterns
- **TestResult**: Comprehensive test result model with backward compatibility
- **Enums**: ResultStatus, RunStatus, ProofyAttributes for type safety

### Hook System

Based on `pluggy`, provides framework-agnostic extension points:

- Test lifecycle hooks (start, finish, update)
- Session lifecycle hooks (start, finish)
- Attachment hooks (add, uploaded)
- Metadata hooks (attributes, name, description, severity, tags)

### Runtime Context

Thread-local context management for test execution:

- **TestContext**: Per-test metadata and state
- **SessionContext**: Per-session metadata and test collection
- Context stack for nested scenarios

## API Reference

### Core Models

#### TestResult

```python
@dataclass
class TestResult:
    # Core identification
    id: str                           # Local ID (nodeid)
    name: str                         # Display name
    path: str                         # Test file path

    # Server integration
    server_id: Optional[int] = None   # Server-assigned ID
    run_id: Optional[int] = None      # Run ID

    # Execution details
    outcome: Optional[str] = None     # passed, failed, skipped, error
    status: Optional[ResultStatus] = None  # Enum format

    # Timing
    duration_ms: Optional[float] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    # Related data
    attachments: List[Attachment] = field(default_factory=list)
    fixtures: List[FixtureResult] = field(default_factory=list)
```

#### ProofyClient

```python
class ProofyClient:
    def __init__(self, base_url: str, token: Optional[str] = None, timeout_s: float = 10.0)

    # Current project compatibility
    def send_test_result(self, result: TestResult) -> requests.Response
    def send_test_results(self, results: Iterable[TestResult]) -> requests.Response
    def get_presigned_url(self, filename: str) -> requests.Response

    # Old project compatibility (returns server IDs)
    def create_test_result(self, run_id: int, ...) -> int
    def create_test_result_batches(self, run_id: int, results: List[TestResult]) -> List[Dict]
    def update_test_result(self, result_id: int, ...) -> Dict
    def add_attachment(self, result_id: int, ...) -> Dict
```

### Runtime API

#### Metadata Functions

```python
def set_name(name: str, test_id: Optional[str] = None) -> None
def set_description(description: str, test_id: Optional[str] = None) -> None
def set_severity(severity: str, test_id: Optional[str] = None) -> None
def add_metadata(key: str, value: Any, test_id: Optional[str] = None) -> None
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

def add_file(
    file: Union[str, Path],
    *,
    name: str,
    content_type: Optional[str] = None,
    test_id: Optional[str] = None,
) -> None
```

### Hook Specifications

```python
class ProofyHookSpecs:
    @hookspec
    def proofy_test_start(self, test_id: str, test_name: str, test_path: str) -> None

    @hookspec
    def proofy_test_finish(self, test_result: TestResult) -> None

    @hookspec
    def proofy_add_attachment(self, test_id: str, file_path: str, name: str) -> None

    @hookspec
    def proofy_add_attributes(self, test_id: Optional[str], attributes: Dict[str, Any]) -> None

    # ... and many more
```

## Development

### Setup

```bash
git clone <repository>
cd proofy-python-unified/proofy-commons

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e .[dev]
```

### Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=proofy --cov-report=html

# Type checking
mypy proofy

# Linting and formatting
ruff check --fix
ruff format
```

## License

MIT License - see [LICENSE](../LICENSE) file for details.
