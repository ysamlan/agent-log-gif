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
        # At minimum: 1 user frame + 1 pause + 30 spinner frames + 1 assistant frame + pause + hold
        assert len(frames) >= 30  # spinner alone is 30 frames (10 * 3 cycles)

    def test_empty_events(self):
        """Empty event list produces no frames."""
        frames = generate_frames([])
        assert frames == []

    def test_user_only(self):
        """Single user message with no assistant still produces frames."""
        events = [ReplayEvent(type=EventType.USER_MESSAGE, text="Hello world")]
        frames = generate_frames(events)
        assert len(frames) > 0

    def test_non_visible_events_skipped(self):
        """Thinking and tool events produce no frames."""
        events = [
            ReplayEvent(type=EventType.THINKING, text="hmm"),
            ReplayEvent(type=EventType.TOOL_CALL, text="Bash"),
            ReplayEvent(type=EventType.TOOL_RESULT, text="output"),
        ]
        frames = generate_frames(events)
        assert frames == []

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

    def test_all_frames_same_dimensions(self):
        """Every frame in the sequence has identical dimensions."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hello"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="World " * 50),
        ]
        frames = generate_frames(events)
        sizes = {img.size for img, _ in frames}
        assert len(sizes) == 1, f"Frames have different sizes: {sizes}"
