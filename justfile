# Use uv to run all commands in the project's virtual environment
set shell := ['uv', 'run', 'bash', '-euxo', 'pipefail', '-c']
set positional-arguments

# Default recipe shows available commands
default:
    @just --list

# === Testing ===

# Run all tests
test *args:
    pytest "$@"

# Run tests with verbose output
test-v *args:
    pytest -v "$@"

# === Linting & Formatting ===

# Run linting and formatting (auto-fix)
lint:
    ruff check --fix .
    ruff format .

# Check linting without fixing (for CI)
lint-check:
    ruff check .
    ruff format --check .

# === Development ===

# Run the CLI tool
run *args:
    agent-log-gif "$@"

# Regenerate demo GIFs for the README
demos:
    python scripts/generate_demos.py

# Sync color schemes from iTerm2-Color-Schemes repo
sync-schemes:
    python scripts/sync_color_schemes.py

# Generate Python dependency license audit
licenses:
    python scripts/generate_licenses.py
