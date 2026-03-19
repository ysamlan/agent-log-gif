"""Animation engine: converts replay events into a sequence of terminal frames.

Produces typing animations for user/assistant messages and a braille spinner
between them.
"""

from __future__ import annotations

import random
import textwrap

from PIL import Image

from agent_log_gif.parsers import truncate_text
from agent_log_gif.renderer import HIGHLIGHT_MARKER, StyledLine, TerminalRenderer
from agent_log_gif.spinner import SPINNER_COLOR, SPINNER_FRAMES, SPINNER_VERBS
from agent_log_gif.theme import TerminalTheme
from agent_log_gif.timeline import EventType, ReplayEvent

# Characters per frame for typing animation
USER_CHARS_PER_FRAME = 3
ASSISTANT_CHARS_PER_FRAME = 10

# Frame durations in milliseconds
USER_FRAME_MS = 80
ASSISTANT_FRAME_MS = 50
SPINNER_FRAME_MS = 140
PAUSE_MS = 300  # pause between turns

# Number of spinner cycles to show
SPINNER_CYCLES = 3

# Unicode characters
PROMPT_CHAR = "\u276f"  # ❯
ASSISTANT_CHAR = "\u25cf"  # ●
SEPARATOR_CHAR = "\u2500"  # ─
BLOCK_CHAR = "\u25c6"  # ◆ (used for tool calls and thinking)

# Max lines to show for tool results and thinking blocks
TOOL_RESULT_MAX_LINES = 4
THINKING_MAX_LINES = 3


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


def _snap_muted_block(
    buffer: list[StyledLine],
    prefix: str,
    text: str,
    theme: TerminalTheme,
    max_lines: int | None = None,
    trailing_blank: bool = False,
) -> None:
    """Append a muted text block to the buffer (no typing animation).

    Used for tool calls, tool results, and thinking blocks.
    Text is split by newlines, truncated to max_lines, and each line
    is capped to the terminal width.
    """
    max_width = theme.cols - len(prefix)
    lines = text.split("\n")
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append("\u2026")  # …
    for i, line_text in enumerate(lines):
        line_text = truncate_text(line_text, max_width)
        if i == 0:
            buffer.append([(prefix, theme.comment), (line_text, theme.comment)])
        else:
            indent = " " * len(prefix)
            buffer.append([(indent + line_text, theme.comment)])
    if trailing_blank:
        buffer.append([])


def generate_frames(
    events: list[ReplayEvent],
    theme: TerminalTheme | None = None,
    renderer: TerminalRenderer | None = None,
    transcript_source: str = "claude",
    speed: float = 1.0,
    spinner_time: float = 1.0,
    thinking_verbs: list[str] | None = None,
) -> list[tuple[Image.Image, int]]:
    """Convert replay events into animated frames.

    Args:
        events: List of ReplayEvent to animate. Renders USER_MESSAGE,
                ASSISTANT_MESSAGE, and optionally TOOL_CALL, TOOL_RESULT,
                THINKING (when included via --show).
        theme: Terminal theme (uses defaults if None). Ignored if renderer is provided.
        renderer: Terminal renderer (creates one from theme if None).
        speed: Typing speed multiplier (2.0 = twice as fast, 0.5 = half speed).
        spinner_time: Spinner duration multiplier (0.5 = half the spinner cycles).
        thinking_verbs: Custom spinner verb list. Defaults to built-in whimsical verbs.

    Returns:
        List of (PIL.Image, duration_ms) tuples.
    """
    if renderer is None:
        if theme is None:
            theme = TerminalTheme()
        renderer = TerminalRenderer(theme)
    theme = renderer.theme

    # Apply speed multiplier to typing animation
    user_chars = max(1, int(USER_CHARS_PER_FRAME * speed))
    user_ms = max(10, int(USER_FRAME_MS / speed))
    asst_chars = max(1, int(ASSISTANT_CHARS_PER_FRAME * speed))
    asst_ms = max(10, int(ASSISTANT_FRAME_MS / speed))
    pause_ms = max(50, int(PAUSE_MS / speed))

    # Apply spinner_time multiplier
    spin_cycles = max(1, int(SPINNER_CYCLES * spinner_time))

    # Custom or default verbs
    verbs = thinking_verbs if thinking_verbs is not None else SPINNER_VERBS

    frames: list[tuple[Image.Image, int]] = []
    # Persistent text buffer (list of styled lines) that grows over time
    buffer: list[StyledLine] = []

    # The prompt area: a blank separator line + the ❯ prompt, always at the bottom.
    # This keeps a fixed gap between the scrolling content and the input area.
    prompt_line: StyledLine = [(f"{PROMPT_CHAR} ", theme.prompt_color)]
    prompt_area: list[StyledLine] = [[], prompt_line]

    def _snap(lines: list[StyledLine], duration: int) -> tuple[Image.Image, int]:
        """Render a frame with the prompt area (gap + ❯) at the bottom."""
        return (renderer.render_frame(lines + prompt_area), duration)

    # Track turns for separator placement
    last_event_type = None

    for event in events:
        if event.type == EventType.USER_MESSAGE:
            # Add separator + blank line between turns
            if last_event_type is not None:
                buffer.append([])  # breathing room after previous message
                separator_width = min(theme.cols - 4, 40)
                buffer.append(
                    [(SEPARATOR_CHAR * separator_width, theme.separator_color)]
                )
                buffer.append([])  # blank line after separator
                frames.append(_snap(buffer, pause_ms))

            # User types directly on the bottom prompt line
            _animate_user_typing(
                buffer=buffer,
                frames=frames,
                renderer=renderer,
                text=event.text,
                theme=theme,
                chars_per_frame=user_chars,
                frame_ms=user_ms,
            )

            # Blank line after user message before spinner/response
            buffer.append([])

            # Pause after user message
            frames.append(_snap(buffer, pause_ms))

            # Spinner animation
            _animate_spinner(
                buffer=buffer,
                frames=frames,
                renderer=renderer,
                theme=theme,
                prompt_area=prompt_area,
                transcript_source=transcript_source,
                cycles=spin_cycles,
                verbs=verbs,
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
                chars_per_frame=asst_chars,
                frame_ms=asst_ms,
                cols=theme.cols,
                prompt_area=prompt_area,
            )

            # Brief pause after assistant
            frames.append(_snap(buffer, pause_ms))
            last_event_type = event.type

        elif event.type == EventType.TOOL_CALL:
            _snap_muted_block(buffer, f"{BLOCK_CHAR} ", event.text, theme)
            frames.append(_snap(buffer, pause_ms))
            last_event_type = event.type

        elif event.type == EventType.TOOL_RESULT:
            _snap_muted_block(
                buffer,
                "    ",
                event.text,
                theme,
                max_lines=TOOL_RESULT_MAX_LINES,
                trailing_blank=True,
            )
            frames.append(_snap(buffer, pause_ms))
            last_event_type = event.type

        elif event.type == EventType.THINKING:
            _snap_muted_block(
                buffer,
                f"{BLOCK_CHAR} Thinking\u2026 ",
                event.text,
                theme,
                max_lines=THINKING_MAX_LINES,
                trailing_blank=True,
            )
            frames.append(_snap(buffer, pause_ms))
            last_event_type = event.type

    # Hold final frame a bit longer
    if frames:
        last_img, _ = frames[-1]
        frames[-1] = (last_img, 2000)

    return frames


def _animate_user_typing(
    *,
    buffer: list[StyledLine],
    frames: list[tuple[Image.Image, int]],
    renderer: TerminalRenderer,
    text: str,
    theme: TerminalTheme,
    chars_per_frame: int = USER_CHARS_PER_FRAME,
    frame_ms: int = USER_FRAME_MS,
) -> None:
    """Animate user typing on the bottom prompt line, then 'send' it to the buffer.

    The user types directly on the ❯ line at the bottom. The input area
    grows (wraps to additional lines) as text exceeds the terminal width,
    pushing the content above upward. When typing completes, the text
    moves up into the buffer and the input area shrinks back to one line.
    """
    prefix = f"{PROMPT_CHAR} "
    prefix_len = len(prefix)
    max_first_line = theme.cols - prefix_len
    max_cont_line = theme.cols - 2  # continuation indent

    # Progressive typing — input area grows as text wraps
    chars_typed = 0
    while chars_typed < len(text):
        chars_typed = min(chars_typed + chars_per_frame, len(text))
        visible = text[:chars_typed]

        # Wrap the visible text into input area lines (all highlighted)
        input_lines: list[StyledLine] = []
        remaining = visible
        first = True
        while remaining:
            if first:
                chunk = remaining[:max_first_line]
                remaining = remaining[max_first_line:]
                input_lines.append(
                    [
                        (prefix, theme.prompt_color),
                        (chunk, theme.foreground),
                        HIGHLIGHT_MARKER,
                    ]
                )
                first = False
            else:
                chunk = remaining[:max_cont_line]
                remaining = remaining[max_cont_line:]
                input_lines.append([("  " + chunk, theme.foreground), HIGHLIGHT_MARKER])

        # Content above + growing input area at bottom (no gap — it IS the input)
        snapshot = buffer + input_lines
        frames.append((renderer.render_frame(snapshot), frame_ms))

    # "Send" — move the completed text into the buffer with wrapped lines (all highlighted)
    wrapped_lines = _wrap_text(text, theme.cols, prefix_len)
    for i, line_text in enumerate(wrapped_lines):
        if i == 0:
            buffer.append(
                [
                    (prefix, theme.prompt_color),
                    (line_text, theme.foreground),
                    HIGHLIGHT_MARKER,
                ]
            )
        else:
            buffer.append([("  " + line_text, theme.foreground), HIGHLIGHT_MARKER])


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
    prompt_area: list[StyledLine],
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

        # Render with partial content appended to buffer + prompt line at bottom
        snapshot = buffer + partial_lines + prompt_area
        frames.append((renderer.render_frame(snapshot), frame_ms))

    # Commit full lines to buffer
    buffer.extend(full_lines)


def _animate_spinner(
    *,
    buffer: list[StyledLine],
    frames: list[tuple[Image.Image, int]],
    renderer: TerminalRenderer,
    theme: TerminalTheme,
    prompt_area: list[StyledLine],
    transcript_source: str = "claude",
    cycles: int = SPINNER_CYCLES,
    verbs: list[str] | None = None,
) -> None:
    """Add spinner animation frames between user and assistant messages.

    Claude Code: star character cycles through 6 glyphs in brand orange,
    with a random whimsical verb.
    Codex: static bullet with "Working…" and elapsed time, no animation.
    """
    if transcript_source == "codex":
        # Codex style: "• Working (Xs · esc to interrupt)" — static, no animation
        # Use custom verbs if provided, otherwise just "Working"
        codex_verb = random.choice(verbs) if verbs is not None else "Working"
        total_frames = cycles * len(SPINNER_FRAMES)
        for i in range(total_frames):
            elapsed = (i * SPINNER_FRAME_MS) // 1000
            spinner_line: StyledLine = [
                ("• ", theme.comment),
                (codex_verb, theme.comment),
                (f" ({elapsed}s · esc to interrupt)", theme.comment),
            ]
            snapshot = buffer + [spinner_line] + prompt_area
            frames.append((renderer.render_frame(snapshot), SPINNER_FRAME_MS))
    else:
        # Claude Code style: cycling star + random verb in brand orange
        verb_list = verbs if verbs is not None else SPINNER_VERBS
        verb = random.choice(verb_list)
        total_frames = len(SPINNER_FRAMES) * cycles

        for i in range(total_frames):
            frame_char = SPINNER_FRAMES[i % len(SPINNER_FRAMES)]

            spinner_line: StyledLine = [
                (f"{frame_char} ", SPINNER_COLOR),
                (f"{verb}\u2026", SPINNER_COLOR),
                (" (esc to interrupt)", theme.comment),
            ]

            snapshot = buffer + [spinner_line] + prompt_area
            frames.append((renderer.render_frame(snapshot), SPINNER_FRAME_MS))

    # Add a blank line after spinner (spinner line is not committed to buffer)
    buffer.append([])
