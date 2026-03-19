"""Tests for terminal theme and spinner data."""

from pathlib import Path

from agent_log_gif.spinner import RAINBOW_COLORS, SPINNER_FRAMES, SPINNER_VERBS
from agent_log_gif.theme import DRACULA, TerminalTheme


class TestTerminalTheme:
    def test_default_theme_has_dracula_background(self):
        theme = TerminalTheme()
        assert theme.background == "#282A36"

    def test_default_font_path_resolves_to_bundled_font(self):
        theme = TerminalTheme()
        assert Path(theme.font_path).exists()
        assert "JetBrainsMono" in theme.font_path

    def test_default_dimensions(self):
        theme = TerminalTheme()
        assert theme.cols == 80
        assert theme.rows == 30
        assert theme.font_size == 16
        assert theme.padding == 20

    def test_hex_to_rgb(self):
        theme = TerminalTheme()
        assert theme.hex_to_rgb("#FF5555") == (255, 85, 85)
        assert theme.hex_to_rgb("#282A36") == (40, 42, 54)
        assert theme.hex_to_rgb("000000") == (0, 0, 0)

    def test_custom_theme(self):
        theme = TerminalTheme(background="#000000", cols=120, rows=40)
        assert theme.background == "#000000"
        assert theme.cols == 120
        assert theme.rows == 40


class TestDraculaPalette:
    def test_has_required_colors(self):
        required = [
            "background",
            "foreground",
            "comment",
            "red",
            "green",
            "yellow",
            "cyan",
            "purple",
            "pink",
            "orange",
        ]
        for color in required:
            assert color in DRACULA, f"Missing color: {color}"

    def test_all_colors_are_hex(self):
        for name, value in DRACULA.items():
            assert value.startswith("#"), f"{name} is not hex: {value}"
            assert len(value) == 7, f"{name} has wrong length: {value}"


class TestSpinnerData:
    def test_spinner_has_10_frames(self):
        assert len(SPINNER_FRAMES) == 10

    def test_spinner_frames_are_single_chars(self):
        for frame in SPINNER_FRAMES:
            assert len(frame) == 1

    def test_rainbow_has_7_colors(self):
        assert len(RAINBOW_COLORS) == 7

    def test_rainbow_colors_are_hex(self):
        for color in RAINBOW_COLORS:
            assert color.startswith("#")

    def test_verbs_not_empty(self):
        assert len(SPINNER_VERBS) > 20
