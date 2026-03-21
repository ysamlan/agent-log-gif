"""Spinner animation frames, shimmer engine, and whimsical verb list.

Character sequence sourced from Claude Code's CLI (character values only,
no code copied). The spinner cycles through six star/asterisk-like glyphs
in Claude's brand orange color. The verb text shares the same color.

The shimmer engine produces a cosine-falloff bright band that sweeps across
text, matching the real Codex TUI shimmer helper (shimmer.rs).
"""

import math
from dataclasses import dataclass

from agent_log_gif.theme import TerminalTheme

# Star/asterisk spinner frames (6 frames, cycle at ~80ms each)
SPINNER_FRAMES = ["·", "✢", "✳", "∗", "✻", "✽"]

# Spinner color — Claude's warm orange/terracotta (brand color)
SPINNER_COLOR = "#da7756"

# Tool done color — Dracula green, solid bullet when tool completes
TOOL_DONE_COLOR = "#50FA7B"

# Whimsical verbs displayed alongside the spinner
SPINNER_VERBS = [
    "Accomplishing",
    "Architecting",
    "Baking",
    "Beboppin'",
    "Boogieing",
    "Booping",
    "Brewing",
    "Calculating",
    "Cascading",
    "Cerebrating",
    "Churning",
    "Clauding",
    "Coalescing",
    "Cogitating",
    "Combobulating",
    "Composing",
    "Computing",
    "Concocting",
    "Contemplating",
    "Cooking",
    "Crafting",
    "Creating",
    "Crunching",
    "Crystallizing",
    "Deliberating",
    "Determining",
    "Discombobulating",
    "Doing",
    "Enchanting",
    "Envisioning",
    "Fermenting",
    "Finagling",
    "Flowing",
    "Forging",
    "Forming",
    "Gallivanting",
    "Generating",
    "Grooving",
    "Harmonizing",
    "Hashing",
    "Hatching",
    "Ideating",
    "Imagining",
    "Improvising",
    "Incubating",
    "Inferring",
    "Levitating",
    "Manifesting",
    "Meandering",
    "Metamorphosing",
    "Moonwalking",
    "Mulling",
    "Musing",
    "Noodling",
    "Orchestrating",
    "Percolating",
    "Philosophising",
    "Pondering",
    "Pontificating",
    "Processing",
    "Proofing",
    "Puzzling",
    "Razzle-dazzling",
    "Recombobulating",
    "Ruminating",
    "Simmering",
    "Sketching",
    "Spinning",
    "Sprouting",
    "Synthesizing",
    "Thinking",
    "Tinkering",
    "Transmuting",
    "Undulating",
    "Vibing",
    "Wandering",
    "Whirring",
    "Working",
    "Wrangling",
    "Zigzagging",
]


# ---------------------------------------------------------------------------
# Shimmer engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShimmerProfile:
    """Configuration for a text shimmer sweep effect."""

    base_color: str | None  # hex color at rest (None = must supply override)
    highlight_color: str  # hex target at peak shimmer
    sweep_seconds: float  # time for one full sweep cycle
    band_half_width: float  # cosine band half-width in character units
    padding: int  # off-text padding chars each side
    max_intensity: float  # peak blend factor cap (0.0–1.0)
    direction: int  # +1 LTR, -1 RTL


CODEX_SHIMMER = ShimmerProfile(
    base_color=None,  # filled from theme.comment at call site
    highlight_color="#ffffff",
    sweep_seconds=2.0,
    band_half_width=5.0,
    padding=10,
    max_intensity=0.9,
    direction=1,
)

CLAUDE_SHIMMER = ShimmerProfile(
    base_color=SPINNER_COLOR,
    highlight_color="#ffe0cc",
    sweep_seconds=1.3,
    band_half_width=3.5,
    padding=8,
    max_intensity=0.7,
    direction=-1,
)


def blend_hex(color_a: str, color_b: str, t: float) -> str:
    """Linearly interpolate between two hex colors. t=0→a, t=1→b."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = TerminalTheme.hex_to_rgb(color_a)
    rb, gb, bb = TerminalTheme.hex_to_rgb(color_b)
    r = int(ra + (rb - ra) * t)
    g = int(ga + (gb - ga) * t)
    b = int(ba + (bb - ba) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def shimmer_styled_segments(
    text: str,
    profile: ShimmerProfile,
    elapsed_ms: int,
    base_color_override: str | None = None,
) -> list[tuple[str, str]]:
    """Compute per-character shimmer colors and return coalesced styled segments.

    Args:
        text: The text to apply shimmer to.
        profile: ShimmerProfile controlling the sweep.
        elapsed_ms: Milliseconds since shimmer started (frame_idx * SPINNER_FRAME_MS).
        base_color_override: If set, use instead of profile.base_color.

    Returns:
        List of (text_chunk, hex_color) tuples with adjacent same-color chars merged.
    """
    if not text:
        return []

    base = base_color_override or profile.base_color
    if base is None:
        raise ValueError("base_color_override required when profile.base_color is None")
    period = len(text) + profile.padding * 2
    elapsed_s = elapsed_ms / 1000.0
    pos = (elapsed_s % profile.sweep_seconds) / profile.sweep_seconds * period
    if profile.direction < 0:
        pos = period - pos

    colors: list[str] = []
    for i in range(len(text)):
        i_pos = i + profile.padding
        dist = abs(i_pos - pos)
        if dist <= profile.band_half_width:
            intensity = 0.5 * (1.0 + math.cos(math.pi * dist / profile.band_half_width))
        else:
            intensity = 0.0
        colors.append(
            blend_hex(base, profile.highlight_color, intensity * profile.max_intensity)
        )

    # Coalesce adjacent same-color characters into segments
    segments: list[tuple[str, str]] = []
    run_start = 0
    for i in range(1, len(colors)):
        if colors[i] != colors[run_start]:
            segments.append((text[run_start:i], colors[run_start]))
            run_start = i
    segments.append((text[run_start:], colors[run_start]))
    return segments
