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

    # Supersampling factor for antialiased text rendering
    _SSAA = 2

    def __init__(
        self,
        theme: TerminalTheme | None = None,
        title: str = "",
        chrome: ChromeStyle = ChromeStyle.MAC,
    ):
        self.theme = theme or TerminalTheme()
        self.title = title
        self.chrome = chrome

        # Load fonts at 2x size for supersampled rendering
        ss = self._SSAA
        self._font_ss = ImageFont.truetype(
            self.theme.font_path, self.theme.font_size * ss
        )
        title_font_size = max(self.theme.font_size - 3, 10)
        self._title_font_ss = ImageFont.truetype(
            self.theme.font_path, title_font_size * ss
        )

        # Compute character metrics from the supersampled font, then scale back
        bbox = self._font_ss.getbbox("M")
        self._char_width_ss = int(self._font_ss.getlength("M"))
        line_spacing = 4 * ss
        self._char_height_ss = bbox[3] - bbox[1] + line_spacing
        # Line spacing sits below the glyph. To center text in highlight
        # bands, shift text up and expand the band.
        self._text_nudge_ss = line_spacing // 2

        # Public metrics at 1x (used by animator for text wrapping calculations)
        self.char_width = self._char_width_ss // ss
        self.char_height = self._char_height_ss // ss

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

        # Internal rendering dimensions (2x)
        self._ss_width = self.image_width * ss
        self._ss_height = self.image_height * ss
        self._ss_padding = self.theme.padding * ss
        self._ss_padding_bottom = self.theme.padding_bottom * ss
        self._ss_titlebar_h = titlebar_h * ss
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
        # Extra padding so the band comfortably wraps shifted text
        hl_pad = 2 * self._SSAA

        for row_idx, line in enumerate(visible_lines):
            x = self._ss_padding
            y = (
                self._ss_content_y
                + self._ss_padding
                + (empty_rows_above + row_idx) * self._char_height_ss
            )

            # Draw highlighted background for marked lines
            if any(seg == HIGHLIGHT_MARKER for seg in line):
                draw.rectangle(
                    [
                        0,
                        y - self._text_nudge_ss - hl_pad,
                        self._ss_width,
                        y + self._char_height_ss - self._text_nudge_ss + hl_pad,
                    ],
                    fill=highlight_bg,
                )

            # Shift text up so it's centered in the cell (not flush to top
            # with all line spacing below)
            text_y = y - self._text_nudge_ss
            for seg in line:
                if seg is HIGHLIGHT_MARKER:
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
