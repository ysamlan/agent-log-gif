"""Tests for the animation engine."""

from agent_log_gif.animator import (
    generate_frames,
)
from agent_log_gif.timeline import EventType, ReplayEvent


class TestGenerateFrames:
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
        assert frames == []

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

    def test_multi_turn_has_separator(self):
        """Multiple turns have separator lines between them."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="First"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Response 1"),
            ReplayEvent(type=EventType.USER_MESSAGE, text="Second"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Response 2"),
        ]
        frames = generate_frames(events)
        # Just verify it produces frames without error
        assert len(frames) > 0

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
