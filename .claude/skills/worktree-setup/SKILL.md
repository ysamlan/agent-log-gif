---
name: worktree-setup
description: Set up a git worktree for isolated development on agent-log-gif. Use this skill whenever you're working in a fresh worktree or isolated environment — covers venv creation, dependency sync, and verification. Trigger when entering a worktree, when setup fails in a worktree, or when the user mentions worktree setup.
metadata:
  internal: true
---

# Worktree / Fresh Environment Setup

When working in a git worktree or fresh environment for agent-log-gif, follow these steps. The key requirement is that each worktree gets its own virtualenv — never share the main repo's venv.

## Quick Setup

```bash
# 1. Create an isolated venv pinned to this worktree
export UV_PROJECT_ENVIRONMENT=".venv_devcontainer"
uv venv "$UV_PROJECT_ENVIRONMENT"
uv sync

# 2. Verify everything works
uv run pytest tests/ -q --tb=short
```

## Why a Separate Venv?

Each worktree **must** have its own venv. If worktrees share a venv with the main repo, editable installs (`pip install -e .`) will point at whichever source tree was installed last, causing confusing import mismatches. Set `UV_PROJECT_ENVIRONMENT` so all `uv` commands in that shell use the worktree-local venv:

```bash
export UV_PROJECT_ENVIRONMENT=".venv_devcontainer"
```

The `.venv_devcontainer/` directory is already gitignored project-wide.

## Pre-commit Hooks

If pre-commit hooks fail in a worktree with "venv not found" errors, it's because the hook is looking for the venv at the worktree root. Fix: run `uv venv .venv_devcontainer && uv sync` in the worktree.

## Running the Tool in a Worktree

Same commands as the main repo — `just` and `uv run` work as normal once the venv is set up:

```bash
just test                    # run tests
just lint                    # lint and format
uv run agent-log-gif json tests/sample_session.jsonl -o /tmp/test.gif
```

## Worktree Working Directories

Claude Code agent worktrees live under `.claude/worktrees/` and are gitignored.
