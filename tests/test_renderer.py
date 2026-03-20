"""Tests for the terminal frame renderer."""

from PIL import Image

from agent_log_gif.renderer import HIGHLIGHT_MARKER, TerminalRenderer
from agent_log_gif.theme import TerminalTheme


class TestTerminalRenderer:
    @staticmethod
    def _rows_with_exact_color(
        frame: Image.Image, color: tuple[int, int, int], x_range: range | None = None
    ) -> list[int]:
        rows = []
        for y in range(frame.height):
            xs = x_range if x_range is not None else range(frame.width)
            if any(frame.getpixel((x, y)) == color for x in xs):
                rows.append(y)
        return rows

    def test_creates_image_of_correct_dimensions(self):
        theme = TerminalTheme(cols=80, rows=30, font_size=16, padding=20)
        renderer = TerminalRenderer(theme)

        frame = renderer.render_frame([])
        assert isinstance(frame, Image.Image)
        assert frame.size == (renderer.image_width, renderer.image_height)
        assert frame.size[0] > 0
        assert frame.size[1] > 0

    def test_empty_frame_has_background_in_content_area(self):
        theme = TerminalTheme(background="#282A36")
        renderer = TerminalRenderer(theme)

        frame = renderer.render_frame([])
        # Sample pixel in the content area (below title bar)
        content_y = frame.height // 2 + 20  # well into content area
        center = frame.getpixel((frame.width // 2, content_y))
        assert center == (40, 42, 54)  # #282A36

    def test_title_bar_present(self):
        """Frame is taller than content-only due to title bar."""
        theme = TerminalTheme(cols=80, rows=30, font_size=16, padding=20)
        renderer = TerminalRenderer(theme)

        frame = renderer.render_frame([])
        content_only_height = theme.rows * renderer.char_height + 2 * theme.padding
        assert frame.height > content_only_height

    def test_title_text_renders(self):
        """Title text in the title bar produces different pixels."""
        theme = TerminalTheme()
        no_title = TerminalRenderer(theme, title="")
        with_title = TerminalRenderer(theme, title="agent-log-gif")

        frame_no_title = no_title.render_frame([])
        frame_with_title = with_title.render_frame([])
        # Title bar area should differ
        assert frame_no_title.tobytes() != frame_with_title.tobytes()

    def test_renders_text(self):
        theme = TerminalTheme()
        renderer = TerminalRenderer(theme)

        lines = [[("Hello", "#F8F8F2")]]
        frame = renderer.render_frame(lines)

        # The frame should not be identical to an empty frame
        empty = renderer.render_frame([])
        assert frame.tobytes() != empty.tobytes()

    def test_viewport_scrolling(self):
        """When lines exceed rows, only the bottom rows are visible."""
        theme = TerminalTheme(rows=5)
        renderer = TerminalRenderer(theme)

        # Create 10 lines — only last 5 should be visible
        lines = [[(f"Line {i}", "#F8F8F2")] for i in range(10)]
        frame = renderer.render_frame(lines)

        # Frame should render without error
        assert isinstance(frame, Image.Image)

    def test_multiple_segments_per_line(self):
        """Lines with multiple colored segments render correctly."""
        theme = TerminalTheme()
        renderer = TerminalRenderer(theme)

        lines = [
            [("❯ ", "#8BE9FD"), ("hello world", "#F8F8F2")],
        ]
        frame = renderer.render_frame(lines)
        assert isinstance(frame, Image.Image)

    def test_cursor_renders(self):
        """Cursor block changes pixels at the cursor position."""
        theme = TerminalTheme()
        renderer = TerminalRenderer(theme)

        lines = [[("Hello", "#F8F8F2")]]
        no_cursor = renderer.render_frame(lines)
        with_cursor = renderer.render_frame(lines, cursor_pos=(0, 5))

        assert no_cursor.tobytes() != with_cursor.tobytes()

    def test_small_terminal(self):
        """Renderer works with small terminal dimensions."""
        theme = TerminalTheme(cols=20, rows=5, font_size=12, padding=5)
        renderer = TerminalRenderer(theme)

        lines = [[("Hi", "#F8F8F2")]]
        frame = renderer.render_frame(lines)
        assert frame.size[0] < 300
        assert frame.size[1] < 200

    def test_ssaa_factor_does_not_change_output_dimensions(self):
        """Different SSAA factors produce identical output sizes."""
        theme = TerminalTheme(cols=80, rows=30)
        r_15 = TerminalRenderer(theme, ssaa=1.5)
        r_20 = TerminalRenderer(theme, ssaa=2)
        assert r_15.image_width == r_20.image_width
        assert r_15.image_height == r_20.image_height

        frame_15 = r_15.render_frame([[("Hello", "#F8F8F2")]])
        frame_20 = r_20.render_frame([[("Hello", "#F8F8F2")]])
        assert frame_15.size == frame_20.size

    def test_highlighted_input_text_sits_higher_and_band_has_extra_bottom_room(self):
        theme = TerminalTheme(
            rows=3,
            cols=20,
            font_size=16,
            padding=10,
            padding_bottom=10,
            background="#000000",
            selection_color="#444444",
            foreground="#ffffff",
            prompt_color="#00ffff",
        )
        renderer = TerminalRenderer(theme)

        plain = renderer.render_frame(
            [[("❯ ", theme.prompt_color), ("hello", theme.foreground)]]
        )
        highlighted = renderer.render_frame(
            [
                [
                    ("❯ ", theme.prompt_color),
                    ("hello", theme.foreground),
                    HIGHLIGHT_MARKER,
                ]
            ]
        )

        prompt_rgb = theme.hex_to_rgb(theme.prompt_color)
        selection_rgb = theme.hex_to_rgb(theme.selection_color)
        text_window = range(theme.padding, min(highlighted.width, theme.padding + 120))

        plain_prompt_rows = self._rows_with_exact_color(plain, prompt_rgb, text_window)
        highlighted_prompt_rows = self._rows_with_exact_color(
            highlighted, prompt_rgb, text_window
        )
        assert min(highlighted_prompt_rows) < min(plain_prompt_rows)

        line_top = round(
            (
                renderer._ss_content_y
                + renderer._ss_padding
                + (theme.rows - 1) * renderer._char_height_ss
            )
            / renderer._SSAA
        )
        selection_rows = self._rows_with_exact_color(
            highlighted,
            selection_rgb,
            range(highlighted.width // 2, highlighted.width // 2 + 1),
        )
        assert min(selection_rows) <= line_top - 2
        assert max(selection_rows) >= line_top + renderer.char_height
