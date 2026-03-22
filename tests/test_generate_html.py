"""Tests for session parsing, analysis, and CLI basics."""

import json
import tempfile
from pathlib import Path

import pytest

from agent_log_gif import (
    analyze_conversation,
    find_local_sessions,
    format_tool_stats,
    get_session_summary,
    is_tool_result_message,
    parse_session_file,
)


@pytest.fixture
def sample_session():
    """Load the sample session fixture."""
    fixture_path = Path(__file__).parent / "sample_session.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def output_dir():
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestAnalyzeConversation:
    """Tests for conversation analysis."""

    def test_counts_tools(self):
        """Test that tool usage is counted."""
        messages = [
            (
                "assistant",
                json.dumps(
                    {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "id": "1",
                                "input": {},
                            },
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "id": "2",
                                "input": {},
                            },
                            {
                                "type": "tool_use",
                                "name": "Write",
                                "id": "3",
                                "input": {},
                            },
                        ]
                    }
                ),
                "2025-01-01T00:00:00Z",
            ),
        ]
        result = analyze_conversation(messages)
        assert result["tool_counts"]["Bash"] == 2
        assert result["tool_counts"]["Write"] == 1

    def test_extracts_commits(self):
        """Test that git commits are extracted."""
        messages = [
            (
                "user",
                json.dumps(
                    {
                        "content": [
                            {
                                "type": "tool_result",
                                "content": "[main abc1234] Add new feature\n 1 file changed",
                            }
                        ]
                    }
                ),
                "2025-01-01T00:00:00Z",
            ),
        ]
        result = analyze_conversation(messages)
        assert len(result["commits"]) == 1
        assert result["commits"][0][0] == "abc1234"
        assert "Add new feature" in result["commits"][0][1]

    def test_ignores_commit_like_text_inside_code(self):
        """Test that commit-like text in quoted code does not become a commit."""
        messages = [
            (
                "user",
                json.dumps(
                    {
                        "content": [
                            {
                                "type": "tool_result",
                                "content": 'assert "[main abc1234] Add fake commit" in output',
                            }
                        ]
                    }
                ),
                "2025-01-01T00:00:00Z",
            ),
        ]
        result = analyze_conversation(messages)
        assert result["commits"] == []


class TestFormatToolStats:
    """Tests for tool stats formatting."""

    def test_formats_counts(self):
        """Test tool count formatting."""
        counts = {"Bash": 5, "Read": 3, "Write": 1}
        result = format_tool_stats(counts)
        assert "5 bash" in result
        assert "3 read" in result
        assert "1 write" in result

    def test_empty_counts(self):
        """Test empty tool counts."""
        assert format_tool_stats({}) == ""


class TestIsToolResultMessage:
    """Tests for tool result message detection."""

    def test_detects_tool_result_only(self):
        """Test detection of tool-result-only messages."""
        message = {"content": [{"type": "tool_result", "content": "result"}]}
        assert is_tool_result_message(message) is True

    def test_rejects_mixed_content(self):
        """Test rejection of mixed content messages."""
        message = {
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "tool_result", "content": "result"},
            ]
        }
        assert is_tool_result_message(message) is False

    def test_rejects_empty(self):
        """Test rejection of empty content."""
        assert is_tool_result_message({"content": []}) is False
        assert is_tool_result_message({"content": "string"}) is False


class TestParseSessionFile:
    """Tests for parse_session_file which abstracts both JSON and JSONL formats."""

    def test_parses_json_format(self):
        """Test that standard JSON format is parsed correctly."""
        fixture_path = Path(__file__).parent / "sample_session.json"
        result = parse_session_file(fixture_path)

        assert "loglines" in result
        assert len(result["loglines"]) > 0
        # Check first entry
        first = result["loglines"][0]
        assert first["type"] == "user"
        assert "timestamp" in first
        assert "message" in first

    def test_parses_jsonl_format(self):
        """Test that JSONL format is parsed and converted to standard format."""
        fixture_path = Path(__file__).parent / "sample_session.jsonl"
        result = parse_session_file(fixture_path)

        assert "loglines" in result
        assert len(result["loglines"]) > 0
        # Check structure matches JSON format
        for entry in result["loglines"]:
            assert "type" in entry
            # Skip summary entries which don't have message
            if entry["type"] in ("user", "assistant"):
                assert "timestamp" in entry
                assert "message" in entry

    def test_parses_codex_jsonl_format(self):
        """Test that Codex JSONL format is normalized to the standard format."""
        fixture_path = Path(__file__).parent / "sample_codex_session.jsonl"
        result = parse_session_file(fixture_path)

        assert "loglines" in result
        assert [entry["type"] for entry in result["loglines"]] == [
            "user",
            "assistant",
            "assistant",
            "user",
            "assistant",
        ]

        prompt = result["loglines"][0]
        assert prompt["message"]["content"] == "Build a CLI summary command"

        tool_use = result["loglines"][2]["message"]["content"][0]
        assert tool_use["type"] == "tool_use"
        assert tool_use["name"] == "exec_command"
        assert tool_use["input"] == {"cmd": "pytest -q", "workdir": "/workspace"}

        tool_result = result["loglines"][3]["message"]["content"][0]
        assert tool_result["type"] == "tool_result"
        assert "[main abc1234] Add Codex support" in tool_result["content"]

    def test_jsonl_skips_non_message_entries(self):
        """Test that summary and file-history-snapshot entries are skipped."""
        fixture_path = Path(__file__).parent / "sample_session.jsonl"
        result = parse_session_file(fixture_path)

        # None of the loglines should be summary or file-history-snapshot
        for entry in result["loglines"]:
            assert entry["type"] in ("user", "assistant")

    def test_codex_jsonl_skips_turn_aborted_prompt(self, tmp_path):
        """Test that Codex transport markers are not treated as user prompts."""
        session_file = tmp_path / "codex.jsonl"
        session_file.write_text(
            '{"timestamp":"2026-03-19T00:00:00Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"<turn_aborted>\\nThe user interrupted the previous turn.\\n</turn_aborted>"}]}}\n'
            '{"timestamp":"2026-03-19T00:00:01Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"Real prompt"}]}}\n'
            '{"timestamp":"2026-03-19T00:00:02Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"Real answer"}]}}\n',
            encoding="utf-8",
        )

        result = parse_session_file(session_file)

        # Should have entries but none should be the turn_aborted prompt
        user_messages = [e for e in result["loglines"] if e["type"] == "user"]
        for msg in user_messages:
            content = msg["message"].get("content", "")
            if isinstance(content, str):
                assert "<turn_aborted>" not in content

    def test_jsonl_skips_is_meta_entries(self, tmp_path):
        """Entries with isMeta=true (local-command-caveat, etc.) are filtered."""
        session_file = tmp_path / "meta.jsonl"
        session_file.write_text(
            '{"type":"user","timestamp":"T1","message":{"role":"user","content":"real prompt"}}\n'
            '{"type":"user","timestamp":"T2","isMeta":true,"message":{"role":"user","content":"<local-command-caveat>ignore</local-command-caveat>"}}\n'
            '{"type":"assistant","timestamp":"T3","message":{"role":"assistant","content":[{"type":"text","text":"response"}]}}\n',
            encoding="utf-8",
        )
        result = parse_session_file(session_file)

        assert len(result["loglines"]) == 2
        assert result["loglines"][0]["message"]["content"] == "real prompt"
        assert result["loglines"][1]["type"] == "assistant"

    def test_jsonl_transforms_command_name_xml(self, tmp_path):
        """<command-name> XML in user messages becomes clean slash command text."""
        session_file = tmp_path / "cmd.jsonl"
        session_file.write_text(
            '{"type":"user","timestamp":"T1","message":{"role":"user","content":"<command-name>/reload-plugins</command-name>\\n<command-message>reload-plugins</command-message>\\n<command-args></command-args>"}}\n'
            '{"type":"user","timestamp":"T2","message":{"role":"user","content":"<command-message>simplify</command-message>\\n<command-name>/simplify</command-name>\\n<command-args>everything we\\u0027ve done</command-args>"}}\n',
            encoding="utf-8",
        )
        result = parse_session_file(session_file)

        assert len(result["loglines"]) == 2
        assert result["loglines"][0]["message"]["content"] == "/reload-plugins"
        assert (
            result["loglines"][1]["message"]["content"]
            == "/simplify everything we've done"
        )


class TestGetSessionSummary:
    """Tests for get_session_summary which extracts summary from session files."""

    def test_gets_summary_from_jsonl(self):
        """Test extracting summary from JSONL file."""
        fixture_path = Path(__file__).parent / "sample_session.jsonl"
        summary = get_session_summary(fixture_path)
        assert summary == "Test session for JSONL parsing"

    def test_gets_summary_from_codex_jsonl(self):
        """Test extracting the first real user message from a Codex JSONL file."""
        fixture_path = Path(__file__).parent / "sample_codex_session.jsonl"
        summary = get_session_summary(fixture_path)
        assert summary == "Build a CLI summary command"

    def test_gets_first_user_message_if_no_summary(self, tmp_path):
        """Test falling back to first user message when no summary entry."""
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            '{"type":"user","timestamp":"2025-01-01T00:00:00Z","message":{"role":"user","content":"Hello world test"}}\n'
        )
        summary = get_session_summary(jsonl_file)
        assert summary == "Hello world test"

    def test_returns_no_summary_for_empty_file(self, tmp_path):
        """Test handling empty or invalid files."""
        jsonl_file = tmp_path / "empty.jsonl"
        jsonl_file.write_text("", encoding="utf-8")
        summary = get_session_summary(jsonl_file)
        assert summary == "(no summary)"

    def test_truncates_long_summaries(self, tmp_path):
        """Test that long summaries are truncated."""
        jsonl_file = tmp_path / "long.jsonl"
        long_text = "x" * 300
        jsonl_file.write_text(f'{{"type":"summary","summary":"{long_text}"}}\n')
        summary = get_session_summary(jsonl_file, max_length=100)
        assert len(summary) <= 100
        assert summary.endswith("...")


class TestFindLocalSessions:
    """Tests for find_local_sessions which discovers local JSONL files."""

    def test_finds_jsonl_files(self, tmp_path):
        """Test finding JSONL files in projects directory."""
        # Create mock .claude/projects structure
        projects_dir = tmp_path / ".claude" / "projects" / "test-project"
        projects_dir.mkdir(parents=True)

        # Create a session file
        session_file = projects_dir / "session-123.jsonl"
        session_file.write_text(
            '{"type":"summary","summary":"Test session"}\n'
            '{"type":"user","timestamp":"2025-01-01T00:00:00Z","message":{"role":"user","content":"Hello"}}\n'
        )

        results = find_local_sessions(tmp_path / ".claude" / "projects", limit=10)
        assert len(results) == 1
        assert results[0][0] == session_file
        assert results[0][1] == "Test session"

    def test_excludes_agent_files(self, tmp_path):
        """Test that agent- prefixed files are excluded."""
        projects_dir = tmp_path / ".claude" / "projects" / "test-project"
        projects_dir.mkdir(parents=True)

        # Create agent file (should be excluded)
        agent_file = projects_dir / "agent-123.jsonl"
        agent_file.write_text('{"type":"user","message":{"content":"test"}}\n')

        # Create regular file (should be included)
        session_file = projects_dir / "session-123.jsonl"
        session_file.write_text(
            '{"type":"summary","summary":"Real session"}\n'
            '{"type":"user","timestamp":"2025-01-01T00:00:00Z","message":{"role":"user","content":"Hello"}}\n'
        )

        results = find_local_sessions(tmp_path / ".claude" / "projects", limit=10)
        assert len(results) == 1
        assert "agent-" not in results[0][0].name

    def test_excludes_warmup_sessions(self, tmp_path):
        """Test that warmup sessions are excluded."""
        projects_dir = tmp_path / ".claude" / "projects" / "test-project"
        projects_dir.mkdir(parents=True)

        # Create warmup file (should be excluded)
        warmup_file = projects_dir / "warmup-session.jsonl"
        warmup_file.write_text('{"type":"summary","summary":"warmup"}\n')

        # Create regular file
        session_file = projects_dir / "session-123.jsonl"
        session_file.write_text(
            '{"type":"summary","summary":"Real session"}\n'
            '{"type":"user","timestamp":"2025-01-01T00:00:00Z","message":{"role":"user","content":"Hello"}}\n'
        )

        results = find_local_sessions(tmp_path / ".claude" / "projects", limit=10)
        assert len(results) == 1
        assert results[0][1] == "Real session"

    def test_sorts_by_modification_time(self, tmp_path):
        """Test that results are sorted by modification time, newest first."""
        import time

        projects_dir = tmp_path / ".claude" / "projects" / "test-project"
        projects_dir.mkdir(parents=True)

        # Create files with different mtimes
        file1 = projects_dir / "older.jsonl"
        file1.write_text(
            '{"type":"summary","summary":"Older"}\n{"type":"user","timestamp":"2025-01-01T00:00:00Z","message":{"role":"user","content":"test"}}\n'
        )

        time.sleep(0.1)  # Ensure different mtime

        file2 = projects_dir / "newer.jsonl"
        file2.write_text(
            '{"type":"summary","summary":"Newer"}\n{"type":"user","timestamp":"2025-01-01T00:00:00Z","message":{"role":"user","content":"test"}}\n'
        )

        results = find_local_sessions(tmp_path / ".claude" / "projects", limit=10)
        assert len(results) == 2
        assert results[0][1] == "Newer"  # Most recent first
        assert results[1][1] == "Older"

    def test_respects_limit(self, tmp_path):
        """Test that limit parameter is respected."""
        projects_dir = tmp_path / ".claude" / "projects" / "test-project"
        projects_dir.mkdir(parents=True)

        # Create 5 files
        for i in range(5):
            f = projects_dir / f"session-{i}.jsonl"
            f.write_text(
                f'{{"type":"summary","summary":"Session {i}"}}\n{{"type":"user","timestamp":"2025-01-01T00:00:00Z","message":{{"role":"user","content":"test"}}}}\n'
            )

        results = find_local_sessions(tmp_path / ".claude" / "projects", limit=3)
        assert len(results) == 3


class TestVersionOption:
    """Tests for the --version option."""

    def test_version_long_flag(self):
        """Test that --version shows version info."""
        import importlib.metadata

        from click.testing import CliRunner

        from agent_log_gif import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])

        expected_version = importlib.metadata.version("agent-log-gif")
        assert result.exit_code == 0
        assert expected_version in result.output

    def test_version_short_flag(self):
        """Test that -v shows version info."""
        import importlib.metadata

        from click.testing import CliRunner

        from agent_log_gif import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["-v"])

        expected_version = importlib.metadata.version("agent-log-gif")
        assert result.exit_code == 0
        assert expected_version in result.output
