"""Layout composition layer for chat-style terminal frames.

Codifies the mental model of a terminal chat UI:

    ┌────────────────────────────┐
    │  transcript (scrollback)   │  ← committed content, scrolls up
    │  ...                       │
    │  transient (spinner, etc.) │  ← temporary, never committed
    │  composer (prompt / input) │  ← fixed at bottom
    └────────────────────────────┘

Invariants:
  1. Transcript contains only committed scrollback.
  2. Composer is always present, does not participate in transcript scroll.
  3. Transient content (spinner, partial typing) is never committed to transcript.
  4. Temporary UI states do not move committed transcript rows
     unless real scrolling occurs.
  5. Spacing is a block policy, not incidental blank rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_log_gif.renderer import StyledLine


@dataclass
class LayoutFrame:
    """The three regions of a terminal chat frame.

    transcript: committed scrollback lines (grows over time)
    transient:  temporary lines between transcript and composer
                (spinner, partial assistant typing) — never committed
    composer:   the input area at the bottom (idle prompt or active typing)
    """

    transcript: list[StyledLine]
    transient: list[StyledLine] = field(default_factory=list)
    composer: list[StyledLine] = field(default_factory=list)


def compose_lines(frame: LayoutFrame, viewport_rows: int) -> list[StyledLine]:
    """Flatten a LayoutFrame into a list of styled lines for the renderer.

    Computes viewport budget: transcript gets whatever rows remain after
    composer and transient claim their space.  Composer and transient are
    never truncated — they always appear in full.
    """
    fixed_height = len(frame.composer) + len(frame.transient)
    transcript_budget = max(0, viewport_rows - fixed_height)
    visible_transcript = (
        frame.transcript[-transcript_budget:] if transcript_budget > 0 else []
    )
    return visible_transcript + frame.transient + frame.composer


def commit_with_spacing(
    transcript: list[StyledLine],
    lines: list[StyledLine],
    spacing_after: int = 0,
) -> None:
    """Append lines to the transcript buffer with controlled spacing.

    Args:
        transcript: The transcript buffer to append to (mutated in place).
        lines: The styled lines to append.
        spacing_after: Number of blank lines to insert after the content.
    """
    transcript.extend(lines)
    for _ in range(spacing_after):
        transcript.append([])
