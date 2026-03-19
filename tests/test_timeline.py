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
