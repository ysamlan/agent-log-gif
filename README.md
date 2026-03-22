# agent-log-gif

[![PyPI](https://img.shields.io/pypi/v/agent-log-gif.svg)](https://pypi.org/project/agent-log-gif/)
[![Tests](https://github.com/ysamlan/agent-log-gif/workflows/Test/badge.svg)](https://github.com/ysamlan/agent-log-gif/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/ysamlan/agent-log-gif/blob/main/LICENSE)

Turn your Claude Code and Codex sessions into animated terminal-style replay GIFs or videos. Share them on Reddit, Slack, etc.

![demo](demo.avif)<br><sup>_With apologies to [Summer Yue](https://www.theverge.com/ai-artificial-intelligence/883034/openclaw-ai-deleting-emails-stop-openclaw)._</sup>

Less fun but more usefully: use agent session videos to do retrospective reviews; include cool Claude demos in slide decks.

Supports Claude Code and Codex sessions out of the box.

<details>
<summary>Windows chrome + Codex session</summary>

![windows-codex](docs/demo-windows-codex.avif)

</details>

## Quick start

```bash
uvx agent-log-gif
```

Or pick a specific session from disk:

```bash
uvx agent-log-gif json ~/.claude/projects/<project>/<session>.jsonl
```

Help on all options:
```bash
uvx agent-log-gif json --help
```

To install permanently:

```bash
uv tool install agent-log-gif
```

Or to install as a Skill you can ask your agent to use for you:

```bash
npx skills add ysamlan/agent-log-gif
```

## Claude/Codex skill

agent-log-gif includes an [agent-log-gif Skill](https://github.com/ysamlan/agent-log-gif/tree/main/skills/agent-log-gif/) that lets Claude Code / Codex find your sessions and generate animations for you conversationally. Copy the skills/agent-log-gif  folder it into `~/.claude/skills/`, or install automatically via [skills.sh](https://github.com/vercel-labs/skills):

```bash
npx skills add ysamlan/agent-log-gif
```

Then ask Claude things like "make a gif of my last coding session" or "find the session where I worked on auth and make an mp4 showing tool calls," or run `/agent-log-gif` inside Claude Code (`$agent-log-gif` in Codex).

## Optional tools

For MP4/AVIF output, install [ffmpeg](https://ffmpeg.org/) using your system package manager (`brew install ffmpeg`, `choco install ffmpeg`, `apt install ffmpeg`, etc.).

For AVIF, your `ffmpeg` build must include an AV1 encoder. `agent-log-gif` prefers `libsvtav1` and falls back to `libaom-av1`.

```bash
ffmpeg -encoders | rg 'av1|svt|aom'
```

## Optimized GIFs

GIF optimization is done automatically via [gifsicle](https://www.lcdf.org/gifsicle/) using [gifsicle-bin](https://github.com/ysamlan/gifsicle-bin). Very large GIFs will skip automatic optimization to avoid hanging/crashing `gifsicle`.

## Usage

### Convert a session file

```bash
# GIF (default)
agent-log-gif json session.jsonl

# Animated AVIF
agent-log-gif json session.jsonl --format avif

# MP4 with (optional) background music
agent-log-gif json session.jsonl --format mp4 --music track.mp3 --loop-music

# Specify output file
agent-log-gif local -o out.gif
```

### Pick from local sessions

```bash
agent-log-gif                  # interactive picker, opens result
```

### Turn selection

Sessions default to 20 turns max. Adjust with `--turns`:

```bash
agent-log-gif json session.jsonl --turns 5      # first 5 turns
agent-log-gif json session.jsonl --turns 3,8    # turns 3 through 8
```

### Music (MP4 only)

```bash
agent-log-gif json session.jsonl -o demo.mp4 --format mp4 --music track.mp3
agent-log-gif json session.jsonl -o demo.mp4 --format mp4 --music track.mp3 --loop-music
```

### Window chrome

Default is macOS-26-like with rounded corners and traffic-light buttons. Choose a different style:

```bash
agent-log-gif json session.jsonl --chrome none         # no window frame
agent-log-gif json session.jsonl --chrome mac          # macOS, rounded corners (default)
agent-log-gif json session.jsonl --chrome mac-square   # macOS, square corners
agent-log-gif json session.jsonl --chrome windows      # Windows 11
agent-log-gif json session.jsonl --chrome linux        # GNOME/Ubuntu
```

For dark terminal themes embedded on a light page, you can set the outer canvas color behind the rounded macOS corners:

```bash
agent-log-gif json session.jsonl --chrome mac --canvas-bg "#FFFFFF"
```

### Color scheme

480+ terminal color schemes bundled from [iTerm2-Color-Schemes](https://github.com/mbadolato/iTerm2-Color-Schemes). Default is Dracula.

```bash
agent-log-gif json session.jsonl --color-scheme "Catppuccin Mocha"
```

### Custom font

Default is [DejaVu Sans Mono](https://dejavu-fonts.github.io/) (bundled). Override with any TTF:

```bash
agent-log-gif json session.jsonl --font /path/to/MyFont.ttf
```

### Supported session formats

- Claude Code JSONL files (`~/.claude/projects/`)
- Codex JSONL session files (`~/.codex/sessions/`)
- URLs to any of the above

### Web sessions

> [!WARNING]
> The `web` commands are broken right now due to changes to the unofficial and undocumented APIs that these commands were using. 
> See [this issue](https://github.com/simonw/claude-code-transcripts/issues/77) in simonw/claude-code-transcripts for details.
> 

```bash
agent-log-gif web                       # interactive session picker
agent-log-gif web SESSION_ID            # specific session
agent-log-gif web --repo owner/repo     # filter by repo
```

On macOS, credentials are auto-detected from your keychain. On other platforms, provide `--token` and `--org-uuid`.

## All options

```
agent-log-gif json [OPTIONS] [FILE]

  -o, --output PATH            Output file path (default: <input>.<format>)
  --list [claude|codex]        List recent sessions instead of converting
  --format [gif|mp4|avif]      Output format (default: gif)
  --turns TEXT                 N for first N turns, M,N for range
  --music PATH                 Music track for MP4
  --loop-music                 Loop music if shorter than video
  --chrome STYLE               Window chrome: none|mac|mac-square|windows|linux
  --canvas-bg TEXT             Outer canvas color outside rounded macOS corners
  --color-scheme NAME          Terminal color scheme (e.g. Dracula, Nord)
  --font PATH                  Custom TTF font file
  --cols INT                   Terminal width in columns (default: 80)
  --rows INT                   Terminal height in rows (default: 18)
  --font-size INT              Font size in pixels (default: 16)
  --show TYPES                 Extra content: tools, calls, thinking, all
  --speed FLOAT                Typing speed multiplier (default: 1.0)
  --spinner-time FLOAT         Spinner duration multiplier (default: 1.0)
  --thinking-verbs TEXT        Custom spinner verbs (comma-separated)
  --shimmer / --no-shimmer     Loading line shimmer effect (default: on)
  --colors INT                 GIF palette size, 2-256 (default: 256)
  --parallel INT               Rendering workers (0=auto, 1=off, 2+=explicit)
  --open / --no-open           Open result in default viewer

agent-log-gif search KEYWORD [--source claude|codex]
```

## Credits

Session parsing logic originally based on [Simon Willison](https://simonwillison.net/)'s [claude-code-transcripts](https://github.com/simonw/claude-code-transcripts).
Color schemes from [iTerm2-Color-Schemes](https://github.com/mbadolato/iTerm2-Color-Schemes) by Mark Badolato (MIT license).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and guidelines.
