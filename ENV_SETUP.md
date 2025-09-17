# Environment Configuration Setup

This guide shows how to configure the Proofy plugin using environment variables for local testing.

## Quick Setup

1. **Copy the configuration template:**

   ```bash
   cp proofy.config.template .env
   ```

2. **Edit `.env` with your actual values:**

   ```bash
   # Required for API integration
   PROOFY_API_BASE=https://your-api.proofy.io
   PROOFY_TOKEN=your_actual_token_here
   PROOFY_PROJECT_ID=your_project_id
   ```

3. **Load environment variables:**

   ```bash
   # For bash/zsh
   export $(cat .env | xargs)

   # Or use a tool like direnv
   echo "source_env" >> .envrc
   direnv allow
   ```

## Configuration Options

### API Settings

- `PROOFY_API_BASE` - Base URL for Proofy API
- `PROOFY_TOKEN` - Authentication token
- `PROOFY_PROJECT_ID` - Project ID (integer)

### Plugin Behavior

- `PROOFY_MODE` - Operation mode: `live`, `lazy`, or `batch`
- `PROOFY_BATCH_SIZE` - Number of results to batch (default: 10)
- `PROOFY_TIMEOUT_S` - API timeout in seconds (default: 30.0)
- `PROOFY_MAX_RETRIES` - Maximum retry attempts (default: 3)
- `PROOFY_RETRY_DELAY` - Delay between retries in seconds (default: 1.0)

### Features

- `PROOFY_ENABLE_ATTACHMENTS` - Enable file attachments (`true`/`false`)
- `PROOFY_ENABLE_HOOKS` - Enable hook system (`true`/`false`)

### Local Backup

- `PROOFY_ALWAYS_BACKUP` - Always create local backup (`true`/`false`)
- `PROOFY_OUTPUT_DIR` - Directory for local results (default: `./proofy-artifacts`)

### Run Configuration

- `PROOFY_RUN_ID` - Use existing run ID (optional)
- `PROOFY_RUN_NAME` - Custom run name (optional)

## Priority Order

Configuration values are resolved in this priority order:

1. **Command Line Arguments** (highest)
2. **Environment Variables**
3. **pytest.ini settings**
4. **Default values** (lowest)

## Boolean Values

Environment variables support these boolean formats:

- **True**: `true`, `1`, `yes`, `on` (case-insensitive)
- **False**: `false`, `0`, `no`, `off`, or empty

## Testing Configuration

Run the configuration test to verify your setup:

```bash
python3 test_env_config.py
```

## Example Usage

### Local Development (with backup only)

```bash
export PROOFY_MODE=batch
export PROOFY_ALWAYS_BACKUP=true
export PROOFY_OUTPUT_DIR=./test-results

pytest tests/ --proofy-mode batch
```

### API Integration Testing

```bash
export PROOFY_API_BASE=https://api.proofy.io
export PROOFY_TOKEN=your_token
export PROOFY_PROJECT_ID=123
export PROOFY_MODE=live

pytest tests/ -v
```

### xdist Parallel Testing

```bash
export PROOFY_MODE=batch
export PROOFY_ALWAYS_BACKUP=true

pytest tests/ -n auto  # Uses all CPU cores
```

## Troubleshooting

### Configuration Not Loading

1. Verify environment variables are set: `env | grep PROOFY`
2. Check priority conflicts (CLI args override env vars)
3. Run the test script: `python3 test_env_config.py`

### Boolean Values Not Working

- Use lowercase: `PROOFY_ALWAYS_BACKUP=true` (not `True`)
- Avoid quotes unless necessary: `true` not `"true"`

### API Connection Issues

1. Verify `PROOFY_API_BASE` and `PROOFY_TOKEN`
2. Test with `PROOFY_ALWAYS_BACKUP=true` for local-only mode
3. Check network connectivity and API endpoint

## Integration with CI/CD

### GitHub Actions

```yaml
env:
  PROOFY_API_BASE: ${{ secrets.PROOFY_API_BASE }}
  PROOFY_TOKEN: ${{ secrets.PROOFY_TOKEN }}
  PROOFY_PROJECT_ID: ${{ secrets.PROOFY_PROJECT_ID }}
  PROOFY_MODE: batch

steps:
  - name: Run tests with Proofy
    run: pytest tests/ -n auto
```

### Jenkins

```groovy
environment {
    PROOFY_API_BASE = credentials('proofy-api-base')
    PROOFY_TOKEN = credentials('proofy-token')
    PROOFY_PROJECT_ID = '123'
    PROOFY_MODE = 'live'
}
```
