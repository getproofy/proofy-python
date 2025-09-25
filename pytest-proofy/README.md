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

Or install from the unified package:

```bash
pip install proofy-python[pytest]
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

# Batch options
--proofy-batch-size N               # Results per batch (default: 10)

# Feature options
--proofy-disable-attachments        # Disable attachment processing
--proofy-disable-hooks              # Disable plugin hooks

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
[tool:pytest]
proofy_mode = lazy
proofy_api_base = https://api.proofy.dev
proofy_token = your-token-here
proofy_project_id = 123
proofy_batch_size = 20
proofy_output_dir = test-artifacts
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
- (add info about testing time saving)

### Batch Mode

Groups results and sends in configurable batches:

```bash
pytest --proofy-mode batch --proofy-batch-size 50
```

- Collects results during execution
- Sends results in batches (during test ??)
- Optimized for large test suites
- Configurable batch size

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
    add_tag, add_attributes, add_attachment
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
            mime_type="image/png"
        )

    add_attributes(
        execution_time=result.duration,
        environment="staging"
    )
```

### Convenience Decorators

```python
from proofy import critical, smoke, regression

@critical  # Same as @severity("critical")
@smoke     # Same as @tags("smoke")
def test_critical_smoke():
    pass

@regression  # Same as @tags("regression")
def test_regression_case():
    pass
```

## Attachments

Add files to test results for better debugging:

```python
from proofy import add_attachment

def test_with_attachments():
    # Your test code
    take_screenshot("failure.png")
    save_logs("test.log")

    # Add attachments
    add_attachment("failure.png", name="Failure Screenshot")
    add_attachment("test.log", name="Test Logs", mime_type="text/plain")
```

## Integration Examples

### Selenium Tests

```python
import pytest
from selenium import webdriver
from proofy import add_attachment, set_severity, tags

class TestWebApp:
    @pytest.fixture
    def driver(self):
        driver = webdriver.Chrome()
        yield driver
        driver.quit()

    @set_severity("critical")
    @tags("ui", "smoke")
    def test_login_page(self, driver):
        driver.get("https://app.example.com/login")

        # Test logic
        assert "Login" in driver.title

        # Add screenshot on failure
        if hasattr(self, '_pytest_failed'):
            screenshot = driver.get_screenshot_as_png()
            with open("login_failure.png", "wb") as f:
                f.write(screenshot)
            add_attachment("login_failure.png", name="Login Failure")
```

### API Tests

```python
import requests
from proofy import description, add_attributes, add_attachment

@description("Test user creation API endpoint")
def test_create_user_api():
    response = requests.post("/api/users", json={
        "name": "Test User",
        "email": "test@example.com"
    })

    # Add response details as attributes
    add_attributes(
        status_code=response.status_code,
        response_time=response.elapsed.total_seconds(),
        endpoint="/api/users"
    )

    # Save response for debugging
    with open("api_response.json", "w") as f:
        f.write(response.text)
    add_attachment("api_response.json", name="API Response")

    assert response.status_code == 201
```

## Hook System Integration

Create custom plugins using the hook system:

```python
from proofy import hookimpl, get_plugin_manager

class CustomProofyPlugin:
    @hookimpl
    def proofy_test_start(self, test_id, test_name, test_path):
        print(f"Starting test: {test_name}")

    @hookimpl
    def proofy_test_finish(self, test_result):
        if test_result.outcome == "failed":
            print(f"Test failed: {test_result.name}")

    @hookimpl
    def proofy_add_attachment(self, test_id, file_path, name, mime_type):
        print(f"Attachment added: {name}")

# Register the plugin
pm = get_plugin_manager()
pm.register_plugin(CustomProofyPlugin())
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**

   ```bash
   # Verify token is correct
   curl -H "Authorization: Bearer YOUR_TOKEN" https://api.proofy.dev/health
   ```

2. **Connection Issues**

   ```bash
   # Test with increased timeout
   pytest --proofy-timeout 60
   ```

3. **Large Test Suites**
   ```bash
   # Use batch mode with larger batches
   pytest --proofy-mode batch --proofy-batch-size 100
   ```

### Debug Mode

Enable debug output:

```bash
pytest --proofy-mode lazy -v -s
```

### Local Backup

Always create local backups:

```bash
pytest --proofy-always-backup --proofy-output-dir ./test-results
```

## API Compatibility

This plugin is compatible with Proofy API v1:

- **POST /v1/runs** - Create test runs
- **PATCH /v1/runs/{run_id}** - Update runs
- **POST /v1/runs/{run_id}/results** - Create test results
- **PATCH /v1/runs/{run_id}/results/{result_id}** - Update results

Status mappings:

- pytest `passed` → `PASSED (1)`
- pytest `failed` → `FAILED (2)`
- pytest `error` → `BROKEN (3)`
- pytest `skipped` → `SKIPPED (4)`

## Development

### Installation for Development

```bash
git clone <repository>
cd pytest-proofy

# Install in development mode
pip install -e .[dev]

# Run tests
pytest tests/

# Type checking
mypy pytest_proofy/

# Linting
ruff check pytest_proofy/
```

### Testing the Plugin

```bash
# Test with a simple test file
pytest tests/test_example.py --proofy-mode lazy -v
```

## License

MIT License - see [LICENSE](../LICENSE) file for details.
