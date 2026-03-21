"""Animation engine: converts replay events into a sequence of terminal frames.

See ``docs/ui-layout-model.md`` for the full layout model.

Fixed height invariant: transient (1 line) + composer (3 lines) = 4 lines.
The renderer is bottom-aligned, so the loading line and prompt are always
pinned at the same pixel row. Only transcript content scrolls.
"""

from __future__ import annotations

import random
import textwrap
from collections.abc import Callable
from datetime import datetime

from agent_log_gif.frame_store import FrameStore
from agent_log_gif.layout import LayoutFrame, compose_lines
from agent_log_gif.parsers import truncate_text
from agent_log_gif.renderer import HIGHLIGHT_MARKER, StyledLine, TerminalRenderer
from agent_log_gif.spinner import (
    CLAUDE_SHIMMER,
    CODEX_SHIMMER,
    SPINNER_COLOR,
    SPINNER_FRAMES,
    SPINNER_VERBS,
    TOOL_DONE_COLOR,
    ShimmerProfile,
    shimmer_styled_segments,
)
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
BLOCK_CHAR = "\u25c6"  # ◆ (used for tool calls and thinking)

# Max lines to show for tool results and thinking blocks
TOOL_RESULT_MAX_LINES = 1
THINKING_MAX_LINES = 3

# Max wrapped lines for long messages (first N/2 + "…" + last N/2)
USER_MESSAGE_MAX_LINES = 12
ASSISTANT_MESSAGE_MAX_LINES = 20


class StatusFooter:
    """Persistent loading line below transcript, above prompt.

    States:
      idle     -- before first user message (blank row)
      thinking -- after user sends, through assistant responses + tool calls
      done     -- after all responses/tools complete for a turn

    Composer is always 3 lines: [status, gap, prompt].
    """

    def __init__(
        self,
        theme: TerminalTheme,
        verbs: list[str],
        transcript_source: str = "claude",
        shimmer: bool = True,
    ):
        self._theme = theme
        self._verbs = verbs
        self._transcript_source = transcript_source
        self._shimmer = shimmer
        self._state = "idle"
        self._frame_idx = 0
        self._verb = ""
        self._done_text = ""

    @property
    def state(self) -> str:
        return self._state

    def start_thinking(self) -> None:
        """Pick new random verb, reset frame index, state -> thinking."""
        self._state = "thinking"
        self._verb = random.choice(self._verbs)
        self._frame_idx = 0

    def mark_done(self, duration_s: int | None = None) -> None:
        """State -> done. Shows 'Churned for Xs' or 'Churned'."""
        self._state = "done"
        if duration_s is not None:
            self._done_text = f"Churned for {duration_s}s"
        else:
            self._done_text = "Churned"

    def tick(self) -> None:
        """Advance spinner glyph (call each frame during thinking)."""
        if self._state == "thinking":
            self._frame_idx += 1

    def _shimmer_or_flat(
        self,
        text: str,
        profile: "ShimmerProfile",
        elapsed_ms: int,
        flat_color: str,
        base_color_override: str | None = None,
    ) -> StyledLine:
        """Return shimmered segments or a single flat-color segment."""
        if self._shimmer:
            return list(
                shimmer_styled_segments(
                    text,
                    profile,
                    elapsed_ms,
                    base_color_override=base_color_override,
                )
            )
        return [(text, flat_color)]

    def render_line(self) -> StyledLine:
        """Return styled line for current state (blank when idle)."""
        if self._state == "thinking":
            elapsed_ms = self._frame_idx * SPINNER_FRAME_MS
            if self._transcript_source == "codex":
                elapsed = elapsed_ms // 1000
                segments: StyledLine = [("\u2022 ", self._theme.comment)]
                segments.extend(
                    self._shimmer_or_flat(
                        self._verb,
                        CODEX_SHIMMER,
                        elapsed_ms,
                        self._theme.comment,
                        base_color_override=self._theme.comment,
                    )
                )
                segments.append(
                    (f" ({elapsed}s \u00b7 esc to interrupt)", self._theme.comment)
                )
                return segments
            glyph = SPINNER_FRAMES[self._frame_idx % len(SPINNER_FRAMES)]
            segments = list(
                self._shimmer_or_flat(
                    f"{glyph} {self._verb}\u2026",
                    CLAUDE_SHIMMER,
                    elapsed_ms,
                    SPINNER_COLOR,
                )
            )
            segments.append((" (esc to interrupt)", self._theme.comment))
            return segments
        if self._state == "done":
            return [
                ("\u273b ", self._theme.comment),
                (self._done_text, self._theme.comment),
            ]
        return []

    def build_prompt_area(self, prompt_line: StyledLine) -> list[StyledLine]:
        """Return composer lines: always exactly 3 lines.

        ``[status, gap, prompt]`` — the status line is blank when idle,
        the gap separates status from the highlighted prompt line.
        This keeps the composer height constant across all frames.
        """
        return [self.render_line(), [], prompt_line]


def _compute_turn_duration(
    start_event: ReplayEvent, end_event: ReplayEvent
) -> int | None:
    """Compute seconds between two events from their ISO 8601 timestamps."""
    if not start_event.timestamp or not end_event.timestamp:
        return None
    try:
        start = datetime.fromisoformat(start_event.timestamp)
        end = datetime.fromisoformat(end_event.timestamp)
        return max(0, int((end - start).total_seconds()))
    except (ValueError, TypeError):
        return None


def _tool_done_line(text: str, theme: TerminalTheme) -> StyledLine:
    """Styled line for a completed tool call: green ● + tool name."""
    return [(f"{ASSISTANT_CHAR} ", TOOL_DONE_COLOR), (text, theme.comment)]


def _tool_preview_text(text: str) -> str:
    """Flatten multiline tool text for the single-row transient preview."""
    parts = [part.strip() for part in text.splitlines()]
    return " ".join(part for part in parts if part)


def _append_tool_call_block(
    buffer: list[StyledLine], text: str, theme: TerminalTheme
) -> None:
    """Append a committed tool call, preserving embedded newlines as rows."""
    lines = text.splitlines() or [text]
    first, *rest = lines
    buffer.append(_tool_done_line(first, theme))
    for line_text in rest:
        buffer.append([("  ", theme.comment), (line_text, theme.comment)])


def _elide_wrapped_lines(lines: list[str], max_lines: int) -> list[str]:
    """Elide wrapped lines: first half + '…' + last half if over max_lines."""
    if len(lines) <= max_lines:
        return lines
    head = max_lines // 2
    tail = max_lines - head - 1  # -1 for the ellipsis line
    omitted = len(lines) - head - tail
    return lines[:head] + [f"\u2026 ({omitted} more lines)"] + lines[-tail:]


def _wrap_text(text: str, width: int, prefix_len: int = 0) -> list[str]:
    """Wrap text to fit within terminal width, accounting for prefix on first line."""
    if not text:
        return [""]

    # Reserve 1 column so text doesn't butt against the right padding edge
    width = width - 1

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
        if max_lines <= 1:
            # Single-line mode: first line + count
            omitted = len(lines) - 1
            lines = [lines[0], f"\u2026 +{omitted} lines"]
        else:
            # Head/tail elision
            lines = _elide_wrapped_lines(lines, max_lines)
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
    on_turn: Callable[[int, int], None] | None = None,
    shimmer: bool = True,
) -> FrameStore:
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
        FrameStore of (PIL.Image, duration_ms) tuples (compressed in memory).
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

    frames = FrameStore()
    # Persistent text buffer (list of styled lines) that grows over time
    buffer: list[StyledLine] = []

    # Status footer and prompt line
    footer = StatusFooter(theme, verbs, transcript_source, shimmer=shimmer)
    prompt_line: StyledLine = [(f"{PROMPT_CHAR} ", theme.prompt_color)]
    prompt_line.append(HIGHLIGHT_MARKER)

    def _snap(lines: list[StyledLine], duration: int) -> None:
        """Render a frame and append to store.

        Transient placeholder keeps fixed height = 4 (1 transient + 3
        composer) across all frames, preventing vertical jumps.
        """
        composed = compose_lines(
            LayoutFrame(
                transcript=lines,
                transient=[[]],
                composer=footer.build_prompt_area(prompt_line),
            ),
            theme.rows,
        )
        frames.append(renderer.render_frame(composed), duration)

    # Turn tracking for progress reporting
    total_turns = sum(1 for e in events if e.type == EventType.USER_MESSAGE)
    current_turn = 0
    turn_start_event: ReplayEvent | None = None
    pending_tool_text: str | None = None

    for idx, event in enumerate(events):
        next_event = events[idx + 1] if idx + 1 < len(events) else None

        # Commit pending tool call if next event isn't TOOL_RESULT
        if pending_tool_text is not None and event.type != EventType.TOOL_RESULT:
            _append_tool_call_block(buffer, pending_tool_text, theme)
            pending_tool_text = None

        if event.type == EventType.USER_MESSAGE:
            current_turn += 1
            if on_turn is not None:
                on_turn(current_turn, total_turns)

            # If footer is still thinking from a previous turn that ended
            # without an ASSISTANT_MESSAGE (e.g. ended with TOOL_RESULT),
            # mark it done before the next user starts typing.
            if footer.state == "thinking" and turn_start_event is not None:
                prev_event = events[idx - 1] if idx > 0 else None
                duration = (
                    _compute_turn_duration(turn_start_event, prev_event)
                    if prev_event
                    else None
                )
                footer.mark_done(duration)

            turn_start_event = event

            # User types directly on the bottom prompt line
            _animate_user_typing(
                buffer=buffer,
                frames=frames,
                renderer=renderer,
                text=event.text,
                theme=theme,
                footer=footer,
                chars_per_frame=user_chars,
                frame_ms=user_ms,
            )

            # Blank line after user message before spinner/response
            buffer.append([])

            # Transition footer to thinking
            footer.start_thinking()

            # Pause after user message
            _snap(buffer, pause_ms)

            # Thinking pause animation (spinner in footer)
            _animate_footer_loop(
                buffer=buffer,
                frames=frames,
                renderer=renderer,
                theme=theme,
                footer=footer,
                prompt_line=prompt_line,
                cycles=spin_cycles,
            )

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
                theme=theme,
                footer=footer,
                prompt_line=prompt_line,
            )

            if next_event is None or next_event.type == EventType.USER_MESSAGE:
                duration = (
                    _compute_turn_duration(turn_start_event, event)
                    if turn_start_event
                    else None
                )
                footer.mark_done(duration)
                buffer.append([])

            # Brief pause after assistant
            _snap(buffer, pause_ms)

        elif event.type == EventType.TOOL_CALL:
            pending_tool_text = event.text
            tool_text = _tool_preview_text(event.text)

            def _blink_transient(i: int) -> list[StyledLine]:
                color = theme.comment if (i // 3) % 2 == 0 else theme.background
                return [[(f"{ASSISTANT_CHAR} ", color), (tool_text, theme.comment)]]

            _animate_footer_loop(
                buffer=buffer,
                frames=frames,
                renderer=renderer,
                theme=theme,
                footer=footer,
                prompt_line=prompt_line,
                cycles=spin_cycles,
                transient_fn=_blink_transient,
            )

        elif event.type == EventType.TOOL_RESULT:
            if pending_tool_text is not None:
                _append_tool_call_block(buffer, pending_tool_text, theme)
                pending_tool_text = None
            _snap_muted_block(
                buffer,
                "    ",
                event.text,
                theme,
                max_lines=TOOL_RESULT_MAX_LINES,
                trailing_blank=True,
            )
            _snap(buffer, pause_ms)

        elif event.type == EventType.THINKING:
            _snap_muted_block(
                buffer,
                f"{BLOCK_CHAR} Thinking\u2026 ",
                event.text,
                theme,
                max_lines=THINKING_MAX_LINES,
                trailing_blank=True,
            )
            _snap(buffer, pause_ms)

    # Commit any remaining pending tool call
    if pending_tool_text is not None:
        _append_tool_call_block(buffer, pending_tool_text, theme)

    # If footer is still thinking, mark done
    if footer.state == "thinking":
        duration = (
            _compute_turn_duration(turn_start_event, events[-1])
            if turn_start_event and events
            else None
        )
        footer.mark_done(duration)

    # Hold final frame a bit longer
    if frames:
        frames.set_duration(-1, 2000)

    return frames


def _animate_user_typing(
    *,
    buffer: list[StyledLine],
    frames: FrameStore,
    renderer: TerminalRenderer,
    text: str,
    theme: TerminalTheme,
    footer: StatusFooter,
    chars_per_frame: int = USER_CHARS_PER_FRAME,
    frame_ms: int = USER_FRAME_MS,
) -> None:
    """Animate user typing on the bottom prompt line, then 'send' it to the buffer.

    The user types directly on the input line at the bottom. The input area
    grows (wraps to additional lines) as text exceeds the terminal width,
    pushing the content above upward. When typing completes, the text
    moves up into the buffer and the input area shrinks back to one line.

    On turns 2+, the footer shows "Churned for Xs" from the previous turn.
    """
    prefix = f"{PROMPT_CHAR} "
    prefix_len = len(prefix)
    max_first_line = theme.cols - prefix_len
    max_cont_line = theme.cols - 2  # continuation indent

    # Wrap once, elide if needed — reuse for both typing animation and buffer commit
    wrapped_lines = _wrap_text(text, theme.cols, prefix_len)
    wrapped_lines = _elide_wrapped_lines(wrapped_lines, USER_MESSAGE_MAX_LINES)

    # Flatten wrapped lines into a single string for progressive typing
    flat_text = "\n".join(wrapped_lines)

    # Progressive typing — input area grows as text wraps
    chars_typed = 0
    while chars_typed < len(flat_text):
        chars_typed = min(chars_typed + chars_per_frame, len(flat_text))
        visible = flat_text[:chars_typed]

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

        # Composer: [status, gap, input_lines...] — input replaces the prompt.
        # Transient placeholder is the gap between transcript and pinned area.
        composer = [footer.render_line(), []] + input_lines
        composed = compose_lines(
            LayoutFrame(transcript=buffer, transient=[[]], composer=composer),
            theme.rows,
        )
        frames.append(renderer.render_frame(composed), frame_ms)

    # "Send" — move the completed text into the buffer (reuse wrapped_lines)
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
    frames: FrameStore,
    renderer: TerminalRenderer,
    text: str,
    prefix_char: str,
    prefix_color: str,
    text_color: str,
    chars_per_frame: int,
    frame_ms: int,
    theme: TerminalTheme,
    footer: StatusFooter,
    prompt_line: StyledLine,
) -> None:
    """Add typing animation frames for a message, ticking the footer spinner."""
    prefix = f"{prefix_char} "
    prefix_len = len(prefix)

    wrapped_lines = _wrap_text(text, theme.cols, prefix_len)

    # Elide long assistant messages — show head + "…" + tail
    wrapped_lines = _elide_wrapped_lines(wrapped_lines, ASSISTANT_MESSAGE_MAX_LINES)

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
    frame_count = 0
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

        # Tick footer periodically (~every 3 frames to approximate SPINNER_FRAME_MS)
        if frame_count % 3 == 0:
            footer.tick()

        # Render with partial content as transient + dynamic composer at bottom
        prompt_area = footer.build_prompt_area(prompt_line)
        composed = compose_lines(
            LayoutFrame(
                transcript=buffer, transient=partial_lines, composer=prompt_area
            ),
            theme.rows,
        )
        frames.append(renderer.render_frame(composed), frame_ms)
        frame_count += 1

    # Commit full lines to buffer
    buffer.extend(full_lines)


def _animate_footer_loop(
    *,
    buffer: list[StyledLine],
    frames: FrameStore,
    renderer: TerminalRenderer,
    theme: TerminalTheme,
    footer: StatusFooter,
    prompt_line: StyledLine,
    cycles: int = SPINNER_CYCLES,
    transient_fn: Callable[[int], list[StyledLine]] | None = None,
) -> None:
    """Run a spinner loop with the footer ticking each frame.

    Shared implementation for thinking pauses (empty transient) and tool
    call blinks (blinking bullet in transient). ``transient_fn(i)`` returns
    the transient lines for frame *i*; defaults to a gap placeholder.
    """
    total_frames = len(SPINNER_FRAMES) * cycles
    for i in range(total_frames):
        transient = transient_fn(i) if transient_fn else [[]]
        prompt_area = footer.build_prompt_area(prompt_line)
        composed = compose_lines(
            LayoutFrame(transcript=buffer, transient=transient, composer=prompt_area),
            theme.rows,
        )
        frames.append(renderer.render_frame(composed), SPINNER_FRAME_MS)
        footer.tick()
