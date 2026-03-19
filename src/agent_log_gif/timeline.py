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
                        events.append(
                            ReplayEvent(
                                type=EventType.TOOL_CALL,
                                text=tool_name,
                                timestamp=timestamp,
                            )
                        )

    return events


def visible_events(events: list[ReplayEvent]) -> list[ReplayEvent]:
    """Filter to only events visible in default GIF output."""
    return [e for e in events if e.type in VISIBLE_EVENT_TYPES]
