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
[tool:pytest]
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
[tool:pytest]
proofy_run_attributes = environment=development,team=backend
```

#### Via conftest.py

```python
# conftest.py
import proofy

def pytest_configure(config):
    """Set run attributes programmatically."""
    # This runs after plugin initialization but before tests
    pass

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

### Common Use Cases

#### CI/CD Integration

```bash
# Jenkins/GitHub Actions
pytest \
  --proofy-run-attributes \
    "ci=true,\
     build_id=${BUILD_ID},\
     branch=${GIT_BRANCH},\
     commit=${GIT_COMMIT},\
     ci_job=${JOB_NAME}"
```

#### Environment-Specific Testing

```python
# conftest.py
import os
import proofy

def pytest_sessionstart(session):
    """Add environment-specific run attributes."""
    proofy.add_run_attributes(
        environment=os.getenv("TEST_ENV", "local"),
        database_url=os.getenv("DATABASE_URL", "local"),
        api_endpoint=os.getenv("API_ENDPOINT", "http://localhost"),
        test_suite="regression"
    )
```

#### Application Version Tracking

```python
# conftest.py
import proofy

def pytest_sessionstart(session):
    """Track application version being tested."""
    from myapp import __version__

    proofy.add_run_attributes(
        app_version=__version__,
        tested_at=datetime.now().isoformat(),
        tester=os.getenv("USER", "unknown")
    )
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
