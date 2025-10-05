## Proofy Python

A monorepo for Proofy’s Python ecosystem. It contains the shared core library and adapters for popular testing frameworks.

- Core library: published as `proofy-python`
- Pytest plugin: published as `pytest-proofy`
- Additional adapters (behave, unittest, nose2): work in progress

## Installation

```bash
# Core library (programmatic API, decorators, runtime helpers)
pip install proofy-python

# Pytest plugin (installs the core)
pip install pytest-proofy
```

Using uv:

```bash
uv add proofy-python
uv add pytest-proofy
```

## Project structure

```text
proofy-python/
├── proofy-commons/           # Shared core library (package: proofy)
│   └── proofy/               # Public API, clients, internal runtime
├── pytest-proofy/            # Pytest adapter (package: pytest_proofy)
├── behave-proofy/            # Behave adapter (WIP)
├── unittest-proofy/          # unittest adapter (WIP)
└── nose2-proofy/             # nose2 adapter (WIP)
```

## Configuration

Below are the global configuration parameters supported by Proofy integrations. How to set these (CLI flags, env vars, config files) is documented in each adapter’s README.

| Parameter          | Type                       | Default            | Description                                               |
| ------------------ | -------------------------- | ------------------ | --------------------------------------------------------- |
| mode               | enum[str]: live/batch/lazy | lazy               | Delivery mode controlling when results are sent           |
| api_base           | str                        | —                  | Base URL of the Proofy API (e.g., https://api.proofy.dev) |
| token              | str                        | —                  | Bearer token for API authentication                       |
| project_id         | int                        | —                  | Proofy project identifier                                 |
| batch_size         | int                        | 10                 | Number of results per batch (batch mode)                  |
| output_dir         | str                        | `proofy-artifacts` | Directory for local backup exports                        |
| always_backup      | bool                       | false              | Always create local backup files with results             |
| run_name           | str                        | —                  | Display name for the test run                             |
| run_attributes     | dict[str,str]              | —                  | Custom run metadata applied to the entire run             |
| enable_attachments | bool                       | true               | Enable attachment capture and upload                      |

## Development

### Prerequisites

- Python 3.12+
- uv (recommended) or pip

### Setup

```bash
git clone <repository>
cd proofy-python

# Using uv (recommended)
uv venv .venv
source .venv/bin/activate
uv pip install -e ./proofy-commons -e ./pytest-proofy -e .[dev]

# Using pip
python -m venv .venv
source .venv/bin/activate
pip install -e ./proofy-commons -e ./pytest-proofy -e .[dev]
```

### Testing (use uv)

```bash
# Core library tests
cd proofy-commons && uv run -q pytest -n auto

# Pytest plugin tests
cd ../pytest-proofy && uv run -q pytest -n auto

# From repo root (all suites)
cd .. && uv run -q pytest -n auto
```

### Code quality

```bash
ruff format
ruff check --fix
mypy
pre-commit run --all-files
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Add tests covering your change
4. Ensure quality: `ruff format && ruff check && mypy`
5. Run tests with uv: `uv run -q pytest -n auto`
6. Open a pull request

## License

Apache-2.0 — see [LICENSE](LICENSE).
