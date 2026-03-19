"""Terminal frame renderer: converts styled text lines into Pillow images."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from agent_log_gif.theme import TerminalTheme

# Type alias: a styled line is a list of (text, hex_color) segments
StyledSegment = tuple[str, str]
StyledLine = list[StyledSegment]

# Sentinel segment: append to a StyledLine to mark it for background highlighting.
# The renderer draws a subtle background rectangle behind highlighted lines.
HIGHLIGHT_MARKER: StyledSegment = ("", "HIGHLIGHT")

# Title bar constants
TITLEBAR_HEIGHT = 36
TITLEBAR_COLOR = "#21222C"  # slightly darker than Dracula background
TRAFFIC_LIGHT_Y = 18  # center Y of dots in title bar
TRAFFIC_LIGHT_X_START = 18  # X of first dot
TRAFFIC_LIGHT_SPACING = 22  # spacing between dot centers
TRAFFIC_LIGHT_RADIUS = 6
TRAFFIC_LIGHT_COLORS = ["#FF5F56", "#FFBD2E", "#27C93F"]  # close, minimize, maximize
CORNER_RADIUS = 10


class TerminalRenderer:
    """Renders terminal frames as Pillow images.

    Each frame is a fixed-size viewport showing the bottom N rows of a
    text buffer. Text is drawn character-by-character using a monospace font.
    A macOS-style title bar with traffic light dots is drawn above the content.
    """

    # Supersampling factor for antialiased text rendering
    _SSAA = 2

    def __init__(self, theme: TerminalTheme | None = None, title: str = ""):
        self.theme = theme or TerminalTheme()
        self.title = title

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
        self._char_height_ss = bbox[3] - bbox[1] + 4 * ss

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

        self.image_width = content_width
        self.image_height = TITLEBAR_HEIGHT + content_height
        self._content_y_offset = TITLEBAR_HEIGHT

        # Internal rendering dimensions (2x)
        self._ss_width = self.image_width * ss
        self._ss_height = self.image_height * ss
        self._ss_padding = self.theme.padding * ss
        self._ss_padding_bottom = self.theme.padding_bottom * ss
        self._ss_titlebar_h = TITLEBAR_HEIGHT * ss
        self._ss_content_y = self._ss_titlebar_h

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
        ss = self._SSAA
        bg = self.theme.hex_to_rgb(self.theme.background)
        titlebar_bg = self.theme.hex_to_rgb(TITLEBAR_COLOR)

        # Render at 2x resolution for antialiased text
        img = Image.new("RGB", (self._ss_width, self._ss_height), bg)
        draw = ImageDraw.Draw(img)

        # Draw title bar background
        draw.rectangle(
            [0, 0, self._ss_width, self._ss_titlebar_h],
            fill=titlebar_bg,
        )

        # Draw rounded top corners
        _draw_rounded_top(
            draw,
            self._ss_width,
            self._ss_titlebar_h,
            titlebar_bg,
            bg,
            corner_radius=CORNER_RADIUS * ss,
        )

        # Draw traffic light dots
        for i, color in enumerate(TRAFFIC_LIGHT_COLORS):
            cx = TRAFFIC_LIGHT_X_START * ss + i * TRAFFIC_LIGHT_SPACING * ss
            cy = TRAFFIC_LIGHT_Y * ss
            r = TRAFFIC_LIGHT_RADIUS * ss
            rgb = self.theme.hex_to_rgb(color)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgb)

        # Draw title text (centered)
        if self.title:
            title_color = self.theme.hex_to_rgb(self.theme.comment)
            title_bbox = self._title_font_ss.getbbox(self.title)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (self._ss_width - title_width) // 2
            title_y = (self._ss_titlebar_h - (title_bbox[3] - title_bbox[1])) // 2
            draw.text(
                (title_x, title_y),
                self.title,
                fill=title_color,
                font=self._title_font_ss,
            )

        # Draw terminal content — bottom-aligned like real terminal UIs
        visible_lines = lines[-self.theme.rows :]
        num_visible = len(visible_lines)
        empty_rows_above = self.theme.rows - num_visible

        # Highlight color for user prompt lines (Dracula current_line)
        highlight_bg = self.theme.hex_to_rgb("#44475A")

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
                    [0, y, self._ss_width, y + self._char_height_ss],
                    fill=highlight_bg,
                )

            for seg in line:
                if seg is HIGHLIGHT_MARKER:
                    continue
                text, color_hex = seg
                rgb = self.theme.hex_to_rgb(color_hex)
                draw.text((x, y), text, fill=rgb, font=self._font_ss)
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


def _draw_rounded_top(
    draw, width, height, fill_color, bg_color, corner_radius=CORNER_RADIUS
):
    """Draw rounded top corners on the title bar.

    Draws the corner arcs by overlaying background-colored circles at the
    top-left and top-right corners.
    """
    r = corner_radius
    # Top-left corner: draw bg circle that "cuts" the corner
    draw.pieslice([0, 0, r * 2, r * 2], 180, 270, fill=bg_color)
    draw.rectangle([0, 0, r, r], fill=bg_color)
    draw.pieslice([0, 0, r * 2, r * 2], 180, 270, fill=fill_color)

    # Top-right corner
    draw.pieslice([width - r * 2, 0, width, r * 2], 270, 360, fill=bg_color)
    draw.rectangle([width - r, 0, width, r], fill=bg_color)
    draw.pieslice([width - r * 2, 0, width, r * 2], 270, 360, fill=fill_color)
