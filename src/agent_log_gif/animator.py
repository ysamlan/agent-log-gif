"""Animation engine: converts replay events into a sequence of terminal frames.

Produces typing animations for user/assistant messages and a braille spinner
between them.
"""

from __future__ import annotations

import random
import textwrap

from PIL import Image

from agent_log_gif.renderer import StyledLine, TerminalRenderer
from agent_log_gif.spinner import RAINBOW_COLORS, SPINNER_FRAMES, SPINNER_VERBS
from agent_log_gif.theme import TerminalTheme
from agent_log_gif.timeline import EventType, ReplayEvent

# Characters per frame for typing animation
USER_CHARS_PER_FRAME = 3
ASSISTANT_CHARS_PER_FRAME = 10

# Frame durations in milliseconds
USER_FRAME_MS = 80
ASSISTANT_FRAME_MS = 50
SPINNER_FRAME_MS = 80
PAUSE_MS = 300  # pause between turns

# Number of spinner cycles to show
SPINNER_CYCLES = 3

# Unicode characters
PROMPT_CHAR = "\u276f"  # ❯
ASSISTANT_CHAR = "\u25cf"  # ●
SEPARATOR_CHAR = "\u2500"  # ─


def _wrap_text(text: str, width: int, prefix_len: int = 0) -> list[str]:
    """Wrap text to fit within terminal width, accounting for prefix on first line."""
    if not text:
        return [""]

    # First line has less space due to prefix
    first_width = max(width - prefix_len, 20)
    subsequent_width = max(width - 2, 20)  # 2 chars indent for continuation

    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue

        if not lines:
            wrapped = textwrap.wrap(paragraph, width=first_width) or [""]
            lines.extend(wrapped)
        else:
            wrapped = textwrap.wrap(paragraph, width=subsequent_width) or [""]
            lines.extend(wrapped)

    return lines


def generate_frames(
    events: list[ReplayEvent],
    theme: TerminalTheme | None = None,
    renderer: TerminalRenderer | None = None,
) -> list[tuple[Image.Image, int]]:
    """Convert replay events into animated frames.

    Args:
        events: List of ReplayEvent to animate. Only USER_MESSAGE and
                ASSISTANT_MESSAGE are rendered; others are skipped.
        theme: Terminal theme (uses defaults if None).
        renderer: Terminal renderer (creates one from theme if None).

    Returns:
        List of (PIL.Image, duration_ms) tuples.
    """
    if theme is None:
        theme = TerminalTheme()
    if renderer is None:
        renderer = TerminalRenderer(theme)

    frames: list[tuple[Image.Image, int]] = []
    # Persistent text buffer (list of styled lines) that grows over time
    buffer: list[StyledLine] = []

    # Track turns for separator placement
    last_event_type = None

    for event in events:
        if event.type == EventType.USER_MESSAGE:
            # Add separator if this isn't the first turn
            if last_event_type is not None:
                separator_width = min(theme.cols - 4, 40)
                buffer.append(
                    [(SEPARATOR_CHAR * separator_width, theme.separator_color)]
                )
                buffer.append([])  # blank line
                frames.append((renderer.render_frame(buffer), PAUSE_MS))

            # Type user message with ❯ prefix
            _animate_typing(
                buffer=buffer,
                frames=frames,
                renderer=renderer,
                text=event.text,
                prefix_char=PROMPT_CHAR,
                prefix_color=theme.prompt_color,
                text_color=theme.foreground,
                chars_per_frame=USER_CHARS_PER_FRAME,
                frame_ms=USER_FRAME_MS,
                cols=theme.cols,
            )

            # Pause after user message
            frames.append((renderer.render_frame(buffer), PAUSE_MS))

            # Spinner animation
            _animate_spinner(
                buffer=buffer,
                frames=frames,
                renderer=renderer,
                theme=theme,
            )

            last_event_type = event.type

        elif event.type == EventType.ASSISTANT_MESSAGE:
            # Type assistant message with ● prefix
            _animate_typing(
                buffer=buffer,
                frames=frames,
                renderer=renderer,
                text=event.text,
                prefix_char=ASSISTANT_CHAR,
                prefix_color=theme.assistant_color,
                text_color=theme.foreground,
                chars_per_frame=ASSISTANT_CHARS_PER_FRAME,
                frame_ms=ASSISTANT_FRAME_MS,
                cols=theme.cols,
            )

            # Brief pause after assistant
            frames.append((renderer.render_frame(buffer), PAUSE_MS))
            last_event_type = event.type

    # Hold final frame a bit longer
    if frames:
        last_img, _ = frames[-1]
        frames[-1] = (last_img, 2000)

    return frames


def _animate_typing(
    *,
    buffer: list[StyledLine],
    frames: list[tuple[Image.Image, int]],
    renderer: TerminalRenderer,
    text: str,
    prefix_char: str,
    prefix_color: str,
    text_color: str,
    chars_per_frame: int,
    frame_ms: int,
    cols: int,
) -> None:
    """Add typing animation frames for a message."""
    prefix = f"{prefix_char} "
    prefix_len = len(prefix)

    wrapped_lines = _wrap_text(text, cols, prefix_len)

    # Build the full styled lines that will appear when typing is complete
    full_lines: list[StyledLine] = []
    for i, line_text in enumerate(wrapped_lines):
        if i == 0:
            full_lines.append([(prefix, prefix_color), (line_text, text_color)])
        else:
            # Continuation lines get indented
            full_lines.append([("  " + line_text, text_color)])

    # Calculate total characters to type (excluding prefix on first line)
    total_chars = sum(len(line) for line in wrapped_lines)
    if total_chars == 0:
        buffer.extend(full_lines)
        return

    # Generate frames at intervals
    chars_typed = 0
    while chars_typed < total_chars:
        chars_typed = min(chars_typed + chars_per_frame, total_chars)

        # Build partial lines based on how many chars have been typed
        partial_lines: list[StyledLine] = []
        remaining = chars_typed
        for i, line_text in enumerate(wrapped_lines):
            if remaining <= 0:
                break
            visible_len = min(remaining, len(line_text))
            visible_text = line_text[:visible_len]
            remaining -= visible_len

            if i == 0:
                partial_lines.append(
                    [(prefix, prefix_color), (visible_text, text_color)]
                )
            else:
                partial_lines.append([("  " + visible_text, text_color)])

        # Render with partial content appended to buffer
        snapshot = buffer + partial_lines
        frames.append((renderer.render_frame(snapshot), frame_ms))

    # Commit full lines to buffer
    buffer.extend(full_lines)


def _animate_spinner(
    *,
    buffer: list[StyledLine],
    frames: list[tuple[Image.Image, int]],
    renderer: TerminalRenderer,
    theme: TerminalTheme,
) -> None:
    """Add spinner animation frames between user and assistant messages."""
    verb = random.choice(SPINNER_VERBS)
    total_frames = len(SPINNER_FRAMES) * SPINNER_CYCLES

    for i in range(total_frames):
        frame_char = SPINNER_FRAMES[i % len(SPINNER_FRAMES)]
        color = RAINBOW_COLORS[i % len(RAINBOW_COLORS)]

        spinner_line: StyledLine = [
            (f"{frame_char} ", color),
            (f"{verb}...", color),
        ]

        # Temporarily append spinner line to buffer
        snapshot = buffer + [spinner_line]
        frames.append((renderer.render_frame(snapshot), SPINNER_FRAME_MS))

    # Add a blank line after spinner (spinner line is not committed to buffer)
    buffer.append([])
