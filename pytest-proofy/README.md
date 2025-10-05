# pytest-proofy

Pytest plugin for Proofy test reporting with real-time results and rich metadata support.

## Features

- **Multiple Reporting Modes**: Live, Lazy, and Batch reporting
- **Rich Metadata**: Decorators for test description, severity, tags, and custom attributes
- **Attachment Support**: Add screenshots, logs, and other files to test results
- **Hook System**: Extensible plugin architecture via proofy
- **Flexible Configuration**: CLI, environment variables, and pytest.ini support
- **Local Backup**: Automatic fallback to local JSON export

## Installation

```bash
pip install pytest-proofy
```

## Quick Start

### Basic Usage

```bash
pytest --proofy-api-base https://api.proofy.dev \
       --proofy-token YOUR_TOKEN \
       --proofy-project-id 123 \
       --proofy-mode live
```

### Configuration

#### Command Line Options

```bash
# Core options
--proofy-mode {live,batch,lazy}     # Reporting mode
--proofy-api-base URL               # Proofy API base URL
--proofy-token TOKEN                # API authentication token
--proofy-project-id ID              # Project ID

# Run options
--proofy-run-id ID                  # Existing run ID to append to
--proofy-run-name NAME              # Custom run name
--proofy-run-attributes ATTRS       # Custom run attributes (key=value,key2=value2)

# Batch options
--proofy-batch-size N               # Results per batch (default: 10)

# Output options
--proofy-output-dir DIR             # Local backup directory
--proofy-always-backup              # Always create local backup
```

#### Environment Variables

```bash
export PROOFY_MODE=live
export PROOFY_API_BASE=https://api.proofy.dev
export PROOFY_TOKEN=your-token-here
export PROOFY_PROJECT_ID=123
```

#### pytest.ini Configuration

```ini
[pytest]
proofy_mode = lazy
proofy_api_base = https://api.proofy.dev
proofy_token = your-token-here
proofy_project_id = 123
proofy_batch_size = 20
proofy_output_dir = test-artifacts
proofy_run_attributes = environment=staging,version=1.2.3
```

## Reporting Modes

### Live Mode

Real-time test reporting with immediate server updates:

```bash
pytest --proofy-mode live
```

- Creates test result when test starts (IN_PROGRESS status)
- Updates result when test finishes with final outcome
- Uploads attachments immediately
- Best for interactive development and debugging

### Lazy Mode (Default)

Sends complete results after test execution:

```bash
pytest --proofy-mode lazy
```

- Collects results during execution
- Sends all results in batches at session end
- Best for CI/CD environments

### Batch Mode

Groups results and sends in configurable batches:

```bash
pytest --proofy-mode batch --proofy-batch-size 50
```

- Collects results during execution
- Sends results in batches
- Optimized for large test suites
- Configurable batch size

## Run Attributes

Run attributes allow you to add metadata to your test runs, such as environment information, version numbers, and other custom data. Proofy automatically collects system information (Python version, OS, framework version) and allows you to add custom attributes.

### Automatic System Attributes

The following attributes are automatically collected for every run:

- `__proofy_python_version` - Python version (e.g., "3.11.0")
- `__proofy_platform` - Platform details (e.g., "macOS-14.0-arm64")
- `__proofy_framework` - Test framework (e.g., "pytest")
- `__proofy_framework_version` - Framework version (e.g., "7.4.0")

### Adding Custom Run Attributes

#### Via Command Line

```bash
pytest --proofy-run-attributes environment=production,version=1.2.3,branch=main
```

#### Via Environment Variable

```bash
export PROOFY_RUN_ATTRIBUTES="environment=staging,version=2.0.0"
pytest
```

#### Via pytest.ini

```ini
[pytest]
proofy_run_attributes = environment=development,team=backend
```

#### Via conftest.py

```python
# conftest.py
import proofy

def pytest_sessionstart(session):
    """Set run attributes at session start."""
    proofy.add_run_attributes(
        environment="staging",
        version="1.2.3",
        build_number="456",
        branch="feature/new-api"
    )
```

#### Via Runtime API in Tests

```python
import proofy

def test_example():
    # You can also set run attributes from within tests
    # (though this is less common - usually set at session start)
    proofy.set_run_attribute("custom_key", "custom_value")
    proofy.add_run_attributes(
        environment="production",
        region="us-east-1"
    )

    # Get all run attributes
    attrs = proofy.get_run_attributes()
    assert "environment" in attrs
```

## Using Decorators and Runtime API

### Decorators

```python
from proofy import name, description, severity, tags, attributes

@name("User Login Test")
@description("Validates user authentication with valid credentials")
@severity("critical")
@tags("auth", "smoke")
@attributes(component="auth", browser="chrome")
def test_user_login():
    # Test implementation
    assert login("user", "pass") == True
```

### Runtime API

```python
from proofy import (
    set_name, set_description, set_severity,
    add_tag, add_attributes, add_attachment, ArtifactType
)


def test_dynamic_metadata():
    set_name("Dynamic Test Name")
    set_description("This description is set at runtime")
    set_severity("high")

    # Test logic here
    result = perform_test()

    if result.screenshot:
        add_attachment(
            result.screenshot,
            name="test_screenshot",
            mime_type="image/png",
            artifact_type=ArtifactType.SCREENSHOT
        )

    add_attributes(
        execution_time=result.duration,
        environment="staging"
    )
```

## Attachments

Add files to test results for better debugging:

```python
from proofy import add_attachment, ArtifactType


def test_with_attachments():
    # Your test code
    take_screenshot("failure.png")
    save_logs("test.log")

    # Add attachments
    add_attachment("failure.png", name="Failure Screenshot", artifact_type=ArtifactType.SCREENSHOT)
    add_attachment("test.log", name="Test Logs", mime_type="text/plain")
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**

   ```bash
   # Verify token is correct
   curl -H "Authorization: Bearer YOUR_TOKEN" https://api.proofy.dev/health
   ```

2. **Large Test Suites**

   ```bash
   # Use batch mode with larger batches
   pytest --proofy-mode batch --proofy-batch-size 100
   ```

### Debug Mode

```bash
pytest --proofy-mode lazy -v -s
```

### Local Backup

```bash
pytest --proofy-always-backup --proofy-output-dir ./test-results
```

Status mappings:

- pytest `passed` → `PASSED (1)`
- pytest `failed` → `FAILED (2)`
- pytest `error` → `BROKEN (3)`
- pytest `skipped` → `SKIPPED (4)`

## Development

```bash
# In monorepo root
uv venv .venv && source .venv/bin/activate
uv pip install -e ../proofy-commons -e .[dev]
uv run -q pytest -n auto
```

## License

Apache-2.0 — see [LICENSE](../LICENSE) file for details.
