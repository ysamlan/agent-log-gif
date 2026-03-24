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

    def test_share_url_in_output(self, tmp_path):
        """json command prints a share URL containing #v1,."""
        fixture = Path(__file__).parent / "sample_session.jsonl"
        output = tmp_path / "share.gif"

        runner = CliRunner()
        result = runner.invoke(cli, ["json", str(fixture), "-o", str(output)])

        assert result.exit_code == 0, result.output
        assert "Share:" in result.output
        assert "#v1," in result.output

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

    def test_open_file_warns_when_xdg_open_missing(self, tmp_path, monkeypatch):
        """Missing xdg-open prints a warning instead of crashing."""
        output = tmp_path / "test.gif"

        monkeypatch.setattr(agent_log_gif.sys, "platform", "linux")
        monkeypatch.setattr(
            agent_log_gif.subprocess,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                FileNotFoundError(2, "No such file or directory", "xdg-open")
            ),
        )

        # Should not raise — just prints a warning
        agent_log_gif._open_file(output)


class TestLocalCommand:
    """Tests for the interactive `local` command with mocked questionary prompts."""

    def _fake_select(self, answers):
        """Return a patched questionary.select that yields answers in order.

        Each call to select(...).ask() pops the next value from *answers*.
        """
        it = iter(answers)

        class FakeQuestion:
            def __init__(self, *a, **kw):
                pass

            def ask(self):
                return next(it)

        def _select(*args, **kwargs):
            return FakeQuestion()

        return _select

    @staticmethod
    def _setup_fake_home(tmp_path, monkeypatch, codex=True, claude=False):
        """Create a fake home with optional .codex/.claude dirs, patching Path.home()."""
        fake_home = tmp_path / "home"
        if codex:
            (fake_home / ".codex" / "sessions").mkdir(parents=True)
        if claude:
            (fake_home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
        return fake_home

    def test_local_walks_through_interactive_prompts(self, tmp_path, monkeypatch):
        """local command uses questionary prompts and produces output."""
        # Create a fake session file the picker will "select"
        fixture = Path(__file__).parent / "sample_session.jsonl"
        output = tmp_path / "out.gif"

        # Fake having only a codex folder (skip source prompt)
        monkeypatch.setattr(
            agent_log_gif, "find_local_sessions", lambda *a, **kw: [(fixture, "hi")]
        )
        self._setup_fake_home(tmp_path, monkeypatch)

        # With -o, format prompt is skipped. Remaining prompts:
        # session picker → fixture, chrome → mac, show → "" (conversation only)
        monkeypatch.setattr(
            agent_log_gif.questionary,
            "select",
            self._fake_select([fixture, "mac", ""]),
        )
        # Loop prompt uses questionary.confirm → answer True
        monkeypatch.setattr(
            agent_log_gif.questionary,
            "confirm",
            self._fake_select([True]),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["local", "-o", str(output)])

        assert result.exit_code == 0, result.output
        assert output.exists()
        with Image.open(output) as img:
            assert img.format == "GIF"
            assert img.is_animated

    def test_local_cancel_at_session_picker_exits_cleanly(self, tmp_path, monkeypatch):
        """Pressing Ctrl-C (None from .ask()) at session picker exits without error."""
        fixture = Path(__file__).parent / "sample_session.jsonl"

        monkeypatch.setattr(
            agent_log_gif, "find_local_sessions", lambda *a, **kw: [(fixture, "hi")]
        )
        self._setup_fake_home(tmp_path, monkeypatch)

        # Return None (user cancelled) at the session picker
        monkeypatch.setattr(
            agent_log_gif.questionary,
            "select",
            self._fake_select([None]),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["local"])

        assert result.exit_code == 0
        assert "No session selected" in result.output

    def test_local_no_sessions_found(self, tmp_path, monkeypatch):
        """Shows message when no sessions exist."""
        self._setup_fake_home(tmp_path, monkeypatch)

        monkeypatch.setattr(agent_log_gif, "find_local_sessions", lambda *a, **kw: [])

        runner = CliRunner()
        result = runner.invoke(cli, ["local"])

        assert result.exit_code == 0
        assert "No" in result.output and "sessions found" in result.output

    def test_local_default_values_dont_crash(self):
        """Questionary default= values match Choice values (regression test)."""
        import questionary as q
        from questionary.prompts.common import InquirerControl

        # Validate defaults via InquirerControl directly — avoids creating
        # a terminal prompt (which fails in CI without a console/pty).
        for choices, default in [
            (
                [
                    q.Choice("GIF (default)", value="gif"),
                    q.Choice("MP4 (requires ffmpeg)", value="mp4"),
                    q.Choice("AVIF (requires ffmpeg)", value="avif"),
                ],
                "gif",
            ),
            (
                [
                    q.Choice("macOS (default)", value="mac"),
                    q.Choice("macOS square corners", value="mac-square"),
                    q.Choice("Windows 11", value="windows"),
                    q.Choice("Linux / GNOME", value="linux"),
                    q.Choice("None", value="none"),
                ],
                "mac",
            ),
            (
                [
                    q.Choice("Conversation only (default)", value=""),
                    q.Choice("+ Tool call names", value="calls"),
                    q.Choice("+ Tool calls and results", value="tools"),
                    q.Choice("Everything (tools + thinking)", value="all"),
                ],
                "",
            ),
        ]:
            # This raises ValueError if default doesn't match a choice value
            InquirerControl(choices, initial_choice=default)
