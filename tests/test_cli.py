"""Tests for CLI commands."""

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner
from PIL import Image

import agent_log_gif
from agent_log_gif import cli


class TestJsonCommand:
    def test_produces_gif_from_jsonl(self, tmp_path):
        """json command produces a valid animated GIF from JSONL."""
        fixture = Path(__file__).parent / "sample_session.jsonl"
        output = tmp_path / "out.gif"

        runner = CliRunner()
        result = runner.invoke(cli, ["json", str(fixture), "-o", str(output)])

        assert result.exit_code == 0, result.output
        assert output.exists()
        with Image.open(output) as img:
            assert img.format == "GIF"
            assert img.is_animated

    def test_produces_gif_from_codex_jsonl(self, tmp_path):
        """json command works with Codex JSONL sessions."""
        fixture = Path(__file__).parent / "sample_codex_session.jsonl"
        output = tmp_path / "codex.gif"

        runner = CliRunner()
        result = runner.invoke(cli, ["json", str(fixture), "-o", str(output)])

        assert result.exit_code == 0, result.output
        assert output.exists()

    def test_produces_gif_from_json(self, tmp_path):
        """json command works with standard JSON sessions."""
        fixture = Path(__file__).parent / "sample_session.json"
        output = tmp_path / "json.gif"

        runner = CliRunner()
        result = runner.invoke(cli, ["json", str(fixture), "-o", str(output)])

        assert result.exit_code == 0, result.output
        assert output.exists()

    def test_turns_flag(self, tmp_path):
        """--turns limits the number of turns."""
        fixture = Path(__file__).parent / "sample_session.jsonl"
        output = tmp_path / "limited.gif"

        runner = CliRunner()
        result = runner.invoke(
            cli, ["json", str(fixture), "-o", str(output), "--turns", "1"]
        )

        assert result.exit_code == 0, result.output
        assert "1 turn" in result.output

    def test_missing_file_errors(self):
        """json command errors on missing file."""
        runner = CliRunner()
        result = runner.invoke(cli, ["json", "/nonexistent/file.jsonl"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "Error" in result.output

    def test_default_output_name(self, tmp_path, monkeypatch):
        """Without -o, output is named after input file stem."""
        fixture = Path(__file__).parent / "sample_session.jsonl"
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["json", str(fixture)])

        assert result.exit_code == 0, result.output
        assert (tmp_path / "sample_session.gif").exists()

    def test_canvas_bg_flag_sets_rounded_mac_corner_color(self, tmp_path):
        """--canvas-bg changes the outside-corner color for rounded mac chrome."""
        fixture = Path(__file__).parent / "sample_session.jsonl"
        output = tmp_path / "canvas.gif"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "json",
                str(fixture),
                "-o",
                str(output),
                "--chrome",
                "mac",
                "--canvas-bg",
                "#FFFFFF",
            ],
        )

        assert result.exit_code == 0, result.output
        with Image.open(output) as img:
            corner = img.convert("RGB").getpixel((0, 0))
            assert all(channel >= 245 for channel in corner)

    def test_canvas_bg_is_not_ignored_for_avif(self, tmp_path):
        """AVIF output should still honor the outer canvas color setting."""
        fixture = Path(__file__).parent / "sample_session.jsonl"
        output = tmp_path / "canvas.avif"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "json",
                str(fixture),
                "-o",
                str(output),
                "--format",
                "avif",
                "--chrome",
                "mac",
                "--canvas-bg",
                "#FFFFFF",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "ignored for AVIF" not in result.output
        assert output.exists()

    def test_fetch_url_to_tempfile_uses_unique_tempfile(self, tmp_path, monkeypatch):
        """Fetched URL input should not overwrite a predictable temp path."""

        class FakeResponse:
            text = '{"type":"summary","summary":"ok"}\n'

            def raise_for_status(self):
                return None

        existing = tmp_path / "claude-url-session.jsonl"
        existing.write_text("sentinel", encoding="utf-8")

        monkeypatch.setattr(
            agent_log_gif.httpx, "get", lambda *args, **kwargs: FakeResponse()
        )
        monkeypatch.setattr(
            agent_log_gif.tempfile,
            "gettempdir",
            lambda: str(tmp_path),
        )

        fetched = agent_log_gif.fetch_url_to_tempfile(
            "https://example.com/session.jsonl"
        )

        assert fetched != existing
        assert fetched.suffix == ".jsonl"
        assert fetched.read_text(encoding="utf-8") == FakeResponse.text
        assert existing.read_text(encoding="utf-8") == "sentinel"

    def test_open_file_on_windows_uses_startfile(self, tmp_path, monkeypatch):
        """Windows open path should bypass shell command interpolation."""
        opened = []
        run_calls = []
        output = tmp_path / "%COMSPEC%.gif"

        monkeypatch.setattr(agent_log_gif.sys, "platform", "win32")
        monkeypatch.setattr(
            agent_log_gif,
            "os",
            SimpleNamespace(startfile=lambda path: opened.append(path)),
            raising=False,
        )
        monkeypatch.setattr(
            agent_log_gif.subprocess,
            "run",
            lambda *args, **kwargs: run_calls.append((args, kwargs)),
        )

        agent_log_gif._open_file(output)

        assert opened == [str(output)]
        assert run_calls == []
