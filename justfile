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
    djhtml --tabwidth=2 web/

# Check linting without fixing (for CI)
lint-check:
    ruff check .
    ruff format --check .
    djhtml --tabwidth=2 --check web/

# === Profiling ===

# Profile memory and timing for the animation pipeline
profile *args:
    python scripts/profile_memory.py "$@"

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

# Run web UI e2e tests (fast UI tests only, skip slow Pyodide pipeline tests)
test-web:
    pytest tests/test_web_ui.py -m "not slow" "$@"

# Run web UI e2e tests including slow full-pipeline tests
test-web-full:
    pytest tests/test_web_ui.py "$@"

# === Web ===

# Install JS dependencies and copy WASM artifacts into place
install-js:
    bun install
    cp node_modules/gifsicle-wasm/dist/gifsicle.js web/lib/gifsicle/gifsicle.js
    cp node_modules/gifsicle-wasm/dist/gifsicle.wasm web/lib/gifsicle/gifsicle.wasm

# Build the web bundle (agent_log_gif.zip for Pyodide)
build-web:
    bash scripts/build_web.sh

# Serve the web UI locally (rebuild bundle first)
serve: build-web
    cd web && python3 -m http.server 8000
