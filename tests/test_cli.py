"""Tests for CLI commands."""

from pathlib import Path

from click.testing import CliRunner
from PIL import Image

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
