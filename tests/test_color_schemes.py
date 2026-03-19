"""Tests for color scheme support."""

from pathlib import Path

import pytest
from PIL import Image

from agent_log_gif.theme import (
    TerminalTheme,
    get_color_scheme,
    list_color_schemes,
)


class TestColorSchemeData:
    def test_bundled_json_exists(self):
        path = (
            Path(__file__).parent.parent
            / "src"
            / "agent_log_gif"
            / "color_schemes.json"
        )
        assert path.exists()

    def test_bundled_json_has_schemes(self):
        schemes = list_color_schemes()
        assert len(schemes) > 100

    def test_dracula_scheme_present(self):
        scheme = get_color_scheme("Dracula")
        assert scheme is not None
        assert scheme["background"] == "#282a36"
        assert scheme["foreground"] == "#f8f8f2"

    def test_lookup_is_case_insensitive(self):
        assert get_color_scheme("dracula") == get_color_scheme("Dracula")
        assert get_color_scheme("DRACULA") == get_color_scheme("Dracula")
        assert get_color_scheme("gruvbox dark") == get_color_scheme("Gruvbox Dark")

    def test_unknown_scheme_returns_none(self):
        assert get_color_scheme("NonexistentScheme12345") is None

    def test_all_schemes_have_required_keys(self):
        for name in list_color_schemes():
            scheme = get_color_scheme(name)
            assert "foreground" in scheme, f"{name} missing foreground"
            assert "background" in scheme, f"{name} missing background"


class TestThemeFromScheme:
    def test_creates_theme_from_scheme_name(self):
        theme = TerminalTheme.from_color_scheme("Dracula")
        assert theme.background == "#282a36"
        assert theme.foreground == "#f8f8f2"

    def test_maps_ansi_colors_to_theme_fields(self):
        theme = TerminalTheme.from_color_scheme("Dracula")
        # ansi_0 (black) → titlebar_color
        assert theme.titlebar_color == "#21222c"
        # ansi_8 (bright black) → comment
        assert theme.comment == "#6272a4"
        # ansi_6 (cyan) → prompt_color
        assert theme.prompt_color == "#8be9fd"
        # selection_color is derived by blending bg toward white (dark scheme)
        # Dracula bg=#282a36 blended 12% white → slightly lighter
        assert theme.selection_color != theme.background  # visually distinct

    def test_unknown_scheme_raises(self):
        with pytest.raises(ValueError, match="Unknown color scheme"):
            TerminalTheme.from_color_scheme("NonexistentScheme12345")

    def test_gruvbox_dark_theme(self):
        theme = TerminalTheme.from_color_scheme("Gruvbox Dark")
        assert theme.background == "#282828"
        assert theme.foreground == "#ebdbb2"

    def test_preserves_non_color_defaults(self):
        theme = TerminalTheme.from_color_scheme("Dracula")
        default = TerminalTheme()
        assert theme.font_size == default.font_size
        assert theme.cols == default.cols
        assert theme.rows == default.rows
        assert theme.padding == default.padding


class TestRendererWithScheme:
    def test_renders_with_color_scheme(self):
        from agent_log_gif.renderer import TerminalRenderer

        theme = TerminalTheme.from_color_scheme("Gruvbox Dark")
        renderer = TerminalRenderer(theme)
        frame = renderer.render_frame([[("Hello", theme.foreground)]])
        assert isinstance(frame, Image.Image)

    def test_scheme_changes_background_color(self):
        from agent_log_gif.renderer import TerminalRenderer

        dracula = TerminalRenderer(TerminalTheme.from_color_scheme("Dracula"))
        gruvbox = TerminalRenderer(TerminalTheme.from_color_scheme("Gruvbox Dark"))

        d_frame = dracula.render_frame([])
        g_frame = gruvbox.render_frame([])

        # Content area background should differ
        d_bg = d_frame.getpixel((d_frame.width // 2, d_frame.height // 2 + 20))
        g_bg = g_frame.getpixel((g_frame.width // 2, g_frame.height // 2 + 20))
        assert d_bg != g_bg

    def test_scheme_changes_titlebar_color(self):
        from agent_log_gif.renderer import TerminalRenderer

        dracula = TerminalRenderer(TerminalTheme.from_color_scheme("Dracula"))
        gruvbox = TerminalRenderer(TerminalTheme.from_color_scheme("Gruvbox Dark"))

        d_frame = dracula.render_frame([])
        g_frame = gruvbox.render_frame([])

        # Title bar center pixel should differ
        d_tb = d_frame.getpixel((d_frame.width // 2, 10))
        g_tb = g_frame.getpixel((g_frame.width // 2, 10))
        assert d_tb != g_tb
