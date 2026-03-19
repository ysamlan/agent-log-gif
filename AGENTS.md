Uses uv. Run tests:

    just test

Run the tool:

    uv run agent-log-gif json tests/sample_session.jsonl -o /tmp/test.gif

Lint and format (also runs via git hook):

    just lint

All commands: `just --list`

Practice TDD: failing test first, then implementation. Bundle test + code + docs in one commit.
