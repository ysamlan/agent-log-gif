"""Tests for the terminal frame renderer."""

from PIL import Image

from agent_log_gif.renderer import TerminalRenderer
from agent_log_gif.theme import TerminalTheme


class TestTerminalRenderer:
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
