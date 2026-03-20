"""Tests for the animation engine."""

from agent_log_gif.animator import (
    StatusFooter,
    _compute_turn_duration,
    _elide_wrapped_lines,
    generate_frames,
)
from agent_log_gif.spinner import SPINNER_COLOR, SPINNER_FRAMES, TOOL_DONE_COLOR
from agent_log_gif.timeline import EventType, ReplayEvent


class TestFooterPromptSeparation:
    def test_prompt_highlight_does_not_bleed_into_footer(self):
        """The prompt's highlight band must not visually overlap the footer.

        The footer status line (e.g. "✳ Puzzling…") sits above the
        prompt ("❯"). With SSAA rendering, anti-aliased colors blend at
        boundaries. We check that there's at least half a character height
        of gap between the bottom of the spinner-influenced region and the
        top of the selection-influenced region.
        """
        from agent_log_gif.renderer import TerminalRenderer
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()
        renderer = TerminalRenderer(theme)
        half_char = renderer._char_height_ss // (renderer._SSAA * 2)

        frames = generate_frames(
            [
                ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
                ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hello"),
            ],
            theme=theme,
            thinking_verbs=["Thinking"],
        )

        thinking_img = frames[10][0]
        spinner_rgb = theme.hex_to_rgb(SPINNER_COLOR)
        selection_rgb = theme.hex_to_rgb(theme.selection_color)

        def _is_near(px, target, tol=20):
            return all(abs(a - b) <= tol for a, b in zip(px, target))

        # Scan the left region for spinner-colored pixels (bottom-up)
        spinner_bottom = None
        for y in range(thinking_img.height - 1, 0, -1):
            if any(
                _is_near(thinking_img.getpixel((x, y)), spinner_rgb, tol=60)
                for x in range(10, 200, 10)
            ):
                spinner_bottom = y
                break

        # Scan full-width for selection highlight below the spinner
        prompt_highlight_top = None
        if spinner_bottom:
            for y in range(spinner_bottom + 1, thinking_img.height):
                if any(
                    _is_near(thinking_img.getpixel((x, y)), selection_rgb, tol=10)
                    for x in range(0, thinking_img.width, 20)
                ):
                    prompt_highlight_top = y
                    break

        assert spinner_bottom is not None, "Should find spinner pixels"
        assert prompt_highlight_top is not None, "Should find prompt highlight"

        gap = prompt_highlight_top - spinner_bottom
        assert gap >= half_char, (
            f"Only {gap}px between footer (bottom={spinner_bottom}) and "
            f"prompt highlight (top={prompt_highlight_top}); need >= {half_char}px"
        )


class TestStatusFooter:
    def test_default_state_is_idle(self):
        """StatusFooter starts idle with a blank render line."""
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()
        footer = StatusFooter(theme, ["Thinking"], "claude")
        assert footer.state == "idle"
        assert footer.render_line() == []

    def test_thinking_renders_spinner_glyph(self):
        """Thinking state renders a spinner glyph line."""
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()
        footer = StatusFooter(theme, ["Thinking"], "claude")
        footer.start_thinking()
        assert footer.state == "thinking"
        line = footer.render_line()
        assert len(line) > 0
        # First segment contains the first spinner glyph
        assert SPINNER_FRAMES[0] in line[0][0]

    def test_tick_advances_glyph(self):
        """tick() changes the spinner glyph."""
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()
        footer = StatusFooter(theme, ["Thinking"], "claude")
        footer.start_thinking()
        glyph_before = footer.render_line()[0][0]
        footer.tick()
        glyph_after = footer.render_line()[0][0]
        assert glyph_before != glyph_after
        assert SPINNER_FRAMES[0] in glyph_before
        assert SPINNER_FRAMES[1] in glyph_after

    def test_done_renders_churned_with_duration(self):
        """Done state shows 'Churned for Xs'."""
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()
        footer = StatusFooter(theme, ["Thinking"], "claude")
        footer.start_thinking()
        footer.mark_done(54)
        assert footer.state == "done"
        line = footer.render_line()
        assert "Churned for 54s" in line[1][0]

    def test_done_without_duration(self):
        """Done state without duration shows 'Churned'."""
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()
        footer = StatusFooter(theme, ["Thinking"], "claude")
        footer.start_thinking()
        footer.mark_done()
        line = footer.render_line()
        assert line[1][0] == "Churned"

    def test_prompt_area_always_three_lines(self):
        """Prompt area is always 3 lines: [status, gap, prompt].

        The status line is blank when idle, the gap separates it from
        the highlighted prompt. This keeps composer height constant.
        """
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()
        footer = StatusFooter(theme, ["Thinking"], "claude")
        prompt = [("\u276f ", theme.prompt_color)]

        # Idle: [blank_status, gap, prompt]
        area = footer.build_prompt_area(prompt)
        assert len(area) == 3
        assert area[0] == []  # blank status

        # Thinking: [spinner_status, gap, prompt]
        footer.start_thinking()
        area = footer.build_prompt_area(prompt)
        assert len(area) == 3
        assert len(area[0]) > 0  # has spinner content

        # Done: [done_status, gap, prompt]
        footer.mark_done(10)
        area = footer.build_prompt_area(prompt)
        assert len(area) == 3
        assert len(area[0]) > 0  # has churned content

    def test_codex_thinking_shows_working_style(self):
        """Codex transcript source uses bullet + elapsed time style."""
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()
        footer = StatusFooter(theme, ["Working"], "codex")
        footer.start_thinking()
        line = footer.render_line()
        assert line is not None
        assert "\u2022" in line[0][0]  # bullet •
        assert "Working" in line[1][0]
        assert "esc to interrupt" in line[2][0]


class TestComputeTurnDuration:
    def test_valid_timestamps(self):
        """Returns seconds between two ISO 8601 timestamps."""
        start = ReplayEvent(
            type=EventType.USER_MESSAGE,
            text="hi",
            timestamp="2024-01-01T00:00:00",
        )
        end = ReplayEvent(
            type=EventType.ASSISTANT_MESSAGE,
            text="hello",
            timestamp="2024-01-01T00:00:54",
        )
        assert _compute_turn_duration(start, end) == 54

    def test_missing_timestamps(self):
        """Returns None when timestamps are empty."""
        start = ReplayEvent(type=EventType.USER_MESSAGE, text="hi")
        end = ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="hello")
        assert _compute_turn_duration(start, end) is None

    def test_partial_timestamps(self):
        """Returns None when only one timestamp is present."""
        start = ReplayEvent(
            type=EventType.USER_MESSAGE,
            text="hi",
            timestamp="2024-01-01T00:00:00",
        )
        end = ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="hello")
        assert _compute_turn_duration(start, end) is None


class TestToolCallBlink:
    def test_tool_call_blink_produces_frames(self):
        """Tool call blink animation produces frames."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.TOOL_CALL, text="Bash echo hi"),
            ReplayEvent(type=EventType.TOOL_RESULT, text="hi"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Done"),
        ]
        frames = generate_frames(events)
        # Thinking pause (18) + tool blink (18) + other frames
        assert len(frames) > 36

    def test_tool_call_committed_with_green_bullet(self):
        """After tool result, green bullet color appears in the frame."""
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.TOOL_CALL, text="Bash echo hi"),
            ReplayEvent(type=EventType.TOOL_RESULT, text="hi"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Done"),
        ]
        frames = generate_frames(events, theme=theme)

        green_rgb = theme.hex_to_rgb(TOOL_DONE_COLOR)
        last_img = frames[-1][0]
        found = any(
            last_img.getpixel((x, y)) == green_rgb
            for y in range(last_img.height)
            for x in range(min(last_img.width, 50))
        )
        assert found, "Final frame should contain green bullet pixels"


class TestGenerateFrames:
    @staticmethod
    def _color_row_clusters(img, color, x_limit=250):
        rows = []
        for y in range(img.height):
            if any(
                img.getpixel((x, y)) == color for x in range(min(img.width, x_limit))
            ):
                rows.append(y)

        clusters = []
        for y in rows:
            if clusters and y == clusters[-1][1] + 1:
                clusters[-1] = (clusters[-1][0], y)
            else:
                clusters.append((y, y))
        return clusters

    def test_produces_frames(self):
        """Basic events produce a non-empty frame sequence."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hello"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hi there!"),
        ]
        frames = generate_frames(events)
        assert len(frames) > 1
        # Each frame is (Image, duration_ms)
        for img, ms in frames:
            assert img.size[0] > 0
            assert img.size[1] > 0
            assert ms > 0

    def test_spinner_frames_between_user_and_assistant(self):
        """Spinner frames appear between user message and assistant response."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hello"),
        ]
        frames = generate_frames(events)

        # Should have: user typing frames + pause + spinner frames + assistant typing + pause + hold
        # At minimum: 1 user frame + 1 pause + 18 spinner frames + 1 assistant frame + pause + hold
        assert len(frames) >= 18  # spinner alone is 18 frames (6 * 3 cycles)

    def test_empty_events(self):
        """Empty event list produces no frames."""
        frames = generate_frames([])
        assert len(frames) == 0

    def test_user_only(self):
        """Single user message with no assistant still produces frames."""
        events = [ReplayEvent(type=EventType.USER_MESSAGE, text="Hello world")]
        frames = generate_frames(events)
        assert len(frames) > 0

    def test_non_visible_events_filtered_by_visible_events(self):
        """Thinking and tool events are filtered out by visible_events()."""
        from agent_log_gif.timeline import visible_events

        events = [
            ReplayEvent(type=EventType.THINKING, text="hmm"),
            ReplayEvent(type=EventType.TOOL_CALL, text="Bash"),
            ReplayEvent(type=EventType.TOOL_RESULT, text="output"),
        ]
        assert visible_events(events) == []

    def test_tool_and_thinking_events_render_when_included(self):
        """Tool and thinking events produce frames when passed to generate_frames."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hello"),
            ReplayEvent(type=EventType.TOOL_CALL, text="Bash echo hi"),
            ReplayEvent(type=EventType.TOOL_RESULT, text="hi"),
            ReplayEvent(type=EventType.THINKING, text="Let me think"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Done"),
        ]
        frames = generate_frames(events)
        assert len(frames) > 0

    def test_multi_turn_second_user_typing_starts_after_assistant(self):
        """In a multi-turn conversation, user typing frames follow the assistant pause."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hello"),
            ReplayEvent(type=EventType.USER_MESSAGE, text="Yo"),
        ]
        frames = generate_frames(events)

        # The second user turn starts typing at USER_FRAME_MS (80ms).
        # Find the first 80ms frame after the assistant pause.
        # Frame sequence: 1 user typing + 1 pause + 18 spinner + 1 asst typing + 1 pause = 22
        # Frame 22 should be the first typing frame for "Yo"
        assert frames[22][1] == 80

    def test_final_frame_held_longer(self):
        """The last frame has a longer duration for viewing."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hello"),
        ]
        frames = generate_frames(events)
        _, last_ms = frames[-1]
        assert last_ms >= 1000  # held for at least 1 second

    def test_long_text_wraps(self):
        """Long text doesn't crash — it wraps within terminal width."""
        long_text = "This is a very long message that should wrap. " * 20
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text=long_text),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text=long_text),
        ]
        frames = generate_frames(events)
        assert len(frames) > 0

    def test_long_user_input_wraps_during_typing(self):
        """User input that exceeds terminal width wraps onto multiple lines while typing."""
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme(cols=40)  # narrow terminal to force wrapping
        long_input = "This is a user message that is definitely longer than forty columns and should wrap"
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text=long_input),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="OK"),
        ]
        frames = generate_frames(events, theme=theme)

        # All frames must be the same size (input area growing doesn't change image dims)
        sizes = {img.size for img, _ in frames}
        assert len(sizes) == 1, f"Frame sizes varied: {sizes}"

        # Should have more typing frames than a short message would
        short_events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="OK"),
        ]
        short_frames = generate_frames(short_events, theme=theme)
        assert len(frames) > len(short_frames)

    def test_long_user_input_produces_more_typing_frames(self):
        """Longer user text produces proportionally more typing frames."""
        short_text = "Hello"
        long_text = "x" * 200  # well beyond 80 cols

        short_frames = generate_frames(
            [
                ReplayEvent(type=EventType.USER_MESSAGE, text=short_text),
            ]
        )
        long_frames = generate_frames(
            [
                ReplayEvent(type=EventType.USER_MESSAGE, text=long_text),
            ]
        )

        # Long text should produce substantially more frames
        assert len(long_frames) > len(short_frames) * 3

    def test_codex_spinner_differs_from_claude(self):
        """Codex sessions use the bullet Working spinner, not the star spinner."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hello"),
        ]
        claude_frames = generate_frames(events, transcript_source="claude")
        codex_frames = generate_frames(events, transcript_source="codex")

        # Both produce frames
        assert len(claude_frames) > 0
        assert len(codex_frames) > 0
        # Frame content should differ (different spinner style)
        # Compare a spinner frame (around frame index after typing)
        # They should have different pixel content due to different spinner chars/colors
        claude_mid = claude_frames[len(claude_frames) // 3][0]
        codex_mid = codex_frames[len(codex_frames) // 3][0]
        assert claude_mid.tobytes() != codex_mid.tobytes()

    def test_all_frames_same_dimensions(self):
        """Every frame in the sequence has identical dimensions."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hello"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="World " * 50),
        ]
        frames = generate_frames(events)
        sizes = {img.size for img, _ in frames}
        assert len(sizes) == 1, f"Frames have different sizes: {sizes}"

    def test_empty_prompt_line_keeps_highlight_when_idle(self):
        """The bottom prompt remains highlighted even when no user text is present."""
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme(
            rows=6, cols=40, font_size=16, padding=20, padding_bottom=28
        )
        frames = generate_frames(
            [ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hello")],
            theme=theme,
        )

        frame = frames[-1][0]
        selection_rgb = theme.hex_to_rgb(theme.selection_color)
        bottom_band_rows = [
            y
            for y in range(frame.height)
            if y > frame.height - 40
            and frame.getpixel((frame.width // 2, y)) == selection_rgb
        ]

        assert bottom_band_rows, "Idle prompt area should still show the highlight band"

    def test_second_turn_typing_does_not_shift_existing_transcript_rows(self):
        """Existing lines stay put when the next user turn starts typing."""
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()
        frames = generate_frames(
            [
                ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
                ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hello"),
                ReplayEvent(type=EventType.USER_MESSAGE, text="Yo"),
            ],
            theme=theme,
        )

        # Frame 21 is the pause after the assistant response (footer shows "done").
        # Frame 22 is the first typing frame for the second user turn.
        separator_pause = frames[21][0]
        first_typing = frames[22][0]
        foreground_rgb = theme.hex_to_rgb(theme.foreground)

        before_clusters = self._color_row_clusters(separator_pause, foreground_rgb)
        after_clusters = self._color_row_clusters(first_typing, foreground_rgb)

        assert before_clusters[0] == after_clusters[0]

    def test_assistant_response_appears_after_transcript(self):
        """Transcript doesn't shift between last thinking frame and first assistant frame.

        With the footer-based spinner, the spinner is in the footer (bottom)
        while assistant text appears in the transient zone (above footer).
        The user message highlight band should stay at the same pixel position.
        """
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()

        frames = generate_frames(
            [
                ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
                ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hello"),
            ],
            theme=theme,
        )

        last_thinking = frames[19][0]
        first_assistant = frames[20][0]
        selection_rgb = theme.hex_to_rgb(theme.selection_color)

        # The user message highlight band should be at the same position
        thinking_clusters = self._color_row_clusters(last_thinking, selection_rgb)
        assistant_clusters = self._color_row_clusters(first_assistant, selection_rgb)

        # First selection cluster is the user message highlight — same in both
        assert thinking_clusters[0] == assistant_clusters[0]

    def test_progress_callback_reports_turns(self):
        """Progress callback fires for each turn with correct turn number."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hello"),
            ReplayEvent(type=EventType.USER_MESSAGE, text="Bye"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="See ya"),
        ]
        reported = []
        generate_frames(
            events, on_turn=lambda turn, total: reported.append((turn, total))
        )
        assert reported == [(1, 2), (2, 2)]

    def test_progress_callback_single_turn(self):
        """Progress callback works with a single turn."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hello"),
        ]
        reported = []
        generate_frames(
            events, on_turn=lambda turn, total: reported.append((turn, total))
        )
        assert reported == [(1, 1)]

    def test_footer_shows_churned_with_timestamps(self):
        """Footer transitions to 'done' with duration when timestamps are present."""
        from agent_log_gif.theme import TerminalTheme

        theme = TerminalTheme()
        events = [
            ReplayEvent(
                type=EventType.USER_MESSAGE,
                text="Hi",
                timestamp="2024-01-01T00:00:00",
            ),
            ReplayEvent(
                type=EventType.ASSISTANT_MESSAGE,
                text="Hello",
                timestamp="2024-01-01T00:00:10",
            ),
        ]
        # Just verify it doesn't crash and produces frames
        frames = generate_frames(events, theme=theme)
        assert len(frames) > 0


class TestElideWrappedLines:
    def test_short_text_unchanged(self):
        lines = ["line 1", "line 2", "line 3"]
        assert _elide_wrapped_lines(lines, 10) == lines

    def test_exact_limit_unchanged(self):
        lines = [f"line {i}" for i in range(12)]
        assert _elide_wrapped_lines(lines, 12) == lines

    def test_over_limit_elides_with_head_and_tail(self):
        lines = [f"line {i}" for i in range(20)]
        result = _elide_wrapped_lines(lines, 12)
        assert len(result) == 12
        # First 6 lines preserved
        assert result[:6] == lines[:6]
        # Ellipsis line in the middle
        assert "\u2026" in result[6]
        assert "9 more lines" in result[6]
        # Last 5 lines preserved
        assert result[7:] == lines[15:]

    def test_large_message_drastically_reduced(self):
        """Simulates a 19K char pasted log — should cap at max_lines."""
        lines = [f"log output line {i}" for i in range(200)]
        result = _elide_wrapped_lines(lines, 12)
        assert len(result) == 12

    def test_long_user_message_produces_fewer_frames(self):
        """A 5000-char user message should produce far fewer frames with elision."""
        long_text = "error: " + "x" * 5000
        long_frames = generate_frames(
            [ReplayEvent(type=EventType.USER_MESSAGE, text=long_text)]
        )
        # Without elision: 5000/3 ≈ 1667 typing frames.
        # With elision to 12 lines: ~312 typing frames + spinner.
        # Should be well under 500 total.
        assert len(long_frames) < 500
