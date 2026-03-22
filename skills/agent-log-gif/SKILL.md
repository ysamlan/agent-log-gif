---
name: agent-log-gif
description: >
  Generate animated GIF/MP4/AVIF terminal replays from Claude Code or Codex sessions.
  Use this skill whenever the user wants to create a GIF, animation, video, or visual
  replay of a coding session — whether they say "make a gif of my session", "animate
  that conversation", "create a terminal recording", "share a replay", or reference
  agent-log-gif directly. Also trigger when users want to find, search, or browse
  their Claude Code or Codex sessions for visualization purposes. Can also create
  synthetic/fictional session GIFs from scratch for demos, docs, or tutorials — if
  the user says "make a demo gif showing X" or "create a fake session gif", use this.
---

# agent-log-gif

Convert Claude Code and Codex session logs into animated terminal replays (GIF, MP4, AVIF).

## Prerequisites

This skill uses `uvx` to run agent-log-gif without permanent installation. Before doing anything else:

```bash
uvx --version
```

If `uvx` is not found, help the user install `uv`. Check their platform and available tools:

- **macOS with Homebrew** (check `brew --version`): `brew install uv`
- **macOS/Linux without Homebrew**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Windows (PowerShell)**: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

Tell the user to restart their terminal after installing.

Do not proceed until `uvx` is confirmed working.

## Discovering options and session sources

Run `--help` to discover current options AND detect available session sources. The help output includes a "Sessions:" line showing which sources (Claude Code, Codex, or both) are detected on this machine:

```bash
uvx agent-log-gif json --help
```

Use this output to understand available flags — the tool evolves, so always check rather than assuming options from memory. The main help also shows tool availability:

```bash
uvx agent-log-gif --help
```
gets help on all available options; note that the `local` option is for an interactive mode you won't be able to navigate inside a skill.

## Finding sessions

### Listing available sessions

Use the built-in `--list` flag to browse recent sessions — it shows dates, sizes, summaries, and full file paths:

```bash
# List recent Claude Code sessions
uvx agent-log-gif json --list=claude

# List recent Codex sessions
uvx agent-log-gif json --list=codex
```

Run whichever source(s) the `--help` output showed as detected. If both exist, list both and let the user pick. The output includes full file paths ready to use in the next command.

### Keyword search

When the user mentions a topic or keyword, use the built-in search command:
```bash
# Search both Claude Code and Codex sessions
uvx agent-log-gif search "keyword"

# Search only one source
uvx agent-log-gif search "keyword" --source claude
uvx agent-log-gif search "keyword" --source codex
```

This returns matching sessions with dates, sizes, summaries, and full file paths.

### Direct file path

If the user provides a path or the session is already identified, skip discovery and go straight to generation.

## Generating the animation

```bash
uvx agent-log-gif json <session-path> -o <output-path> [options] --open
```

### Sensible defaults

- **Format**: GIF unless the user asks for video
- **Chrome style**: Detect the user's OS and match:
  - macOS → `--chrome mac`
  - Linux → `--chrome linux`
  - Other/unsure → `--chrome mac`
- **Color scheme**: Dracula (default) — don't add `--color-scheme` unless the user has a preference
- **Output path**: Descriptive name in the current directory, like `session-replay.gif`
- **Turns**: Let the default cap (20) apply unless requested otherwise
- **--open**: Always include so the user sees the result

### Walking through options

If the user wants to customize, present the key choices conversationally. Refer to the `--help` output for the current set of options, but the main ones are typically:

1. **Format**: GIF (default), MP4, AVIF
2. **Window frame style** (`--chrome`)
3. **Color theme** (`--color-scheme`) — 480+ terminal color schemes available
4. **What to show** (`--show`) — conversation only, tool calls, everything
5. **Size** (`--cols`, `--rows`, `--font-size`)

Build the command from their choices and confirm before running.

### Example commands

```bash
# Basic — auto-opens result
uvx agent-log-gif json ~/.claude/projects/.../session.jsonl -o demo.gif --open

# Customized
uvx agent-log-gif json session.jsonl -o replay.gif --chrome linux --color-scheme Nord --show tools --turns 5

# Interactive picker (shortcut when no search needed)
uvx agent-log-gif
```

## Creating synthetic sessions from scratch

Users may want a GIF that illustrates a *hypothetical* conversation rather than replaying an existing session — for demos, docs, tutorials, or marketing. You can generate a JSONL file from scratch and feed it to the tool.

### JSONL format

Each line is a JSON object. The first line is a summary, then a stream of `user` and `assistant` messages. Here's a minimal example with a tool call:

```jsonl
{"type":"summary","summary":"Demo: adding a test"}
{"type":"user","timestamp":"2025-01-15T10:00:00.000Z","message":{"role":"user","content":"Add a test for the login endpoint"}}
{"type":"assistant","timestamp":"2025-01-15T10:00:08.000Z","message":{"role":"assistant","content":[{"type":"text","text":"I'll create a test for the login endpoint."},{"type":"tool_use","id":"toolu_01","name":"Write","input":{"file_path":"tests/test_login.py","content":"def test_login():\n    response = client.post('/login', json={'user': 'admin', 'pass': 'secret'})\n    assert response.status_code == 200\n"}}]}}
{"type":"user","timestamp":"2025-01-15T10:00:12.000Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_01","content":"File written successfully"}]}}
{"type":"assistant","timestamp":"2025-01-15T10:00:18.000Z","message":{"role":"assistant","content":[{"type":"text","text":"Done! The test is ready. Run pytest to verify it passes."}]}}
```

Note: tool results use `type: "user"` — this is the API protocol, not human input. The harness sends tool output back to the model as user messages.

### Key rules

- **Timestamps** drive the "Churned for Xs" duration display — space them realistically (5-30s between user and assistant)
- **Tool calls** need matching `tool_result` entries with the same `tool_use_id`
- **User messages**: plain string for typed input, or `[{"type":"tool_result",...}]` array for tool results
- **Assistant messages**: always a content array with `{"type":"text"}` and/or `{"type":"tool_use"}` blocks
- Tool calls and results are hidden by default — use `--show tools` or `--show all` to include them
- Keep messages concise — long text gets elided in the animation

### Workflow

1. Write the JSONL to a temp file
2. Render with `uvx agent-log-gif json <path> -o demo.gif --open`
3. Adjust content/timing and re-render until it looks right

## Important notes

- Always use `uvx agent-log-gif` — it handles installation automatically
- MP4/AVIF require ffmpeg — help the user install it if needed
- Session file URLs also work: `uvx agent-log-gif json https://...`
- Codex sessions are auto-detected by the tool's parser — no special flags needed
