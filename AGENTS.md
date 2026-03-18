Uses uv. Run tests like this:

    just test

Or directly:

    uv run pytest

Run the development version of the tool like this:

    uv run agent-log-gif --help

Always practice TDD: write a failing test, watch it fail, then make it pass.

Commit early and often. Commits should bundle the test, implementation, and documentation changes together.

Run linting and formatting before you commit (also runs automatically via git hook):

    just lint

For all available commands: `just --list`
