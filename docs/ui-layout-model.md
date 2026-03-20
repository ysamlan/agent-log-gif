# Claude Code UI Layout Model

How the real Claude Code terminal UI maps to our animation model.

## Real Claude Code UI

Claude Code's terminal UI has a fixed three-zone layout. The bottom
zones are **pinned** — they never scroll. Only the transcript scrolls.

```
 ┌──────────────────────────────────────┐
 │                                      │
 │  TRANSCRIPT (scrollable)             │
 │                                      │
 │    ❯ user message                    │  ← highlighted
 │    ● assistant response text         │
 │    ● Write /project/hello.py         │  ← green ● = tool done
 │        File written successfully     │
 │    ● assistant continuation          │
 │                                      │
 │                                      │
 │  ● I'll crea                         │  ← streaming (temporary)
 ├──────────────────────────────────────┤  ← FIXED BOUNDARY
 │  ✻ Imagining…                        │  ← loading line (pinned)
 │                                      │  ← gap (prevents highlight bleed)
 │  ❯                                   │  ← prompt (pinned, highlighted)
 └──────────────────────────────────────┘
```

### Loading line states

The loading line is **always present** as a row — blank when idle.
It never changes the layout height; only its content changes.

```
 STATE       WHEN                           DISPLAY
 ─────────── ────────────────────────────── ──────────────────────────
 idle        before first user message      (blank row)
 thinking    user sent msg → assistant done ✻ Imagining…  (animated)
 done        turn complete                  ✻ Churned for 54s
```

The loading line never leaves the pinned area. It cannot overlap with
the transcript above it. A blank gap row between it and the prompt
prevents the prompt's highlight band from bleeding upward into it.

### Tool call states (when tools are visible)

Tool calls appear **in the transcript**, not in the loading line:

```
 STATE       DISPLAY
 ─────────── ──────────────────────────────
 loading     ● Bash echo hi        (blinking gray ●, in-progress)
 done        ● Bash echo hi        (solid green ●, committed)
                 hi                 (result text below, indented)
```

## Our Animation Model (layout.py)

The layout engine (`LayoutFrame`) has three generic zones — it doesn't
know about loading lines or prompts. The animator builds higher-level
UI concepts on top of these zones.

```python
@dataclass
class LayoutFrame:
    transcript: list[StyledLine]   # committed scrollback
    transient:  list[StyledLine]   # temporary (never committed)
    composer:   list[StyledLine]   # pinned bottom area
```

`compose_lines()` flattens them:

```
 visible_transcript[-budget:]   ← scrolls, gets truncated
 + transient                    ← temporary content
 + composer                     ← always shown in full
```

Why three generic zones instead of named UI slots? The layout engine
is intentionally simple — it just needs to know what scrolls, what's
temporary, and what's pinned. The animator maps UI concepts onto
these zones:

```
 Real UI concept       LayoutFrame zone    Built by
 ────────────────────  ──────────────────  ───────────────────────
 Transcript            transcript          buffer (grows over time)
 Streaming text        transient           partial typing lines
 Gap above loading     transient           [[]] placeholder
 Loading line          composer[0]         StatusFooter.render_line()
 Gap below loading     composer[1]         [] (blank line)
 Prompt                composer[2]         prompt_line
```

The transient zone serves double duty: it holds streaming text during
typing, and acts as a gap placeholder during pauses. This is why the
layout engine doesn't need a dedicated "loading line" concept — the
animator handles the mapping.

### Critical invariant: fixed height = 4

The renderer is **bottom-aligned** (like a real terminal). When there
are fewer lines than viewport rows, empty space appears at the top.
This means if the fixed height (transient + composer) changes between
frames, the pinned area shifts vertically — visible as "overlapping"
in the animated GIF.

The solution: **fixed height is always 4**.

```
 Zone        Lines  Contents
 ──────────  ─────  ─────────────────────────────────────
 transient   1      [[]] gap placeholder, or streaming/tool content
 composer    3      [loading_line, gap, prompt]
 ──────────  ─────
 TOTAL       4      (constant across all frames)
```

The loading line is always present (blank when idle), the gap always
separates it from the prompt, and the transient always has at least
a placeholder line. This means:

- The prompt and loading line are **always at the same pixel row**
- The only thing that shifts transcript upward is the input area
  growing when the user types a long wrapping message
- Content commits to the transcript naturally push older lines up

```
 Phase               Transient         Composer                Fixed
 ──────────────────  ────────────────  ──────────────────────  ─────
 idle (no turns)     [[]] (gap)        [blank, gap, prompt]    4
 thinking pause      [[]] (gap)        [spinner, gap, prompt]  4
 assistant typing    [partial text]    [spinner, gap, prompt]  4
 pause after asst    [[]] (gap)        [churned, gap, prompt]  4
 tool call blink     [tool line]       [spinner, gap, prompt]  4
 pause after tool    [[]] (gap)        [spinner, gap, prompt]  4
 user typing (t2+)   [[]] (gap)        [churned, gap, input]   4
```
