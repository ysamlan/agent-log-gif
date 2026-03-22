"""Tests for the replay timeline model."""

from pathlib import Path

from agent_log_gif.parsers import parse_session_file
from agent_log_gif.timeline import (
    EventType,
    ReplayEvent,
    loglines_to_timeline,
    visible_events,
)


class TestLoglinesToTimeline:
    """Test converting parsed loglines to replay events."""

    def test_claude_jsonl_produces_events(self):
        """Claude JSONL session produces user + assistant events."""
        fixture = Path(__file__).parent / "sample_session.jsonl"
        data = parse_session_file(fixture)
        events = loglines_to_timeline(data["loglines"])

        assert len(events) > 0
        types = {e.type for e in events}
        assert EventType.USER_MESSAGE in types
        assert EventType.ASSISTANT_MESSAGE in types

    def test_codex_jsonl_produces_events(self):
        """Codex JSONL session produces user + assistant + tool events."""
        fixture = Path(__file__).parent / "sample_codex_session.jsonl"
        data = parse_session_file(fixture)
        events = loglines_to_timeline(data["loglines"])

        assert len(events) > 0
        types = {e.type for e in events}
        assert EventType.USER_MESSAGE in types
        assert EventType.ASSISTANT_MESSAGE in types
        assert EventType.TOOL_CALL in types
        assert EventType.TOOL_RESULT in types

    def test_claude_json_produces_events(self):
        """Claude JSON session produces events."""
        fixture = Path(__file__).parent / "sample_session.json"
        data = parse_session_file(fixture)
        events = loglines_to_timeline(data["loglines"])

        assert len(events) > 0
        types = {e.type for e in events}
        assert EventType.USER_MESSAGE in types

    def test_user_message_text_extracted(self):
        """User message text is correctly extracted."""
        loglines = [
            {
                "type": "user",
                "timestamp": "2025-01-01T00:00:00Z",
                "message": {"role": "user", "content": "Hello world"},
            }
        ]
        events = loglines_to_timeline(loglines)
        assert len(events) == 1
        assert events[0].type == EventType.USER_MESSAGE
        assert events[0].text == "Hello world"
        assert events[0].timestamp == "2025-01-01T00:00:00Z"

    def test_assistant_text_blocks_extracted(self):
        """Assistant content blocks produce assistant message events."""
        loglines = [
            {
                "type": "assistant",
                "timestamp": "2025-01-01T00:00:01Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Here is the answer."}],
                },
            }
        ]
        events = loglines_to_timeline(loglines)
        assert len(events) == 1
        assert events[0].type == EventType.ASSISTANT_MESSAGE
        assert events[0].text == "Here is the answer."

    def test_thinking_blocks_produce_thinking_events(self):
        """Thinking blocks become THINKING events."""
        loglines = [
            {
                "type": "assistant",
                "timestamp": "T",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "thinking", "thinking": "Let me consider..."}],
                },
            }
        ]
        events = loglines_to_timeline(loglines)
        assert len(events) == 1
        assert events[0].type == EventType.THINKING
        assert events[0].text == "Let me consider..."

    def test_tool_use_produces_tool_call_event(self):
        """Tool use blocks become TOOL_CALL events with tool name."""
        loglines = [
            {
                "type": "assistant",
                "timestamp": "T",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "name": "Bash", "id": "123", "input": {}}
                    ],
                },
            }
        ]
        events = loglines_to_timeline(loglines)
        assert len(events) == 1
        assert events[0].type == EventType.TOOL_CALL
        assert events[0].text == "Bash"

    def test_tool_use_preserves_multiline_command_text(self):
        """Tool summaries keep embedded newlines for multiline commands."""
        loglines = [
            {
                "type": "assistant",
                "timestamp": "T",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "id": "123",
                            "input": {
                                "command": "# Check inbox\ngog gmail count 'in:inbox'"
                            },
                        }
                    ],
                },
            }
        ]
        events = loglines_to_timeline(loglines)
        assert len(events) == 1
        assert events[0].type == EventType.TOOL_CALL
        assert events[0].text == "Bash # Check inbox\ngog gmail count 'in:inbox'"

    def test_tool_result_produces_tool_result_event(self):
        """Tool result blocks become TOOL_RESULT events."""
        loglines = [
            {
                "type": "user",
                "timestamp": "T",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "content": "Command output here"}
                    ],
                },
            }
        ]
        events = loglines_to_timeline(loglines)
        assert len(events) == 1
        assert events[0].type == EventType.TOOL_RESULT
        assert events[0].text == "Command output here"

    def test_empty_loglines(self):
        """Empty loglines produces empty events."""
        assert loglines_to_timeline([]) == []

    def test_skips_empty_text(self):
        """Entries with empty text are skipped."""
        loglines = [
            {
                "type": "user",
                "timestamp": "T",
                "message": {"role": "user", "content": "   "},
            }
        ]
        events = loglines_to_timeline(loglines)
        assert len(events) == 0

    def test_interrupt_marker_becomes_interrupted_event(self):
        """[Request interrupted by user] text becomes an INTERRUPTED event."""
        loglines = [
            {
                "type": "assistant",
                "timestamp": "T1",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "partial response"}],
                },
            },
            {
                "type": "user",
                "timestamp": "T2",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "[Request interrupted by user]"}
                    ],
                },
            },
        ]
        events = loglines_to_timeline(loglines)

        assert len(events) == 2
        assert events[0].type == EventType.ASSISTANT_MESSAGE
        assert events[1].type == EventType.INTERRUPTED
        assert "\u21b3 Interrupted" in events[1].text

    def test_interrupt_marker_not_a_user_message(self):
        """The interrupt marker must not appear as a USER_MESSAGE event."""
        loglines = [
            {
                "type": "user",
                "timestamp": "T",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "[Request interrupted by user]"}
                    ],
                },
            },
        ]
        events = loglines_to_timeline(loglines)

        assert len(events) == 1
        assert events[0].type == EventType.INTERRUPTED


class TestVisibleEvents:
    """Test filtering to visible events."""

    def test_filters_to_user_and_assistant(self):
        """Only user and assistant messages pass the filter."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.THINKING, text="Hmm"),
            ReplayEvent(type=EventType.TOOL_CALL, text="Bash"),
            ReplayEvent(type=EventType.TOOL_RESULT, text="output"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hello"),
        ]
        filtered = visible_events(events)
        assert len(filtered) == 2
        assert filtered[0].type == EventType.USER_MESSAGE
        assert filtered[1].type == EventType.ASSISTANT_MESSAGE

    def test_empty_list(self):
        """Empty input returns empty output."""
        assert visible_events([]) == []

    def test_show_tools_includes_tool_events(self):
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.TOOL_CALL, text="Bash echo"),
            ReplayEvent(type=EventType.TOOL_RESULT, text="output"),
            ReplayEvent(type=EventType.THINKING, text="Hmm"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Done"),
        ]
        filtered = visible_events(
            events, show={EventType.TOOL_CALL, EventType.TOOL_RESULT}
        )
        types = [e.type for e in filtered]
        assert EventType.TOOL_CALL in types
        assert EventType.TOOL_RESULT in types
        assert EventType.THINKING not in types

    def test_interrupted_always_visible(self):
        """INTERRUPTED events pass the default visibility filter."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="partial"),
            ReplayEvent(type=EventType.INTERRUPTED, text="\u21b3 Interrupted"),
        ]
        filtered = visible_events(events)
        assert len(filtered) == 3
        assert filtered[2].type == EventType.INTERRUPTED

    def test_show_all_includes_everything(self):
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hi"),
            ReplayEvent(type=EventType.THINKING, text="Hmm"),
            ReplayEvent(type=EventType.TOOL_CALL, text="Bash"),
            ReplayEvent(type=EventType.TOOL_RESULT, text="out"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Done"),
        ]
        filtered = visible_events(
            events,
            show={EventType.THINKING, EventType.TOOL_CALL, EventType.TOOL_RESULT},
        )
        assert len(filtered) == 5


class TestParseShowFlag:
    def test_single_token(self):
        from agent_log_gif.timeline import parse_show_flag

        result = parse_show_flag("tools")
        assert EventType.TOOL_CALL in result
        assert EventType.TOOL_RESULT in result

    def test_comma_separated(self):
        from agent_log_gif.timeline import parse_show_flag

        result = parse_show_flag("calls,thinking")
        assert EventType.TOOL_CALL in result
        assert EventType.THINKING in result
        assert EventType.TOOL_RESULT not in result

    def test_all(self):
        from agent_log_gif.timeline import parse_show_flag

        result = parse_show_flag("all")
        assert EventType.TOOL_CALL in result
        assert EventType.TOOL_RESULT in result
        assert EventType.THINKING in result

    def test_invalid_raises(self):
        import pytest

        from agent_log_gif.timeline import parse_show_flag

        with pytest.raises(ValueError, match="Unknown --show value"):
            parse_show_flag("bogus")
