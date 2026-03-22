"""Tests for the terminal frame renderer."""

from PIL import Image, ImageFont

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

    def test_full_width_text_not_clipped(self):
        """Text filling all `cols` columns must not be clipped at the right edge.

        Regression: int() truncation of fractional char width made the canvas
        narrower than the font's actual glyph advances, clipping the last
        character on full-width lines.
        """
        from agent_log_gif.chrome import ChromeStyle, get_titlebar_height

        theme = TerminalTheme(cols=40, rows=5)
        renderer = TerminalRenderer(theme)
        bg = theme.hex_to_rgb(theme.background)
        titlebar_h = get_titlebar_height(ChromeStyle.MAC)

        # Render a full-width line and find the rightmost foreground pixel
        # in the content area (below the titlebar).
        full_line = "M" * 40
        frame = renderer.render_frame([[(full_line, theme.foreground)]])

        rightmost_text_x = 0
        for x in range(frame.width - 1, -1, -1):
            for y in range(titlebar_h, frame.height):
                if frame.getpixel((x, y)) != bg:
                    rightmost_text_x = x
                    break
            if rightmost_text_x:
                break

        # Right margin (canvas edge minus rightmost text pixel) should be
        # roughly comparable to the left padding — not wildly larger.
        right_margin = frame.width - rightmost_text_x
        assert right_margin <= theme.padding * 2, (
            f"Right margin {right_margin}px is too wide vs left padding "
            f"{theme.padding}px — text isn't filling the available width"
        )

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

    def test_highlighted_input_has_selection_band(self):
        """Highlighted lines have a selection background band around the text."""
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

        highlighted = renderer.render_frame(
            [
                [
                    ("❯ ", theme.prompt_color),
                    ("hello", theme.foreground),
                    HIGHLIGHT_MARKER,
                ]
            ]
        )

        selection_rgb = theme.hex_to_rgb(theme.selection_color)
        selection_rows = self._rows_with_exact_color(
            highlighted,
            selection_rgb,
            range(highlighted.width // 2, highlighted.width // 2 + 1),
        )
        # Band should span a meaningful number of rows around the text
        assert len(selection_rows) >= renderer.char_height - 2

    def test_char_height_includes_descenders(self):
        """char_height must cover the full ascent+descent so descenders aren't clipped."""
        theme = TerminalTheme(font_size=16)
        font = ImageFont.truetype(theme.font_path, theme.font_size)
        ascent, descent = font.getmetrics()
        full_line_height = ascent + descent

        renderer = TerminalRenderer(theme)
        # char_height (before line_spacing) must be at least ascent+descent
        line_spacing = 4
        assert renderer.char_height >= full_line_height + line_spacing, (
            f"char_height {renderer.char_height} < font height {full_line_height} + "
            f"line_spacing {line_spacing}; descenders will be clipped"
        )

    def test_descender_pixels_not_overlapped(self):
        """Descenders on one row must not overlap into the next row's text area."""
        theme = TerminalTheme(
            rows=3,
            cols=20,
            font_size=16,
            padding=10,
            padding_bottom=10,
            background="#000000",
            foreground="#ffffff",
        )
        renderer = TerminalRenderer(theme)
        # Row 0: "g" with descenders, Row 1: "M" (no descenders), Row 2: empty
        # Color row 0 green, row 1 red — if green pixels appear in row 1's band,
        # descenders are overlapping.
        frame = renderer.render_frame(
            [
                [("ggggg", "#00ff00")],
                [("MMMMM", "#ff0000")],
            ]
        )
        green = (0, 255, 0)
        red = (255, 0, 0)

        # Find the topmost red pixel (start of row 1's text)
        top_red = None
        for y in range(frame.height):
            if any(frame.getpixel((x, y)) == red for x in range(10, 120, 5)):
                top_red = y
                break

        # Check no green pixels at or below the red row's start
        assert top_red is not None, "Should find red pixels"
        green_in_red_zone = False
        for y in range(top_red, frame.height):
            if any(frame.getpixel((x, y)) == green for x in range(10, 120, 5)):
                green_in_red_zone = True
                break

        assert not green_in_red_zone, (
            f"Descender overlap: green pixels found at y={y} "
            f"(red row starts at y={top_red})"
        )


class TestIncrementalRendering:
    """Test that incremental rendering produces pixel-identical output to fresh rendering.

    Each test uses a fresh TerminalRenderer as the oracle (not reset()) to ensure
    the incremental renderer matches a fully independent stateless renderer.
    """

    THEME = TerminalTheme(
        rows=10,
        cols=40,
        font_size=14,
        padding=10,
        padding_bottom=10,
        background="#1e1e2e",
        foreground="#cdd6f4",
        selection_color="#45475a",
        prompt_color="#89b4fa",
    )

    @staticmethod
    def _fresh_render(theme, lines, cursor_pos=None):
        """Render a single frame with a brand-new renderer (oracle)."""
        return TerminalRenderer(theme).render_frame(lines, cursor_pos)

    def test_incremental_matches_full_redraw_sequence(self):
        """Render a diverse 15-frame sequence; every frame matches fresh renderer."""
        theme = self.THEME
        renderer = TerminalRenderer(theme)

        # Build a sequence of frames with diverse transitions:
        # empty → text → more text → highlight → scroll → cursor → highlight removal → etc.
        frames = [
            # 0: empty
            ([], None),
            # 1: single line of text
            ([[("Hello", "#cdd6f4")]], None),
            # 2: two lines
            ([[("Hello", "#cdd6f4")], [("World", "#cdd6f4")]], None),
            # 3: add highlighted line
            (
                [
                    [("Hello", "#cdd6f4")],
                    [("World", "#cdd6f4")],
                    [("❯ ", "#89b4fa"), ("input", "#cdd6f4"), HIGHLIGHT_MARKER],
                ],
                None,
            ),
            # 4: more lines (approaching scroll)
            (
                [[(f"Line {i}", "#cdd6f4")] for i in range(8)]
                + [[("❯ ", "#89b4fa"), ("cmd", "#cdd6f4"), HIGHLIGHT_MARKER]],
                None,
            ),
            # 5: scroll — more lines than viewport
            (
                [[(f"Line {i}", "#cdd6f4")] for i in range(12)],
                None,
            ),
            # 6: add cursor
            (
                [[(f"Line {i}", "#cdd6f4")] for i in range(12)],
                (9, 3),
            ),
            # 7: move cursor
            (
                [[(f"Line {i}", "#cdd6f4")] for i in range(12)],
                (8, 5),
            ),
            # 8: remove cursor
            (
                [[(f"Line {i}", "#cdd6f4")] for i in range(12)],
                None,
            ),
            # 9: change one line in middle of viewport
            (
                [[(f"Line {i}", "#cdd6f4")] for i in range(11)]
                + [[("CHANGED", "#ff0000")]],
                None,
            ),
            # 10: highlight a line
            (
                [[(f"Line {i}", "#cdd6f4")] for i in range(11)]
                + [[("❯ ", "#89b4fa"), ("typed", "#cdd6f4"), HIGHLIGHT_MARKER]],
                None,
            ),
            # 11: remove highlight (transition)
            (
                [[(f"Line {i}", "#cdd6f4")] for i in range(11)]
                + [[("plain line", "#cdd6f4")]],
                None,
            ),
            # 12: completely different content
            (
                [[("New content", "#ff79c6")] for _ in range(5)],
                None,
            ),
            # 13: back to empty
            ([], None),
            # 14: single line with cursor
            ([[("Final", "#cdd6f4")]], (0, 5)),
        ]

        for i, (lines, cursor) in enumerate(frames):
            incremental = renderer.render_frame(lines, cursor)
            oracle = self._fresh_render(theme, lines, cursor)
            assert incremental.tobytes() == oracle.tobytes(), (
                f"Frame {i}: incremental output differs from fresh render"
            )

    def test_scroll_matches_fresh_render(self):
        """Progressive line addition causing viewport scroll matches fresh renderer."""
        theme = self.THEME
        renderer = TerminalRenderer(theme)

        for n in range(1, theme.rows + 5):
            lines = [[(f"Row {i}", "#cdd6f4")] for i in range(n)]
            incremental = renderer.render_frame(lines)
            oracle = self._fresh_render(theme, lines)
            assert incremental.tobytes() == oracle.tobytes(), (
                f"Scroll step {n}: incremental output differs from fresh render"
            )

    def test_highlight_transition_matches_fresh_render(self):
        """Highlighted line replaced by non-highlighted line at same position."""
        theme = self.THEME
        renderer = TerminalRenderer(theme)

        base = [[(f"Line {i}", "#cdd6f4")] for i in range(8)]

        # Frame 1: line 8 is highlighted
        lines_hl = base + [
            [("❯ ", "#89b4fa"), ("input text", "#cdd6f4"), HIGHLIGHT_MARKER]
        ]
        f1 = renderer.render_frame(lines_hl)
        assert f1.tobytes() == self._fresh_render(theme, lines_hl).tobytes()

        # Frame 2: line 8 loses highlight
        lines_no_hl = base + [[("plain text", "#cdd6f4")]]
        f2 = renderer.render_frame(lines_no_hl)
        assert f2.tobytes() == self._fresh_render(theme, lines_no_hl).tobytes()

        # Frame 3: line 8 gains highlight again
        lines_hl2 = base + [
            [("❯ ", "#89b4fa"), ("new input", "#cdd6f4"), HIGHLIGHT_MARKER]
        ]
        f3 = renderer.render_frame(lines_hl2)
        assert f3.tobytes() == self._fresh_render(theme, lines_hl2).tobytes()

    def test_cursor_move_matches_fresh_render(self):
        """Cursor appears, moves, and disappears — each step matches fresh renderer."""
        theme = self.THEME
        renderer = TerminalRenderer(theme)

        lines = [[(f"Line {i}", "#cdd6f4")] for i in range(5)]

        steps = [
            (lines, None),  # no cursor
            (lines, (4, 0)),  # cursor appears
            (lines, (4, 3)),  # cursor moves right
            (lines, (3, 0)),  # cursor moves to different row
            (lines, None),  # cursor disappears
        ]

        for i, (ln, cur) in enumerate(steps):
            incremental = renderer.render_frame(ln, cur)
            oracle = self._fresh_render(theme, ln, cur)
            assert incremental.tobytes() == oracle.tobytes(), (
                f"Cursor step {i}: incremental output differs from fresh render"
            )

    def test_reset_produces_fresh_state(self):
        """After reset(), next frame matches a brand-new renderer."""
        theme = self.THEME
        renderer = TerminalRenderer(theme)

        # Render some frames to build up cache state
        renderer.render_frame([[(f"Line {i}", "#cdd6f4")] for i in range(8)])
        renderer.render_frame(
            [[(f"Line {i}", "#cdd6f4")] for i in range(10)], cursor_pos=(5, 2)
        )

        # Reset
        renderer.reset()

        # Next frame should match a completely fresh renderer
        lines = [[("After reset", "#ff79c6")]]
        after_reset = renderer.render_frame(lines)
        oracle = self._fresh_render(theme, lines)
        assert after_reset.tobytes() == oracle.tobytes()
