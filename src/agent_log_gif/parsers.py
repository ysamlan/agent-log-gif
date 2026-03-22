"""Session file parsing for Claude Code and Codex formats.

Handles JSON, JSONL (Claude Code), and Codex JSONL session files,
normalizing them into a standard loglines format.
"""

import json
import re
from pathlib import Path


def extract_text_from_content(content):
    """Extract plain text from message content.

    Handles both string content (older format) and array content (newer format).

    Args:
        content: Either a string or a list of content blocks like
                 [{"type": "text", "text": "..."}, {"type": "image", ...}]

    Returns:
        The extracted text as a string, or empty string if no text found.
    """
    if isinstance(content, str):
        return content.strip()
    elif isinstance(content, list):
        # Extract text from content blocks of type "text"
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    texts.append(text)
        return " ".join(texts).strip()
    return ""


def truncate_text(text, max_length):
    """Truncate text to max_length with ellipsis."""
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def read_first_jsonl_object(filepath):
    """Return the first valid JSON object from a JSONL file, or None."""
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def is_codex_jsonl(first_obj):
    """Detect Codex session JSONL based on its event envelope."""
    if not isinstance(first_obj, dict):
        return False
    return (
        first_obj.get("type")
        in {
            "session_meta",
            "event_msg",
            "response_item",
        }
        and "payload" in first_obj
    )


def get_transcript_label(transcript_source):
    """Return the display label for a transcript source."""
    if transcript_source == "codex":
        return "Codex transcript"
    return "Claude Code transcript"


def parse_session_file(filepath):
    """Parse a session file and return normalized data.

    Supports both JSON and JSONL formats.
    Returns a dict with 'loglines' key containing the normalized entries.
    """
    filepath = Path(filepath)

    if filepath.suffix == ".jsonl":
        first_obj = read_first_jsonl_object(filepath)
        if is_codex_jsonl(first_obj):
            return _parse_codex_jsonl_file(filepath)
        return _parse_jsonl_file(filepath)
    else:
        # Standard JSON format
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("transcript_source", "claude")
        return data


def _parse_jsonl_file(filepath):
    """Parse JSONL file and convert to standard format."""
    loglines = []

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                entry_type = obj.get("type")

                # Skip non-message entries
                if entry_type not in ("user", "assistant"):
                    continue

                # Skip internal meta-messages (local-command-caveat, skill
                # base-directory instructions, etc.) — never shown in the UI.
                if obj.get("isMeta"):
                    continue

                # Rewrite <command-name> XML → clean slash command
                message = obj.get("message", {})
                msg_content = message.get("content", "")
                if entry_type == "user" and isinstance(msg_content, str):
                    cmd = _extract_slash_command(msg_content)
                    if cmd is not None:
                        message = {
                            "role": "user",
                            "content": cmd,
                        }

                # Convert to standard format
                entry = {
                    "type": entry_type,
                    "timestamp": obj.get("timestamp", ""),
                    "message": message,
                }

                # Preserve isCompactSummary if present
                if obj.get("isCompactSummary"):
                    entry["isCompactSummary"] = True

                loglines.append(entry)
            except json.JSONDecodeError:
                continue

    return {"loglines": loglines, "transcript_source": "claude"}


_COMMAND_NAME_RE = re.compile(r"<command-name>\s*(/\S+)\s*</command-name>")
_COMMAND_ARGS_RE = re.compile(r"<command-args>\s*(.*?)\s*</command-args>", re.DOTALL)


def _extract_slash_command(text):
    """Convert Claude Code ``<command-name>`` XML into a clean slash command.

    Returns the cleaned string (e.g. ``/simplify everything``) when the text
    matches the XML pattern, or *None* if it doesn't match.
    """
    m = _COMMAND_NAME_RE.search(text)
    if not m:
        return None
    name = m.group(1)

    args_m = _COMMAND_ARGS_RE.search(text)
    args = args_m.group(1).strip() if args_m else ""

    return f"{name} {args}".strip() if args else name


def _is_codex_setup_text(text):
    """Detect setup/instruction content that should not appear as a prompt."""
    if not text:
        return True

    stripped = text.strip()
    setup_prefixes = (
        "# AGENTS.md instructions",
        "<environment_context>",
        "<INSTRUCTIONS>",
    )
    return stripped.startswith(setup_prefixes)


def _is_codex_transport_text(text):
    """Detect transport/meta user content that should not become a prompt."""
    if not text:
        return True

    return text.strip().startswith("<turn_aborted>")


def _parse_codex_tool_arguments(arguments):
    """Parse Codex tool arguments into a dict for tool rendering."""
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {"arguments": arguments}
        if isinstance(parsed, dict):
            return parsed
        return {"arguments": parsed}
    if arguments is None:
        return {}
    return {"arguments": arguments}


def _extract_codex_message_texts(content, item_type):
    """Extract text snippets from Codex message content items."""
    texts = []
    if not isinstance(content, list):
        return texts

    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != item_type:
            continue
        text = item.get("text", "")
        if text:
            texts.append(text)
    return texts


def _extract_codex_reasoning_summary(summary):
    """Extract plain-text reasoning summary from Codex reasoning payloads."""
    if isinstance(summary, str):
        return summary.strip()
    if not isinstance(summary, list):
        return ""

    parts = []
    for item in summary:
        if isinstance(item, str):
            if item.strip():
                parts.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("text", "")
        if text:
            parts.append(text.strip())

    return "\n\n".join(part for part in parts if part)


def _get_codex_jsonl_summary(filepath, max_length=200):
    """Extract summary from a Codex session JSONL file.

    Streams through the file and returns as soon as the first real user
    prompt is found, avoiding a full parse.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("type") != "response_item":
                continue
            payload = obj.get("payload", {})
            if not isinstance(payload, dict):
                continue
            if payload.get("type") != "message" or payload.get("role") != "user":
                continue

            texts = _extract_codex_message_texts(
                payload.get("content", []), "input_text"
            )
            if not texts:
                continue
            if all(_is_codex_setup_text(t) for t in texts):
                continue
            if all(_is_codex_transport_text(t) for t in texts):
                continue

            return truncate_text("\n\n".join(texts).strip(), max_length)

    return "(no summary)"


def _parse_codex_jsonl_file(filepath):
    """Parse Codex JSONL session events into the standard loglines format."""
    loglines = []

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("type") != "response_item":
                continue

            payload = obj.get("payload", {})
            if not isinstance(payload, dict):
                continue

            timestamp = obj.get("timestamp", "")
            payload_type = payload.get("type")

            if payload_type == "message":
                role = payload.get("role")
                content = payload.get("content", [])

                if role == "user":
                    texts = _extract_codex_message_texts(content, "input_text")
                    if not texts:
                        continue

                    if all(_is_codex_setup_text(text) for text in texts):
                        continue
                    if all(_is_codex_transport_text(text) for text in texts):
                        continue

                    loglines.append(
                        {
                            "type": "user",
                            "timestamp": timestamp,
                            "message": {
                                "role": "user",
                                "content": "\n\n".join(texts).strip(),
                            },
                        }
                    )
                elif role == "assistant":
                    texts = _extract_codex_message_texts(content, "output_text")
                    if not texts:
                        continue

                    blocks = [{"type": "text", "text": text} for text in texts]
                    loglines.append(
                        {
                            "type": "assistant",
                            "timestamp": timestamp,
                            "message": {
                                "role": "assistant",
                                "content": blocks,
                            },
                        }
                    )
            elif payload_type == "function_call":
                loglines.append(
                    {
                        "type": "assistant",
                        "timestamp": timestamp,
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": payload.get("name", "Unknown tool"),
                                    "id": payload.get("call_id", ""),
                                    "input": _parse_codex_tool_arguments(
                                        payload.get("arguments")
                                    ),
                                }
                            ],
                        },
                    }
                )
            elif payload_type == "function_call_output":
                loglines.append(
                    {
                        "type": "user",
                        "timestamp": timestamp,
                        "message": {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "content": payload.get("output", ""),
                                    "is_error": bool(payload.get("is_error", False)),
                                }
                            ],
                        },
                    }
                )
            elif payload_type == "reasoning":
                thinking = _extract_codex_reasoning_summary(payload.get("summary"))
                if not thinking:
                    continue

                loglines.append(
                    {
                        "type": "assistant",
                        "timestamp": timestamp,
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "thinking", "thinking": thinking}],
                        },
                    }
                )

    return {"loglines": loglines, "transcript_source": "codex"}
