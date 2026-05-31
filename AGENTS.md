Uses uv. Run tests:

    just test

Run the tool:

    uv run agent-log-gif json tests/sample_session.jsonl -o tmp/test.gif

Lint and format (also runs via git hook):

    just lint

All commands: `just --list`

Practice TDD: failing test first, then implementation. Bundle test + code + docs in one commit.

Put generated output for review (GIFs, MP4s, renders) in the repo's `tmp/` dir (gitignored). A repo-relative path works everywhere: it resolves to `/workspace/tmp` in the devcontainer and `tmp/` under the repo on a native checkout.

Web UI (`web/`): use the `agent-browser` skill to verify the frontend visually, and write Playwright e2e tests for it. Use `bun` for any JS dependency/build tooling (not npm/yarn/pnpm); check before installing Playwright or other tools.
