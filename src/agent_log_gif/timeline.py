"""Replay timeline model: converts parsed loglines into a sequence of replay events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EventType(Enum):
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


# Events visible by default in GIF output
VISIBLE_EVENT_TYPES = {EventType.USER_MESSAGE, EventType.ASSISTANT_MESSAGE}

# Named show presets: map user-facing names to event type sets
SHOW_EXTRAS = {
    "tools": {EventType.TOOL_CALL, EventType.TOOL_RESULT},
    "calls": {EventType.TOOL_CALL},
    "thinking": {EventType.THINKING},
    "all": {EventType.THINKING, EventType.TOOL_CALL, EventType.TOOL_RESULT},
}


@dataclass(frozen=True)
class ReplayEvent:
    """A single event in a replay timeline."""

    type: EventType
    text: str
    timestamp: str = ""


def loglines_to_timeline(loglines: list[dict]) -> list[ReplayEvent]:
    """Convert normalized loglines into a flat list of ReplayEvents.

    All event types are emitted (user, assistant, thinking, tool_call, tool_result)
    so that callers can filter by visibility. User and assistant messages extract
    plain text; tool calls preserve the tool name; tool results preserve the content.
    """
    events: list[ReplayEvent] = []

    for entry in loglines:
        entry_type = entry.get("type")
        timestamp = entry.get("timestamp", "")
        message = entry.get("message", {})
        content = message.get("content", "")

        if entry_type == "user":
            # User entries can be plain text prompts or tool result arrays
            if isinstance(content, str):
                text = content.strip()
                if text:
                    events.append(
                        ReplayEvent(
                            type=EventType.USER_MESSAGE,
                            text=text,
                            timestamp=timestamp,
                        )
                    )
            elif isinstance(content, list):
                # Could be tool_result blocks or text blocks
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type", "")
                    if block_type == "tool_result":
                        result_text = block.get("content", "")
                        if isinstance(result_text, str) and result_text.strip():
                            events.append(
                                ReplayEvent(
                                    type=EventType.TOOL_RESULT,
                                    text=result_text.strip(),
                                    timestamp=timestamp,
                                )
                            )
                    elif block_type == "text":
                        text = block.get("text", "").strip()
                        if text:
                            events.append(
                                ReplayEvent(
                                    type=EventType.USER_MESSAGE,
                                    text=text,
                                    timestamp=timestamp,
                                )
                            )

        elif entry_type == "assistant":
            if isinstance(content, str):
                text = content.strip()
                if text:
                    events.append(
                        ReplayEvent(
                            type=EventType.ASSISTANT_MESSAGE,
                            text=text,
                            timestamp=timestamp,
                        )
                    )
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type", "")
                    if block_type == "text":
                        text = block.get("text", "").strip()
                        if text:
                            events.append(
                                ReplayEvent(
                                    type=EventType.ASSISTANT_MESSAGE,
                                    text=text,
                                    timestamp=timestamp,
                                )
                            )
                    elif block_type == "thinking":
                        thinking = block.get("thinking", "").strip()
                        if thinking:
                            events.append(
                                ReplayEvent(
                                    type=EventType.THINKING,
                                    text=thinking,
                                    timestamp=timestamp,
                                )
                            )
                    elif block_type == "tool_use":
                        tool_name = block.get("name", "Unknown")
                        tool_summary = _tool_call_summary(
                            tool_name, block.get("input", {})
                        )
                        events.append(
                            ReplayEvent(
                                type=EventType.TOOL_CALL,
                                text=tool_summary,
                                timestamp=timestamp,
                            )
                        )

    return events


def visible_events(
    events: list[ReplayEvent], show: set[EventType] | None = None
) -> list[ReplayEvent]:
    """Filter to events visible in GIF output.

    Always includes user and assistant messages. Pass extra event types
    via ``show`` to include tool calls, tool results, and/or thinking.
    """
    visible = VISIBLE_EVENT_TYPES | (show or set())
    return [e for e in events if e.type in visible]


def parse_show_flag(value: str) -> set[EventType]:
    """Parse a comma-separated ``--show`` value into event types.

    Accepted tokens: tools, calls, thinking, all.
    """
    result: set[EventType] = set()
    for token in value.split(","):
        token = token.strip().lower()
        if token in SHOW_EXTRAS:
            result |= SHOW_EXTRAS[token]
        else:
            valid = ", ".join(sorted(SHOW_EXTRAS))
            raise ValueError(f"Unknown --show value: {token!r}. Choose from: {valid}")
    return result


def _tool_call_summary(name: str, inputs: dict) -> str:
    """Build a short one-line summary for a tool call.

    Examples:
        Write /project/hello.py
        Bash git add . && git commit ...
        Read /src/main.py
        exec_command pytest -q
    """
    # Pick the most informative input field
    hint = ""
    if "file_path" in inputs:
        hint = inputs["file_path"]
    elif "command" in inputs:
        hint = inputs["command"]
    elif "cmd" in inputs:
        hint = inputs["cmd"]
    elif "pattern" in inputs:
        hint = inputs["pattern"]
    elif "path" in inputs:
        hint = inputs["path"]
    elif isinstance(inputs, dict) and inputs:
        # Fallback: grab the first short string value
        for v in inputs.values():
            if isinstance(v, str) and len(v) < 200:
                hint = v
                break

    if hint:
        from agent_log_gif.parsers import truncate_text

        return f"{name} {truncate_text(hint, 60)}"
    return name
