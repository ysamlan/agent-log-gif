"""Terminal frame renderer: converts styled text lines into Pillow images."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from agent_log_gif.chrome import ChromeStyle, draw_titlebar, get_titlebar_height
from agent_log_gif.theme import TerminalTheme

# Type alias: a styled line is a list of (text, hex_color) segments
StyledSegment = tuple[str, str]
StyledLine = list[StyledSegment]

# Sentinel segment: append to a StyledLine to mark it for background highlighting.
# The renderer draws a subtle background rectangle behind highlighted lines.
HIGHLIGHT_MARKER: StyledSegment = ("", "HIGHLIGHT")


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
        ssaa: float = 2,
    ):
        self.theme = theme or TerminalTheme()
        self.title = title
        self.chrome = chrome
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
        content_width = self.theme.cols * self.char_width + 2 * self.theme.padding
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

    def _build_titlebar_template(self) -> Image.Image:
        """Pre-render the full background + title bar as a reusable template.

        This image has the correct background color everywhere and the title
        bar (corners, controls, title text) already drawn.
        Copying it is much cheaper than re-drawing primitives per frame.
        """
        ss = self._SSAA
        bg = self.theme.hex_to_rgb(self.theme.background)
        titlebar_bg = self.theme.hex_to_rgb(self.theme.titlebar_color)

        img = Image.new("RGB", (self._ss_width, self._ss_height), bg)
        draw = ImageDraw.Draw(img)

        draw_titlebar(
            draw,
            self.chrome,
            self._ss_width,
            self._ss_titlebar_h,
            titlebar_bg,
            bg,
            ss,
            title=self.title,
            title_font=self._title_font_ss if self.title else None,
            comment_color=self.theme.hex_to_rgb(self.theme.comment),
        )

        return img

    def render_frame(
        self,
        lines: list[StyledLine],
        cursor_pos: tuple[int, int] | None = None,
    ) -> Image.Image:
        """Render styled text lines into a terminal frame image.

        Args:
            lines: List of styled lines. Each line is a list of (text, hex_color)
                   segments. If there are more lines than theme.rows, only the
                   bottom theme.rows lines are shown (scrolling viewport).
            cursor_pos: Optional (row, col) for a cursor block. Row is relative
                        to the visible viewport.

        Returns:
            A PIL Image of the terminal frame.
        """
        # Start from the pre-rendered background + title bar template
        img = self._titlebar_template.copy()
        draw = ImageDraw.Draw(img)

        # Draw terminal content — bottom-aligned like real terminal UIs
        visible_lines = lines[-self.theme.rows :]
        num_visible = len(visible_lines)
        empty_rows_above = self.theme.rows - num_visible

        highlight_bg = self.theme.hex_to_rgb(self.theme.selection_color)

        for row_idx, line in enumerate(visible_lines):
            x = self._ss_padding
            y = (
                self._ss_content_y
                + self._ss_padding
                + (empty_rows_above + row_idx) * self._char_height_ss
            )
            has_highlight = any(seg == HIGHLIGHT_MARKER for seg in line)

            # Draw highlighted background for marked lines
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
                    fill=highlight_bg,
                )

            # Highlighted prompt/input lines read better with a slightly
            # higher baseline inside the selection band.
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

        # Draw cursor block if specified
        if cursor_pos is not None:
            crow, ccol = cursor_pos
            if 0 <= crow < num_visible:
                cx = self._ss_padding + ccol * self._char_width_ss
                cy = (
                    self._ss_content_y
                    + self._ss_padding
                    + (empty_rows_above + crow) * self._char_height_ss
                )
                cursor_color = self.theme.hex_to_rgb(self.theme.foreground)
                draw.rectangle(
                    [cx, cy, cx + self._char_width_ss, cy + self._char_height_ss],
                    fill=cursor_color,
                )

        # Downscale from 2x to 1x with Lanczos for smooth antialiasing
        return img.resize((self.image_width, self.image_height), Image.LANCZOS)
