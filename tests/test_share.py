"""Tests for share URL encoding/decoding."""

from pathlib import Path

import pytest

from agent_log_gif.parsers import parse_session_file
from agent_log_gif.share import (
    CODE_TO_EVENT_TYPE,
    EVENT_TYPE_TO_CODE,
    SHARE_BASE_URL,
    _decode_options,
    _encode_options,
    _truncate_for_share,
    decode_share_fragment,
    encode_share_url,
)
from agent_log_gif.timeline import EventType, ReplayEvent, loglines_to_timeline


class TestEventTypeMappings:
    def test_all_event_types_have_codes(self):
        for et in EventType:
            assert et in EVENT_TYPE_TO_CODE

    def test_round_trip_codes(self):
        for et, code in EVENT_TYPE_TO_CODE.items():
            assert CODE_TO_EVENT_TYPE[code] is et


class TestEncodeOptions:
    def test_empty_when_all_defaults(self):
        assert _encode_options({}) == ""

    def test_non_default_options_encoded(self):
        result = _encode_options({"chrome": "windows", "speed": 2.0})
        assert "c=windows" in result
        assert "s=2.0" in result
        assert ";" in result

    def test_loop_false_encoded(self):
        result = _encode_options({"loop": False})
        assert "l=0" in result

    def test_loop_true_omitted(self):
        result = _encode_options({"loop": True})
        assert "l=" not in result

    def test_defaults_omitted(self):
        # Default values should not appear
        result = _encode_options({"chrome": "mac", "speed": 1.0, "loop": True})
        assert result == ""


class TestDecodeOptions:
    def test_empty_string(self):
        assert _decode_options("") == {}

    def test_round_trip(self):
        opts = {"chrome": "windows", "speed": 2.0, "loop": False}
        encoded = _encode_options(opts)
        decoded = _decode_options(encoded)
        assert decoded["chrome"] == "windows"
        assert decoded["speed"] == 2.0
        assert decoded["loop"] is False

    def test_multiple_options(self):
        decoded = _decode_options("c=linux;s=1.5;l=0")
        assert decoded["chrome"] == "linux"
        assert decoded["speed"] == 1.5
        assert decoded["loop"] is False


class TestTruncateForShare:
    def test_user_message_truncated(self):
        events = [ReplayEvent(type=EventType.USER_MESSAGE, text="x" * 1000)]
        result = _truncate_for_share(events)
        assert len(result[0].text) <= 500

    def test_assistant_message_truncated(self):
        events = [ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="y" * 1500)]
        result = _truncate_for_share(events)
        assert len(result[0].text) <= 800

    def test_thinking_truncated(self):
        events = [ReplayEvent(type=EventType.THINKING, text="z" * 500)]
        result = _truncate_for_share(events)
        assert len(result[0].text) <= 120

    def test_tool_result_truncated(self):
        events = [ReplayEvent(type=EventType.TOOL_RESULT, text="r" * 200)]
        result = _truncate_for_share(events)
        assert len(result[0].text) <= 40

    def test_short_text_unchanged(self):
        events = [ReplayEvent(type=EventType.USER_MESSAGE, text="hello")]
        result = _truncate_for_share(events)
        assert result[0].text == "hello"


class TestEncodeDecodeRoundTrip:
    def test_basic_round_trip(self):
        events = [
            ReplayEvent(
                type=EventType.USER_MESSAGE, text="Create a hello world function"
            ),
            ReplayEvent(
                type=EventType.ASSISTANT_MESSAGE, text="I'll create that for you."
            ),
            ReplayEvent(type=EventType.TOOL_CALL, text="Write /project/hello.py"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Done!"),
        ]
        url = encode_share_url(events)
        assert url is not None
        assert url.startswith(SHARE_BASE_URL + "#v1,")

        fragment = url.split("#", 1)[1]
        decoded_events, decoded_opts = decode_share_fragment(fragment)

        assert len(decoded_events) == len(events)
        for orig, dec in zip(events, decoded_events):
            assert orig.type == dec.type
            assert orig.text == dec.text

    def test_round_trip_with_options(self):
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hello"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hi there"),
        ]
        url = encode_share_url(events, chrome="windows", speed=2.0, loop=False)
        assert url is not None

        fragment = url.split("#", 1)[1]
        decoded_events, decoded_opts = decode_share_fragment(fragment)

        assert decoded_opts["chrome"] == "windows"
        assert decoded_opts["speed"] == 2.0
        assert decoded_opts["loop"] is False
        assert len(decoded_events) == 2

    def test_all_event_types_round_trip(self):
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Do something"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Sure"),
            ReplayEvent(type=EventType.THINKING, text="Let me think..."),
            ReplayEvent(type=EventType.TOOL_CALL, text="Read /file.py"),
            ReplayEvent(type=EventType.TOOL_RESULT, text="file contents"),
            ReplayEvent(type=EventType.INTERRUPTED, text="Interrupted"),
        ]
        url = encode_share_url(events)
        assert url is not None

        fragment = url.split("#", 1)[1]
        decoded_events, _ = decode_share_fragment(fragment)

        assert len(decoded_events) == len(events)
        for orig, dec in zip(events, decoded_events):
            assert orig.type == dec.type

    def test_empty_options_produce_empty_string_between_commas(self):
        events = [ReplayEvent(type=EventType.USER_MESSAGE, text="Hi")]
        url = encode_share_url(events)
        assert url is not None
        fragment = url.split("#", 1)[1]
        parts = fragment.split(",", 2)
        assert parts[0] == "v1"
        assert parts[1] == ""  # empty options

    def test_transcript_source_in_options(self):
        events = [ReplayEvent(type=EventType.USER_MESSAGE, text="Hi")]
        url = encode_share_url(events, transcript_source="codex")
        assert url is not None
        fragment = url.split("#", 1)[1]
        _, opts = decode_share_fragment(fragment)
        assert opts["transcript_source"] == "codex"


class TestShareUrlDoesNotEncodeRedundantOptions:
    """Share URLs should NOT encode max_turns or show since events are pre-selected."""

    def test_max_turns_not_in_share_url(self):
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hello"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hi"),
        ]
        url = encode_share_url(events, max_turns=5)
        assert url is not None
        fragment = url.split("#", 1)[1]
        _, opts = decode_share_fragment(fragment)
        assert "max_turns" not in opts

    def test_show_not_in_share_url(self):
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hello"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hi"),
        ]
        url = encode_share_url(events, show="tools")
        assert url is not None
        fragment = url.split("#", 1)[1]
        _, opts = decode_share_fragment(fragment)
        assert "show" not in opts

    def test_tuple_turns_not_encoded(self):
        """Regression: tuple turns like (1, 3) must not corrupt the URL."""
        events = [
            ReplayEvent(type=EventType.USER_MESSAGE, text="Hello"),
            ReplayEvent(type=EventType.ASSISTANT_MESSAGE, text="Hi"),
        ]
        # Even if someone passes a tuple, it should be silently ignored
        url = encode_share_url(events, max_turns=(1, 3))
        assert url is not None
        fragment = url.split("#", 1)[1]
        decoded_events, opts = decode_share_fragment(fragment)
        assert "max_turns" not in opts
        assert len(decoded_events) == 2


class TestOversizeUrl:
    def test_returns_none_when_too_large(self):
        # Use varied text that doesn't compress well
        import hashlib

        events = [
            ReplayEvent(
                type=EventType.USER_MESSAGE,
                text=hashlib.sha256(str(i).encode()).hexdigest() * 10,
            )
            for i in range(200)
        ]
        result = encode_share_url(events, max_chars=500)
        assert result is None


class TestVersionValidation:
    def test_unknown_version_raises(self):
        with pytest.raises(ValueError, match="Unsupported share URL version"):
            decode_share_fragment("v2,,abc123")

    def test_v1_accepted(self):
        events = [ReplayEvent(type=EventType.USER_MESSAGE, text="test")]
        url = encode_share_url(events)
        fragment = url.split("#", 1)[1]
        # Should not raise
        decode_share_fragment(fragment)


class TestFixtureRoundTrip:
    def test_sample_session_round_trip(self):
        fixture = Path(__file__).parent / "sample_session.jsonl"
        data = parse_session_file(fixture)
        loglines = data.get("loglines", [])
        events = loglines_to_timeline(loglines)

        url = encode_share_url(
            events, transcript_source=data.get("transcript_source", "claude")
        )
        assert url is not None, "Sample session should fit in a share URL"

        fragment = url.split("#", 1)[1]
        decoded_events, decoded_opts = decode_share_fragment(fragment)

        # Events should round-trip (texts may be truncated)
        assert len(decoded_events) == len(events)
        for orig, dec in zip(events, decoded_events):
            assert orig.type == dec.type
            # Decoded text should be a prefix of original (possibly truncated)
            assert (
                orig.text.startswith(dec.text.rstrip("...").rstrip("."))
                or dec.text == orig.text
            )
