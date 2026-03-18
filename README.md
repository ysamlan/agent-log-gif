# agent-log-gif

[![PyPI](https://img.shields.io/pypi/v/agent-log-gif.svg)](https://pypi.org/project/agent-log-gif/)
[![Changelog](https://img.shields.io/github/v/release/ysamlan/agent-log-gif?include_prereleases&label=changelog)](https://github.com/ysamlan/agent-log-gif/releases)
[![Tests](https://github.com/ysamlan/agent-log-gif/workflows/Test/badge.svg)](https://github.com/ysamlan/agent-log-gif/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/ysamlan/agent-log-gif/blob/main/LICENSE)

Convert Claude Code or Codex session files (JSON or JSONL) to animated GIFs or videos.

Forked from [Simon Willison](https://simonwillison.net/)'s [claude-code-transcripts](https://github.com/simonw/claude-code-transcripts); all Claude Code transcript parsing logic is based on that work.

> [!WARNING]
>
> The `web` commands for both listing Claude Code for web sessions and converting those to a transcript are both broken right now due to changes to the unofficial and undocumented APIs that these commands were using. See upstream [issue #77](https://github.com/simonw/agent-log-gif/issues/77) for details.

## Installation

Install this tool using `uv`:
```bash
uv tool install agent-log-gif
```
Or run it without installing:
```bash
uvx agent-log-gif --help
```

## Usage

This tool converts Claude Code or Codex session files into animated gifs or videos.

There are four commands available:

- `local` (default) - select from local Claude Code sessions stored in `~/.claude/projects`
- `web` - select from web sessions via the Claude API
- `json` - convert a specific Claude Code or Codex JSON/JSONL session file
- `all` - convert all local sessions to a browsable HTML archive

The quickest way to view a recent local session:

```bash
agent-log-gif
```

This shows an interactive picker to select a session, generates a GIF, and opens it in your default browser.

### Output options

All commands support these options:

- `-o, --output DIRECTORY` - output directory (default: writes to temp dir and opens browser)
- `-a, --output-auto` - auto-name output subdirectory based on session ID or filename
- `--repo OWNER/NAME` - GitHub repo for commit links (auto-detected if not specified). For `web` command, also filters the session list.
- `--open` - open the generated `index.html` in your default browser (default if no `-o` specified)
- `--gist` - upload the generated HTML files to a GitHub Gist and output a preview URL
- `--json` - include the original session file in the output directory

The generated output includes:
- `session.gif` - animated version of the session

### Local sessions

Local Claude Code sessions are stored as JSONL files in `~/.claude/projects`. Run with no arguments to select from recent sessions:

```bash
agent-log-gif
# or explicitly:
agent-log-gif local
```

Use `--limit` to control how many sessions are shown (default: 10):

```bash
agent-log-gif local --limit 20
```

### Web sessions

Import sessions directly from the Claude API:

```bash
# Interactive session picker
agent-log-gif web

# Import a specific session by ID
agent-log-gif web SESSION_ID
```

The session picker displays sessions grouped by their associated GitHub repository:

```
simonw/datasette              2025-01-15T10:30:00  Fix the bug in query parser
simonw/llm                    2025-01-14T09:00:00  Add streaming support
(no repo)                     2025-01-13T14:22:00  General coding session
```

Use `--repo` to filter the session list to a specific repository:

```bash
agent-log-gif web --repo simonw/datasette
```

On macOS, API credentials are automatically retrieved from your keychain (requires being logged into Claude Code). On other platforms, provide `--token` and `--org-uuid` manually.

### Auto-naming output directories

Use `-a/--output-auto` to automatically create a subdirectory named after the session:

```bash
# Creates ./session_ABC123/ subdirectory
agent-log-gif web SESSION_ABC123 -a

# Creates ./transcripts/session_ABC123/ subdirectory
agent-log-gif web SESSION_ABC123 -o ./transcripts -a
```

### Including the source file

Use the `--json` option to include the original session file in the output directory:

```bash
agent-log-gif json session.json -o ./my-transcript --json
```

This will output:
```
JSON: ./my-transcript/session_ABC.json (245.3 KB)
```

This is useful for archiving the source data alongside the animated output.

### Converting from JSON/JSONL files

Convert a specific session file directly:

```bash
agent-log-gif json session.json -o output-directory/
agent-log-gif json session.jsonl --open
```
This works with:

- JSONL files in the `~/.claude/projects/` folder
- JSON session files extracted from Claude Code for web
- Codex JSONL session files such as those under `~/.codex/sessions/`

The `json` command can take a URL to a JSON or JSONL file as an alternative to a path on disk.

Codex support is currently file-based via `json`. The `local`, `web`, and `all` commands still target Claude Code sessions.

### Converting all sessions

Convert all your local Claude Code sessions to animated gifs:

```bash
agent-log-gif all
```

This creates a directory structure with:
- A master index listing all projects
- Per-project pages listing sessions
- Individual session transcripts

Options:

- `-s, --source DIRECTORY` - source directory (default: `~/.claude/projects`)
- `-o, --output DIRECTORY` - output directory (default: `./claude-archive`)
- `--include-agents` - include agent session files (excluded by default)
- `--dry-run` - show what would be converted without creating files
- `--open` - open the generated archive in your default browser
- `-q, --quiet` - suppress all output except errors

Examples:

```bash
# Preview what would be converted
agent-log-gif all --dry-run

# Convert all sessions and open in browser
agent-log-gif all --open

# Convert to a specific directory
agent-log-gif all -o ./my-archive

# Include agent sessions
agent-log-gif all --include-agents
```

## Development

To contribute to this tool, first checkout the code. You can run the tests using `uv run`:
```bash
cd agent-log-gif
uv run pytest
```
And run your local development copy of the tool like this:
```bash
uv run agent-log-gif --help
```
