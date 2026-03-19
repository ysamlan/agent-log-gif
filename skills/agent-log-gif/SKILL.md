---
name: agent-log-gif
description: >
  Generate animated GIF/MP4/AVIF terminal replays from Claude Code or Codex sessions.
  Use this skill whenever the user wants to create a GIF, animation, video, or visual
  replay of a Claude Code or Codex session — whether they say "make a gif of my session", "animate
  that conversation", "create a terminal recording", "share a replay", or reference
  agent-log-gif directly. Also trigger when users want to find, search, or browse
  their Claude Code or Codex sessions for visualization purposes.
---

# agent-log-gif

Convert Claude Code and Codex session logs into animated terminal replays (GIF, MP4, AVIF).

## Prerequisites

This skill uses `uvx` to run agent-log-gif without permanent installation. Before doing anything else:

```bash
uvx --version
```

If `uvx` is not found, tell the user:

> agent-log-gif requires `uv` to run. Install it with:
> ```
> curl -LsSf https://astral.sh/uv/install.sh | sh
> ```
> Then restart your terminal and try again.

Do not proceed until `uvx` is confirmed working.

## Discovering options

Always check the current CLI options rather than assuming from memory:

```bash
uvx agent-log-gif json --help
```

## Finding sessions

Sessions can come from two sources. Detect which are available:

- **Claude Code**: `~/.claude/projects/` — JSONL files in project subfolders
- **Codex**: `~/.codex/sessions/` — JSONL files, possibly in year subfolders

Check both:
```bash
ls ~/.claude/projects/ 2>/dev/null && echo "Claude Code sessions found"
ls ~/.codex/sessions/ 2>/dev/null && echo "Codex sessions found"
```

If both exist, tell the user and ask which they want, or search both.

### Picker-style interaction

When the user wants to browse rather than search, present their recent sessions as a numbered list they can choose from. Gather the most recent sessions from whichever sources exist:

```bash
# Recent Claude Code sessions (most recent first)
find ~/.claude/projects -name "*.jsonl" -not -name "agent-*" -type f -printf "%T@ %p\n" 2>/dev/null | sort -rn | head -10

# Recent Codex sessions
find ~/.codex/sessions -name "*.jsonl" -type f -printf "%T@ %p\n" 2>/dev/null | sort -rn | head -10
```

For each candidate, extract a summary (first user message) to show the user:
```bash
head -20 <session-file> | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        obj = json.loads(line)
        t = obj.get('type', '')
        msg = obj.get('message', {}).get('content', '')
        # Claude Code format
        if t == 'user' and isinstance(msg, str) and msg.strip():
            print(msg[:120]); break
        # Also check for summary entries
        if t == 'summary':
            s = obj.get('summary', '')
            if s: print(s[:120]); break
    except: pass
"
```

Present like:
```
1. [2026-03-19] "Create a hello world function" (Claude Code, 12 KB)
2. [2026-03-18] "Fix the auth middleware bug" (Claude Code, 45 KB)
3. [2026-03-18] "Build a REST API endpoint" (Codex, 8 KB)
```

Let the user pick by number, then proceed to generation.

### Keyword search

When the user mentions a topic or keyword:
```bash
grep -rl "keyword" ~/.claude/projects/*/  --include="*.jsonl" 2>/dev/null | head -10
grep -rl "keyword" ~/.codex/sessions/ --include="*.jsonl" 2>/dev/null | head -10
```

Show matching sessions with summaries and let the user confirm.

### Direct file path

If the user provides a path or the session is already identified, skip discovery and go straight to generation.

## Generating the animation

```bash
uvx agent-log-gif json <session-path> -o <output-path> [options] --open
```

### Sensible defaults

- **Format**: GIF unless the user asks for video
- **Chrome style**: Detect OS and match:
  - macOS → `--chrome mac`
  - Linux → `--chrome linux`
  - Other/unsure → `--chrome mac`
- **Color scheme**: Dracula (default) — don't add `--color-scheme` unless the user has a preference
- **Output path**: Descriptive name in current directory, like `session-replay.gif`
- **Turns**: Let the default cap (20) apply unless requested otherwise
- **--open**: Always include so the user sees the result

### Walking through options

If the user wants to customize, present the key choices conversationally:

1. **Format**: GIF (default, works everywhere), MP4 (smaller, needs ffmpeg), AVIF (smallest, needs ffmpeg)
2. **Window frame**: macOS, macOS square corners, Windows 11, Linux/GNOME, or no frame
3. **Color theme**: 480+ terminal themes available — popular ones include Dracula, Nord, Catppuccin Mocha, Gruvbox Dark, TokyoNight. Also light themes like Catppuccin Latte, Rose Pine Dawn
4. **What to show**: Just conversation (default), tool call names, tool calls + results, or everything including thinking
5. **Size**: Terminal width/height and font size are adjustable

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

## Important notes

- Always use `uvx agent-log-gif` — it handles installation automatically
- The tool warns if gifsicle is missing (GIFs still work, just larger) — relay the install tip
- MP4/AVIF require ffmpeg — help the user install it if needed
- Session file URLs also work: `uvx agent-log-gif json https://...`
- Codex sessions are auto-detected by the tool — no special flags needed
