"""Terminal frame renderer: converts styled text lines into Pillow images."""

from __future__ import annotations

import copy
import math

from PIL import Image, ImageDraw, ImageFont

from agent_log_gif.chrome import (
    ChromeStyle,
    draw_titlebar,
    draw_window_corners,
    get_titlebar_height,
)
from agent_log_gif.theme import TerminalTheme

# Type alias: a styled line is a list of (text, hex_color) segments
StyledSegment = tuple[str, str]
StyledLine = list[StyledSegment]

# Sentinel segment: append to a StyledLine to mark it for background highlighting.
# The renderer draws a subtle background rectangle behind highlighted lines.
HIGHLIGHT_MARKER: StyledSegment = ("", "HIGHLIGHT")


def _line_has_highlight(line: StyledLine) -> bool:
    return any(seg == HIGHLIGHT_MARKER for seg in line)


class TerminalRenderer:
    """Renders terminal frames as Pillow images.

    Each frame is a fixed-size viewport showing the bottom N rows of a
    text buffer. Text is drawn character-by-character using a monospace font.
    An optional window chrome (title bar with controls) is drawn above the content.
    """

    def __init__(
        self,
        theme: TerminalTheme | None = None,
        title: str = "",
        chrome: ChromeStyle = ChromeStyle.MAC,
        canvas_background: str | None = None,
        ssaa: float = 2,
    ):
        self.theme = theme or TerminalTheme()
        self.title = title
        self.chrome = chrome
        self.canvas_background = canvas_background
        self._SSAA = ssaa

        # Compute 1x character metrics from a 1x font so that output
        # dimensions are identical regardless of the supersample factor.
        font_1x = ImageFont.truetype(self.theme.font_path, self.theme.font_size)
        self.char_width = int(font_1x.getlength("M"))
        line_spacing = 4
        # Use ascent+descent (not bbox of "M") so descenders aren't clipped
        ascent_1x, descent_1x = font_1x.getmetrics()
        self.char_height = ascent_1x + descent_1x + line_spacing

        # Load fonts at ss× size for supersampled rendering
        ss = self._SSAA
        self._font_ss = ImageFont.truetype(
            self.theme.font_path, round(self.theme.font_size * ss)
        )
        title_font_size = max(self.theme.font_size - 3, 10)
        self._title_font_ss = ImageFont.truetype(
            self.theme.font_path, round(title_font_size * ss)
        )

        # Use actual ss× font metrics for text positioning so glyphs
        # don't overlap.  Output dimensions come from the 1x metrics above.
        self._char_width_ss = int(self._font_ss.getlength("M"))
        line_spacing_ss = round(line_spacing * ss)
        ascent_ss, descent_ss = self._font_ss.getmetrics()
        self._char_height_ss = ascent_ss + descent_ss + line_spacing_ss
        # Line spacing sits below the glyph, so text needs a small upward
        # correction to look vertically centered in the line box.
        self._text_nudge_ss = line_spacing_ss // 2
        # Highlighted user input sits a touch higher than regular terminal
        # text, with extra band padding to avoid clipped antialiasing.
        self._highlight_text_raise_ss = 0
        self._highlight_top_pad_ss = round(ss * 4)
        self._highlight_bottom_pad_ss = round(ss * 1)

        # Compute final output dimensions (1x)
        # Use ceil on the total text width (not per-char) so the canvas
        # fits all cols at the font's fractional glyph advance without
        # adding excess per-column padding.
        content_width = (
            math.ceil(self.theme.cols * font_1x.getlength("M")) + 2 * self.theme.padding
        )
        content_height = (
            self.theme.rows * self.char_height
            + self.theme.padding
            + self.theme.padding_bottom
        )

        titlebar_h = get_titlebar_height(chrome)
        self.image_width = content_width
        self.image_height = titlebar_h + content_height
        self._content_y_offset = titlebar_h

        # Internal rendering dimensions (ss×)
        self._ss_width = round(self.image_width * ss)
        self._ss_height = round(self.image_height * ss)
        self._ss_padding = round(self.theme.padding * ss)
        self._ss_padding_bottom = round(self.theme.padding_bottom * ss)
        self._ss_titlebar_h = round(titlebar_h * ss)
        self._ss_content_y = self._ss_titlebar_h

        # Pre-render title bar template (background + chrome + title text)
        # so render_frame only draws content.
        self._titlebar_template = self._build_titlebar_template()

        # Cached background color for clearing dirty rows
        self._bg_rgb = self.theme.hex_to_rgb(self.theme.background)
        self._highlight_bg = self.theme.hex_to_rgb(self.theme.selection_color)

        # Incremental rendering cache state
        self._prev_visible: list[StyledLine] | None = None
        self._prev_cursor: tuple[int, int] | None = None
        self._prev_output: Image.Image | None = None
        self._prev_ss_img: Image.Image | None = None
        self._prev_empty_above: int | None = None

    def reset(self) -> None:
        """Clear cached state so the next render_frame() does a full redraw.

        Call this when reusing a renderer for a different session or when
        the frame sequence is no longer sequential.
        """
        self._prev_visible = None
        self._prev_cursor = None
        self._prev_output = None
        self._prev_ss_img = None
        self._prev_empty_above = None

    def _build_titlebar_template(self) -> Image.Image:
        """Pre-render the full background + title bar as a reusable template.

        This image has the correct background color everywhere and the title
        bar (corners, controls, title text) already drawn.
        Copying it is much cheaper than re-drawing primitives per frame.
        """
        ss = self._SSAA
        bg = self.theme.hex_to_rgb(self.theme.background)
        canvas_bg = self.theme.hex_to_rgb(self._outer_canvas_background())
        titlebar_bg = self.theme.hex_to_rgb(self.theme.titlebar_color)

        img = Image.new("RGB", (self._ss_width, self._ss_height), canvas_bg)
        draw = ImageDraw.Draw(img)
        if canvas_bg != bg:
            draw.rectangle(
                [0, self._ss_content_y, self._ss_width, self._ss_height],
                fill=bg,
            )

        draw_titlebar(
            draw,
            self.chrome,
            self._ss_width,
            self._ss_titlebar_h,
            titlebar_bg,
            canvas_bg,
            ss,
            title=self.title,
            title_font=self._title_font_ss if self.title else None,
            comment_color=self.theme.hex_to_rgb(self.theme.comment),
        )
        draw_window_corners(
            draw,
            self.chrome,
            self._ss_width,
            self._ss_height,
            bg,
            canvas_bg,
            ss,
        )

        return img

    def _outer_canvas_background(self) -> str:
        """Return the color used outside rounded chrome corners."""
        if self.chrome == ChromeStyle.MAC and self.canvas_background is not None:
            return self.canvas_background
        return self.theme.background

    def _row_y(self, row_idx: int, empty_rows_above: int) -> int:
        """Compute the y coordinate for a given row index in ss space."""
        return (
            self._ss_content_y
            + self._ss_padding
            + (empty_rows_above + row_idx) * self._char_height_ss
        )

    def _draw_line(
        self,
        draw: ImageDraw.ImageDraw,
        line: StyledLine,
        row_idx: int,
        empty_rows_above: int,
    ) -> None:
        """Draw a single line (highlight band + text segments) at the given row."""
        x = self._ss_padding
        y = self._row_y(row_idx, empty_rows_above)
        has_highlight = _line_has_highlight(line)

        if has_highlight:
            draw.rectangle(
                [
                    0,
                    y - self._text_nudge_ss - self._highlight_top_pad_ss,
                    self._ss_width,
                    y
                    + self._char_height_ss
                    - self._text_nudge_ss
                    + self._highlight_bottom_pad_ss,
                ],
                fill=self._highlight_bg,
            )

        text_y = y - self._text_nudge_ss
        if has_highlight:
            text_y -= self._highlight_text_raise_ss
        for seg in line:
            if seg == HIGHLIGHT_MARKER:
                continue
            text, color_hex = seg
            rgb = self.theme.hex_to_rgb(color_hex)
            draw.text((x, text_y), text, fill=rgb, font=self._font_ss)
            x += len(text) * self._char_width_ss

    def _draw_cursor(
        self,
        draw: ImageDraw.ImageDraw,
        cursor_pos: tuple[int, int],
        num_visible: int,
        empty_rows_above: int,
    ) -> None:
        """Draw a cursor block at the given (row, col) position."""
        crow, ccol = cursor_pos
        if 0 <= crow < num_visible:
            cx = self._ss_padding + ccol * self._char_width_ss
            cy = self._row_y(crow, empty_rows_above)
            cursor_color = self.theme.hex_to_rgb(self.theme.foreground)
            draw.rectangle(
                [cx, cy, cx + self._char_width_ss, cy + self._char_height_ss],
                fill=cursor_color,
            )

    def _clear_line_region(
        self,
        draw: ImageDraw.ImageDraw,
        row_idx: int,
        empty_rows_above: int,
        old_had_highlight: bool,
    ) -> None:
        """Clear a row's region to background color before redrawing.

        Clears the tile plus the 4px text overhang above it.
        If the old line had a highlight band, extends the clear to cover
        the highlight's top padding as well.
        """
        y = self._row_y(row_idx, empty_rows_above)

        clear_y_top = y - self._text_nudge_ss
        if old_had_highlight:
            clear_y_top = y - self._text_nudge_ss - self._highlight_top_pad_ss

        clear_y_bot = y + self._char_height_ss

        draw.rectangle(
            [0, clear_y_top, self._ss_width, clear_y_bot],
            fill=self._bg_rgb,
        )

    def render_frame(
        self,
        lines: list[StyledLine],
        cursor_pos: tuple[int, int] | None = None,
    ) -> Image.Image:
        """Render styled text lines into a terminal frame image.

        This method caches state from the previous call to accelerate
        rendering.  For correct output, calls should represent a sequential
        animation.  To reset state (e.g., when reusing a renderer for a
        different session), call ``reset()``.

        Args:
            lines: List of styled lines. Each line is a list of (text, hex_color)
                   segments. If there are more lines than theme.rows, only the
                   bottom theme.rows lines are shown (scrolling viewport).
            cursor_pos: Optional (row, col) for a cursor block. Row is relative
                        to the visible viewport.

        Returns:
            A PIL Image of the terminal frame.
        """
        visible = lines[-self.theme.rows :]
        empty_above = self.theme.rows - len(visible)

        # Tier 1: identical frame → return cached output
        if (
            self._prev_output is not None
            and visible == self._prev_visible
            and cursor_pos == self._prev_cursor
        ):
            return self._prev_output.copy()

        # Decide: full redraw or incremental
        can_incremental = (
            self._prev_ss_img is not None
            and self._prev_visible is not None
            and empty_above == self._prev_empty_above
            and len(visible) == len(self._prev_visible)
        )

        if can_incremental:
            dirty: set[int] = set()

            for i in range(len(visible)):
                if visible[i] != self._prev_visible[i]:
                    dirty.add(i)

            # Cursor change: mark old and new cursor rows dirty
            if cursor_pos != self._prev_cursor:
                if self._prev_cursor is not None:
                    old_crow = self._prev_cursor[0]
                    if 0 <= old_crow < len(self._prev_visible):
                        dirty.add(old_crow)
                if cursor_pos is not None:
                    new_crow = cursor_pos[0]
                    if 0 <= new_crow < len(visible):
                        dirty.add(new_crow)

            # Highlight transition: propagate one level up
            for i in list(dirty):
                if i > 0 and (i - 1) not in dirty:
                    old_hl = _line_has_highlight(self._prev_visible[i])
                    new_hl = _line_has_highlight(visible[i])
                    if old_hl and not new_hl:
                        dirty.add(i - 1)

            # Fall back to full if most rows are dirty
            if len(dirty) > len(visible) // 2:
                can_incremental = False

        if not can_incremental:
            # Full redraw
            img = self._titlebar_template.copy()
            draw = ImageDraw.Draw(img)
            for i, line in enumerate(visible):
                self._draw_line(draw, line, i, empty_above)
        else:
            # Incremental: mutate cached ss image
            img = self._prev_ss_img  # reuse in place
            draw = ImageDraw.Draw(img)
            for i in sorted(dirty):  # top-to-bottom for correct highlight layering
                old_had_hl = _line_has_highlight(self._prev_visible[i])
                self._clear_line_region(draw, i, empty_above, old_had_hl)
                self._draw_line(draw, visible[i], i, empty_above)

        # Cursor
        if cursor_pos is not None:
            self._draw_cursor(draw, cursor_pos, len(visible), empty_above)

        # Downscale from 2x to 1x with Lanczos for smooth antialiasing
        output = img.resize((self.image_width, self.image_height), Image.LANCZOS)

        # Update cache
        self._prev_visible = copy.deepcopy(visible)
        self._prev_cursor = cursor_pos
        self._prev_output = output
        self._prev_ss_img = img
        self._prev_empty_above = empty_above

        return output
