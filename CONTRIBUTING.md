# Contributing

## Setup

```bash
git clone https://github.com/ysamlan/agent-log-gif.git
cd agent-log-gif
uv sync
```

## Running

```bash
uv run agent-log-gif --help          # CLI help
uv run agent-log-gif json session.jsonl -o test.gif  # test a session
```

## Testing

```bash
just test          # run all tests
just test-v        # verbose output
just lint          # auto-fix linting + formatting
just lint-check    # check only (CI mode)
just --list        # all available commands
```

Or directly:

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## TDD workflow

Write a failing test, watch it fail, then make it pass. Commits should bundle test + implementation + doc changes together.

Linting runs automatically via a git pre-commit hook.

## Project structure

```
src/agent_log_gif/
├── __init__.py      # CLI commands and pipeline
├── parsers.py       # Session file parsing (Claude JSON/JSONL, Codex JSONL)
├── session.py       # Local session discovery and summaries
├── analysis.py      # Conversation analysis (tool stats, commits, repos)
├── timeline.py      # Replay event model (loglines → typed events)
├── theme.py         # Terminal theme (Dracula colors, font, dimensions)
├── renderer.py      # Pillow frame renderer (2x SSAA, title bar chrome)
├── animator.py      # Typing + spinner animation engine
├── spinner.py       # Spinner frame data and verb list
├── web.py           # API session fetching (best-effort)
├── backends/
│   ├── gif.py       # GIF assembly + gifsicle optimization
│   ├── video.py     # MP4/AVIF via ffmpeg
│   └── audio.py     # Music mixing via ffmpeg
└── fonts/           # Bundled DejaVu Sans Mono
```

## Dependencies

Python dependencies are in `pyproject.toml`. GIF optimization via gifsicle is included automatically via the [gifsicle-bin](https://github.com/ysamlan/gifsicle-bin) dependency. Optional system tool: ffmpeg (MP4/AVIF/audio).

### Bundled assets

| Asset | License | File |
|-------|---------|------|
| DejaVu Sans Mono font | Bitstream Vera | `fonts/DejaVuSansMono-LICENSE.txt` |
| 484 color schemes ([iTerm2-Color-Schemes](https://github.com/mbadolato/iTerm2-Color-Schemes)) | MIT | `color_schemes_LICENSE.txt` |

Run `just licenses` to regenerate the Python dependency license audit.
