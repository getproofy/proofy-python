# Proofy Python Unified

A unified framework for integrating Proofy test reporting with multiple Python testing frameworks.

## Supported Frameworks

- ✅ **pytest** - Full featured pytest plugin
- 🚧 **behave** - BDD testing with Gherkin syntax
- 🚧 **unittest** - Standard Python unittest framework
- 🚧 **nose2** - Unittest with plugin system

## Architecture

```
proofy-python-unified/
├── proofy-commons/          # Shared components
│   ├── proofy/
│   │   ├── core/           # Client, models, processing
│   │   ├── hooks/          # Plugin system (pluggy)
│   │   ├── runtime/        # Context, decorators, API
│   │   ├── config/         # Configuration management
│   │   └── export/         # JSON/ZIP export utilities
│   └── tests/
├── pytest-proofy/          # Pytest adapter
├── behave-proofy/           # Behave adapter
├── unittest-proofy/         # Unittest adapter
└── nose2-proofy/            # Nose2 adapter
```

## Key Features

### Dual Processing System

- **Live Mode**: Synchronous operations for real-time updates
- **Lazy/Batch Mode**: Asynchronous background processing
- **Smart Mode Selection**: Automatic based on configuration

### Unified API

- Consistent interface across all testing frameworks
- Server-generated ID support for live updates
- Rich attachment and metadata support
- Flexible configuration hierarchy

### Hook System

- Extensible plugin architecture using pluggy
- Framework-agnostic hook specifications
- Easy custom plugin development

## Quick Start

### Installation

```bash
# Install with specific framework support
pip install proofy-python-unified[pytest]
pip install proofy-python-unified[behave]
pip install proofy-python-unified[unittest]
pip install proofy-python-unified[nose2]

# Install with all frameworks
pip install proofy-python-unified[all]
```

### Basic Usage

#### Pytest

```bash
pytest --proofy-url https://api.proofy.io --proofy-token YOUR_TOKEN --proofy-mode live
```

#### Behave

```bash
behave -D proofy.url=https://api.proofy.io -D proofy.token=YOUR_TOKEN
```

### Configuration

Configuration follows hierarchy: **CLI > ENV > config_file > defaults**

```ini
# pytest.ini / behave.ini / nose2.cfg
[proofy]
url = https://api.proofy.io
token = your_token_here
mode = lazy
batch_size = 10
enable_attachments = true
```

### Runtime API

```python
from proofy.runtime import add_attachment, set_description, add_attributes

def test_example():
    set_description("This is a comprehensive test")
    add_attributes(severity="high", component="auth")

    # Your test code here

    add_attachment("screenshot.png", name="failure_screenshot")
```

### Decorators

```python
from proofy import name, description, severity

@name("User Login Test")
@description("Tests user authentication flow")
@severity("critical")
def test_user_login():
    # Test implementation
    pass
```

## Development

### Prerequisites

- Python 3.12+
- uv (recommended) or pip

### Setup

```bash
git clone <repository>
cd proofy-python-unified

# Using uv (recommended)
uv venv .venv
source .venv/bin/activate
uv pip install -e ./proofy-commons -e ./pytest-proofy -e .[dev]

# Using pip
python -m venv .venv
source .venv/bin/activate
pip install -e ./proofy-commons -e ./pytest-proofy -e .[dev]
```

### Testing

```bash
# Run all tests
pytest

# Run specific component tests
pytest proofy-commons/tests
pytest pytest-proofy/tests

# Run with coverage
pytest --cov=proofy --cov-report=html
```

### Code Quality

```bash
# Format and lint
ruff format
ruff check --fix

# Type checking
mypy

# All quality checks
pre-commit run --all-files
```

## Modes

### Live Mode

- Creates test results immediately when test starts
- Real-time updates during test execution
- Synchronous attachment uploads
- Best for interactive development and debugging

### Lazy Mode (Default)

- Collects results and sends after test completion
- Background processing for better performance
- Automatic retry with exponential backoff
- Best for CI/CD environments

### Batch Mode

- Groups results and sends in configurable batches
- Optimized for large test suites
- Balances performance and real-time visibility
- Best for performance-critical environments

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes with tests
4. Ensure code quality: `ruff format && ruff check && mypy`
5. Run tests: `pytest`
6. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Documentation

- [Implementation Plan](IMPLEMENTATION_PLAN.md) - Detailed development roadmap
- [Framework Analysis](FRAMEWORK_ANALYSIS.md) - Technical analysis and decisions
- [API Reference](docs/api.md) - Complete API documentation
- [Examples](examples/) - Usage examples for each framework
