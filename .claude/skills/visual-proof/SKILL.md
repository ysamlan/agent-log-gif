---
name: visual-proof
description: Document visual output with GIF/image captures and proof-of-work reports. Use after making changes to the rendering pipeline (theme, renderer, animator, spinner) to show what the output looks like. Produces a showboat markdown document with embedded GIF frames and test results. Trigger when making visual changes, when the user asks to "show what it looks like" or "show me the output", or when completing work that changes GIF/video appearance.
---

# Visual Proof

Capture and document visual output from agent-log-gif with showboat proof-of-work reports.

## Prerequisites

- `showboat` CLI available (`uvx showboat --version` to check)
- Project tests passing (`just test`)

## How It Works

Generate GIFs from sample sessions, extract representative frames, and assemble a showboat document that proves the output looks correct. Showboat documents are verifiable — `uvx showboat verify` can re-run the embedded commands to confirm outputs still match.

## Standard Proof Workflow

### 1. Initialize the document

```bash
uvx showboat init /workspace/tmp/visual-proof.md "Visual proof: <description of change>"
```

### 2. Generate sample output

Run the tool on test fixtures and/or real sessions to produce GIFs:

```bash
uvx showboat exec /workspace/tmp/visual-proof.md bash \
  'cd /workspace && uv run agent-log-gif json tests/sample_session.jsonl -o /workspace/tmp/proof-sample.gif --turns 2 2>&1'
```

For Codex sessions:
```bash
uvx showboat exec /workspace/tmp/visual-proof.md bash \
  'cd /workspace && uv run agent-log-gif json tests/sample_codex_session.jsonl -o /workspace/tmp/proof-codex.gif 2>&1'
```

### 3. Embed the GIF directly

Showboat's `image` command works with GIFs — embed the animated output directly so reviewers see the full animation in the markdown:

```bash
uvx showboat image /workspace/tmp/visual-proof.md '![Sample session animation](/workspace/tmp/proof-sample.gif)'
uvx showboat note /workspace/tmp/visual-proof.md "2-turn Claude Code session with typing animation and spinner."
```

For static frame extraction (e.g., before/after comparisons where animation isn't needed), use ffmpeg:
```bash
ffmpeg -i /workspace/tmp/proof-sample.gif -vf "select=eq(n\,30)" -frames:v 1 \
  -update 1 /workspace/tmp/proof-frame.png -y 2>/dev/null
```

### 4. Add test results as executable proof

```bash
uvx showboat exec /workspace/tmp/visual-proof.md bash \
  'cd /workspace && uv run pytest tests/ -q --tb=no 2>&1 | tail -5'
```

### 5. Add notes about what changed

```bash
uvx showboat note /workspace/tmp/visual-proof.md "Changed the spinner colors to cycle through rainbow palette..."
```

## Before/After Comparison

For changes that affect visual output (theme colors, font size, spacing, title bar):

1. Generate a GIF on the current branch first, save the frame
2. Make changes
3. Generate a new GIF, save the frame
4. Build a showboat doc with both:

```bash
uvx showboat init /workspace/tmp/comparison.md "Before/after: <description>"
uvx showboat image /workspace/tmp/comparison.md '![Before](/workspace/tmp/before-frame.png)'
uvx showboat note /workspace/tmp/comparison.md "Before — <describe>"
uvx showboat image /workspace/tmp/comparison.md '![After](/workspace/tmp/after-frame.png)'
uvx showboat note /workspace/tmp/comparison.md "After — <what changed>"
```

## File Size Proof

Document GIF optimization impact:

```bash
uvx showboat exec /workspace/tmp/visual-proof.md bash \
  'cd /workspace && uv run agent-log-gif json tests/sample_session.jsonl -o /workspace/tmp/proof.gif 2>&1 | grep -E "gifsicle|Done"'
```

## Important: Never Edit the Showboat File Directly

Always use `uvx showboat` CLI commands (`init`, `note`, `exec`, `image`, `pop`) to build documents. Never write to or edit the `.md` file directly — showboat documents are trustworthy because every entry was produced by the CLI. If you make a mistake, use `uvx showboat pop <file>` to remove the last entry and redo it.

## Output Location

Store all proof artifacts in `/workspace/tmp/`:
- GIFs: `tmp/proof-sample.gif`, `tmp/proof-codex.gif`
- Frames: `tmp/proof-frame.png`, `tmp/before-frame.png`, `tmp/after-frame.png`
- Reports: `tmp/visual-proof.md`, `tmp/comparison.md`

These are gitignored — they're proof-of-work artifacts, not source files.

## When to Use

| Situation | What to capture |
|-----------|----------------|
| Changed theme colors or font | Before/after frame comparison |
| Changed animator (typing speed, spinner) | GIF from sample session + note about timing |
| Changed renderer (title bar, viewport) | Frame showing the chrome |
| Changed GIF backend (compression, palette) | File size comparison |
| New format support (MP4, AVIF) | Exec showing the format works |
| Completing any visual task | Appropriate proof from above |
