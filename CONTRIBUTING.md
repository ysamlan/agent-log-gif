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
just lint          # auto-fix linting + formatting (Python + HTML)
just lint-check    # check only (CI mode)
just --list        # all available commands
```

Or directly:

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run djhtml --tabwidth=2 --check web/
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
├── frame_store.py   # Compressed frame storage (pyzstd, zlib fallback)
├── web.py           # API session fetching (best-effort)
├── backends/
│   ├── gif.py       # GIF assembly + gifsicle optimization
│   ├── video.py     # MP4/AVIF via ffmpeg
│   └── audio.py     # Music mixing via ffmpeg
└── fonts/           # Bundled DejaVu Sans Mono

web/                 # Static web UI (GitHub Pages)
├── index.html       # Single-page app (drag-drop + compose)
├── worker.js        # Web Worker (Pyodide + Pillow + gifsicle.wasm)
├── pipeline.py      # Python pipeline for Pyodide
├── agent_log_gif.zip  # Built by scripts/build_web.sh (not checked in)
└── lib/gifsicle/    # gifsicle compiled to WASM (from gifsicle-bin releases)
    ├── gifsicle.js    # Emscripten JS loader
    └── gifsicle.wasm  # Compiled binary (~233 KB)
```

## Dependencies

Python dependencies are in `pyproject.toml`. GIF optimization via gifsicle is included automatically via the [gifsicle-bin](https://github.com/ysamlan/gifsicle-bin) dependency.
`gifsicle-bin` provides a convenience for installing `gifsicle`, but we invoke it via `subprocess.run` (keeping it at arms-length). We skip final optimization if `gifsicle-bin` is missing (eg unsupported platforms).
Optional system tool: `ffmpeg` (MP4/AVIF/audio).

## Web UI

The web UI runs the rendering pipeline entirely client-side using [Pyodide](https://pyodide.org) (Python in WebAssembly). Users drop a session file or compose a dialog, and get a GIF back without any server. Uses WASM from <a href="https://simonwillison.net/guides/agentic-engineering-patterns/gif-optimization/">Simon Willison</a> to provide `gifsicle` optimization in the browser. We use a separate worker for gifsicle to preserve the same arms-length behavior as the CLI (keeping the GPLv2 code invoked by basically piping the output gif through it and retrieving the optimized gif afterwards).

### Local development

```bash
just serve           # builds the zip bundle and starts http://localhost:8000
```

The `agent_log_gif.zip` bundle is built from `src/agent_log_gif/` excluding CLI-only modules (`__init__.py`, `session.py`, `web.py`, `analysis.py`, video/audio backends). The web `pipeline.py` stubs the package's `__init__.py` and `click` at runtime so the pure-Python submodules can be imported directly in Pyodide.

### How it works

1. **index.html** — tabbed UI (file upload or compose dialog), sends JSONL to the pipeline Web Worker
2. **worker.js** (Apache 2.0) — loads Pyodide + Pillow, unpacks the source bundle, runs the pipeline, then delegates GIF optimization to the gifsicle sub-worker via `postMessage`
3. **pipeline.py** — reimplements `_session_to_media()` for Pyodide (stubs click, uses `parallel=1`, smaller defaults: 72x16 terminal, 10 max turns)
4. **gifsicle-worker.js** (GPL boundary) — dedicated Web Worker that loads gifsicle.wasm in a separate execution context and optimizes the GIF (~37-50% additional size reduction). Communicates solely via serialized `ArrayBuffer` messages, mirroring the CLI's `subprocess.run()` separation.

### Rebuilding the web bundle

```bash
just build-web       # or: bash scripts/build_web.sh
```

This creates `web/agent_log_gif.zip` from `src/`. The zip is not checked into git — it's built in CI by the GitHub Pages deploy workflow.

### Deployment

GitHub Pages deploys automatically on push to `main` via `.github/workflows/pages.yml`. The workflow fetches the gifsicle WASM artifacts from the gifsicle-bin release, runs `build_web.sh`, then deploys the `web/` directory.

To enable: go to repo **Settings → Pages → Source** and select **"GitHub Actions"**.

PyPI publishing runs from `.github/workflows/publish.yml` when a GitHub release is published. That workflow mirrors CI: non-browser tests run across the Python matrix, while Playwright browser tests run once on Ubuntu/Python 3.13 before publish.

## Updating gifsicle WASM

The gifsicle WASM artifacts (`gifsicle.js` + `gifsicle.wasm`) are built by [gifsicle-bin](https://github.com/ysamlan/gifsicle-bin) CI and published as GitHub Release assets. The WASM build approach is based on [Simon Willison's gifsicle WASM work](https://github.com/simonw/tools) ([blog post](https://simonwillison.net/guides/agentic-engineering-patterns/gif-optimization/)).

The compiled artifacts are checked into `web/lib/gifsicle/` (~310 KB total) so local dev works without extra setup.

To update (e.g., after a new gifsicle-bin release):

1. **Bump the version** in `pyproject.toml`:
   ```
   "gifsicle-bin>=1.96.2",  # ← update to the new version
   ```

2. **Fetch the new WASM artifacts**:
   ```bash
   just update-gifsicle-wasm
   ```
   This downloads `gifsicle.js` and `gifsicle.wasm` from the matching [gifsicle-bin GitHub release](https://github.com/ysamlan/gifsicle-bin/releases).

3. **Test** — run `just serve`, drop a file, verify the GIF output and gifsicle savings percentage look reasonable.

4. **Commit** the updated `gifsicle.js` and `gifsicle.wasm`.

The Pages deployment workflow also fetches fresh WASM artifacts during CI (`scripts/fetch_gifsicle_wasm.sh`), so the deployed site always matches the version pinned in `pyproject.toml`.

### Bundled assets

| Asset | License | File |
|-------|---------|------|
| DejaVu Sans Mono font | Bitstream Vera | `fonts/DejaVuSansMono-LICENSE.txt` |
| 484 color schemes ([iTerm2-Color-Schemes](https://github.com/mbadolato/iTerm2-Color-Schemes)) | MIT | `color_schemes_LICENSE.txt` |
| [gifsicle WASM](https://simonwillison.net/guides/agentic-engineering-patterns/gif-optimization/) (from [kohler/gifsicle](https://github.com/kohler/gifsicle)) | GPL v2 | `web/lib/gifsicle/` |

Run `just licenses` to regenerate the Python dependency license audit.
