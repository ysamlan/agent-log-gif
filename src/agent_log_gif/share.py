"""Share URL encoding/decoding for agent-log-gif.

Encodes replay events and rendering options into a compact URL fragment
that can be decoded by the web viewer without any server.

URL format: https://ysamlan.github.io/agent-log-gif/#v1,<options>,<compressed_events>
"""

from __future__ import annotations

import base64
import json
import zlib

from agent_log_gif.timeline import EventType, ReplayEvent

SHARE_BASE_URL = "https://ysamlan.github.io/agent-log-gif/"
URL_MAX_CHARS = 8000

EVENT_TYPE_TO_CODE: dict[EventType, str] = {
    EventType.USER_MESSAGE: "u",
    EventType.ASSISTANT_MESSAGE: "a",
    EventType.THINKING: "k",
    EventType.TOOL_CALL: "tc",
    EventType.TOOL_RESULT: "tr",
    EventType.INTERRUPTED: "i",
}

CODE_TO_EVENT_TYPE: dict[str, EventType] = {v: k for k, v in EVENT_TYPE_TO_CODE.items()}

# Option short keys and their default values
_OPTION_KEYS: dict[str, str] = {
    "chrome": "c",
    "speed": "s",
    "color_scheme": "cs",
    "loop": "l",
    "transcript_source": "src",
}

_SHORT_TO_LONG: dict[str, str] = {v: k for k, v in _OPTION_KEYS.items()}

_DEFAULTS: dict[str, object] = {
    "chrome": "mac",
    "speed": 1.0,
    "color_scheme": None,
    "loop": True,
    "transcript_source": "claude",
}

# Truncation limits per event type
_TRUNCATION_LIMITS: dict[EventType, int] = {
    EventType.USER_MESSAGE: 500,
    EventType.ASSISTANT_MESSAGE: 800,
    EventType.THINKING: 120,
    EventType.TOOL_RESULT: 40,
}


def _truncate_for_share(events: list[ReplayEvent]) -> list[ReplayEvent]:
    """Truncate event text for sharing."""
    result = []
    for event in events:
        limit = _TRUNCATION_LIMITS.get(event.type)
        if limit and len(event.text) > limit:
            truncated = event.text[: limit - 3] + "..."
            result.append(ReplayEvent(type=event.type, text=truncated))
        else:
            result.append(event)
    return result


def _encode_options(options: dict) -> str:
    """Serialize non-default options to key=val;key=val format."""
    parts = []
    for long_key, short_key in _OPTION_KEYS.items():
        if long_key not in options:
            continue
        val = options[long_key]
        default = _DEFAULTS.get(long_key)
        if val == default:
            continue
        # Special encoding for booleans
        if isinstance(val, bool):
            parts.append(f"{short_key}={'1' if val else '0'}")
        elif val is not None:
            parts.append(f"{short_key}={val}")
    return ";".join(parts)


def _decode_options(token: str) -> dict:
    """Parse options string back into a dict with long keys."""
    if not token:
        return {}
    result = {}
    for part in token.split(";"):
        if "=" not in part:
            continue
        short_key, val = part.split("=", 1)
        long_key = _SHORT_TO_LONG.get(short_key)
        if long_key is None:
            continue
        # Type coercion based on known defaults
        default = _DEFAULTS.get(long_key)
        if isinstance(default, bool) or long_key == "loop":
            result[long_key] = val != "0"
        elif isinstance(default, float) or long_key == "speed":
            result[long_key] = float(val)
        elif isinstance(default, int):
            result[long_key] = int(val)
        else:
            result[long_key] = val
    return result


def encode_share_url(
    events: list[ReplayEvent],
    transcript_source: str = "claude",
    base_url: str = SHARE_BASE_URL,
    max_chars: int = URL_MAX_CHARS,
    **options,
) -> str | None:
    """Encode events + options into a share URL. Returns None if too large."""
    # 1. Truncate events
    truncated = _truncate_for_share(events)

    # 2. Convert to [[type_code, text], ...]
    data = [[EVENT_TYPE_TO_CODE[e.type], e.text] for e in truncated]

    # 3. Compact JSON
    json_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")

    # 4. Compress
    compressed = zlib.compress(json_bytes, level=9)

    # 5. Base64url encode
    encoded = base64.urlsafe_b64encode(compressed).rstrip(b"=").decode("ascii")

    # 6. Build options string
    all_options = dict(options)
    if transcript_source != _DEFAULTS["transcript_source"]:
        all_options["transcript_source"] = transcript_source
    options_str = _encode_options(all_options)

    # 7. Assemble URL
    url = f"{base_url}#v1,{options_str},{encoded}"

    if len(url) > max_chars:
        return None
    return url


def decode_share_fragment(fragment: str) -> tuple[list[ReplayEvent], dict]:
    """Decode URL fragment (after #) into (events, options_dict)."""
    # 1. Split on first two commas
    parts = fragment.split(",", 2)
    if len(parts) != 3:
        raise ValueError(
            f"Invalid share URL fragment: expected 3 parts, got {len(parts)}"
        )

    version, options_str, data_str = parts

    # 2. Validate version
    if version != "v1":
        raise ValueError(f"Unsupported share URL version: {version!r}")

    # 3. Parse options
    options = _decode_options(options_str)

    # 4. Decode data: re-pad base64, decode, decompress, parse JSON
    padding = 4 - (len(data_str) % 4)
    if padding < 4:
        data_str += "=" * padding

    compressed = base64.urlsafe_b64decode(data_str)
    json_bytes = zlib.decompress(compressed)
    data = json.loads(json_bytes)

    # 5. Convert [type_code, text] pairs back to ReplayEvent objects
    events = []
    for item in data:
        code, text = item[0], item[1]
        event_type = CODE_TO_EVENT_TYPE[code]
        events.append(ReplayEvent(type=event_type, text=text))

    return events, options
