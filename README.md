# agent-log-gif

[![PyPI](https://img.shields.io/pypi/v/agent-log-gif.svg)](https://pypi.org/project/agent-log-gif/)
[![Tests](https://github.com/ysamlan/agent-log-gif/workflows/Test/badge.svg)](https://github.com/ysamlan/agent-log-gif/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/ysamlan/agent-log-gif/blob/main/LICENSE)

Convert Claude Code or Codex session logs into animated terminal replay GIFs and videos — designed for sharing on Reddit, Slack, and social media.

Session parsing logic originally based on [Simon Willison](https://simonwillison.net/)'s [claude-code-transcripts](https://github.com/simonw/claude-code-transcripts).

## Quick start

```bash
# Run without installing
uvx agent-log-gif json session.jsonl -o demo.gif

# Or install globally
uv tool install agent-log-gif
```

Convert a session file to an animated GIF:

```bash
agent-log-gif json ~/.claude/projects/my-project/session.jsonl -o session.gif
```

Or pick from recent local sessions interactively:

```bash
agent-log-gif
```

## Output formats

The default format is **GIF** (requires only Pillow — no external tools). **MP4** and **AVIF** are also available and require [ffmpeg](https://ffmpeg.org/).

```bash
# GIF (default, no ffmpeg needed)
agent-log-gif json session.jsonl -o demo.gif

# MP4 (much smaller file size, requires ffmpeg)
agent-log-gif json session.jsonl -o demo.mp4 --format mp4

# Animated AVIF (requires ffmpeg)
agent-log-gif json session.jsonl -o demo.avif --format avif
```

If [gifsicle](https://www.lcdf.org/gifsicle/) is installed, GIFs are automatically optimized (typically 80-85% smaller).

## Turn selection

By default, sessions are capped at 20 turns. Use `--turns` to adjust:

```bash
# First 5 turns only
agent-log-gif json session.jsonl -o demo.gif --turns 5

# Turns 3 through 8
agent-log-gif json session.jsonl -o demo.gif --turns 3,8
```

## Music (MP4 only)

Attach a music track to MP4 output:

```bash
# Add background music (trimmed/faded at end of video)
agent-log-gif json session.jsonl -o demo.mp4 --format mp4 --music track.mp3

# Loop short music to cover full video duration
agent-log-gif json session.jsonl -o demo.mp4 --format mp4 --music track.mp3 --loop-music
```

## Custom font

The default font is [JetBrains Mono](https://www.jetbrains.com/lp/mono/) (bundled). Override with any TTF file:

```bash
agent-log-gif json session.jsonl -o demo.gif --font /path/to/MyFont.ttf
```

## Commands

| Command | Description |
|---------|-------------|
| `local` (default) | Interactive picker for local Claude Code sessions in `~/.claude/projects` |
| `json` | Convert a specific JSON/JSONL session file (or URL) to media |
| `web` | Fetch a session from the Claude API (best-effort, see note below) |

### Local sessions

```bash
agent-log-gif                  # interactive picker, opens result
agent-log-gif local --limit 20 # show more sessions
agent-log-gif local -o out.gif # save to specific file
```

### JSON/JSONL files

```bash
agent-log-gif json session.jsonl -o out.gif
agent-log-gif json session.json -o out.mp4 --format mp4
agent-log-gif json https://example.com/session.jsonl -o out.gif
```

Works with:
- Claude Code JSONL files from `~/.claude/projects/`
- Claude Code JSON session files
- Codex JSONL session files from `~/.codex/sessions/`

### Web sessions

> [!WARNING]
> The `web` command relies on unofficial, undocumented APIs and may not work reliably.

```bash
agent-log-gif web                          # interactive session picker
agent-log-gif web SESSION_ID               # specific session
agent-log-gif web --repo owner/repo        # filter by GitHub repo
```

On macOS, credentials are auto-detected from your keychain. On other platforms, provide `--token` and `--org-uuid`.

## Visual style

The generated animations mimic a Claude Code terminal session:

- **Dracula** color scheme (dark background)
- **JetBrains Mono** font
- User prompts type in with a `❯` prompt character
- A spinning indicator with a random whimsical verb plays between turns
- Assistant responses type in with a `●` bullet
- macOS-style window chrome with traffic light dots

## Development

```bash
cd agent-log-gif
uv sync
just test        # run tests
just lint        # run linting
uv run agent-log-gif --help
```

### Dependencies

- **Runtime:** click, Pillow (MIT), httpx, questionary
- **Optional:** ffmpeg (for MP4/AVIF/audio), gifsicle (for GIF optimization)
- **Bundled:** JetBrains Mono Regular (OFL-1.1)
