"""Terminal frame renderer: converts styled text lines into Pillow images."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from agent_log_gif.theme import TerminalTheme

# Type alias: a styled line is a list of (text, hex_color) segments
StyledSegment = tuple[str, str]
StyledLine = list[StyledSegment]

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

    def __init__(self, theme: TerminalTheme | None = None, title: str = ""):
        self.theme = theme or TerminalTheme()
        self.title = title
        self.font = ImageFont.truetype(self.theme.font_path, self.theme.font_size)

        # Smaller font for title bar text
        title_font_size = max(self.theme.font_size - 3, 10)
        self.title_font = ImageFont.truetype(self.theme.font_path, title_font_size)

        # Compute character metrics from font
        bbox = self.font.getbbox("M")
        self.char_width = int(self.font.getlength("M"))
        self.char_height = bbox[3] - bbox[1] + 4  # add small line spacing

        # Compute image dimensions (title bar + content + padding)
        content_width = self.theme.cols * self.char_width + 2 * self.theme.padding
        content_height = self.theme.rows * self.char_height + 2 * self.theme.padding

        self.image_width = content_width
        self.image_height = TITLEBAR_HEIGHT + content_height
        self._content_y_offset = TITLEBAR_HEIGHT

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
        bg = self.theme.hex_to_rgb(self.theme.background)
        titlebar_bg = self.theme.hex_to_rgb(TITLEBAR_COLOR)

        img = Image.new("RGB", (self.image_width, self.image_height), bg)
        draw = ImageDraw.Draw(img)

        # Draw title bar background
        draw.rectangle(
            [0, 0, self.image_width, TITLEBAR_HEIGHT],
            fill=titlebar_bg,
        )

        # Draw rounded top corners
        _draw_rounded_top(draw, self.image_width, TITLEBAR_HEIGHT, titlebar_bg, bg)

        # Draw traffic light dots
        for i, color in enumerate(TRAFFIC_LIGHT_COLORS):
            cx = TRAFFIC_LIGHT_X_START + i * TRAFFIC_LIGHT_SPACING
            cy = TRAFFIC_LIGHT_Y
            rgb = self.theme.hex_to_rgb(color)
            draw.ellipse(
                [
                    cx - TRAFFIC_LIGHT_RADIUS,
                    cy - TRAFFIC_LIGHT_RADIUS,
                    cx + TRAFFIC_LIGHT_RADIUS,
                    cy + TRAFFIC_LIGHT_RADIUS,
                ],
                fill=rgb,
            )

        # Draw title text (centered)
        if self.title:
            title_color = self.theme.hex_to_rgb(self.theme.comment)
            title_bbox = self.title_font.getbbox(self.title)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (self.image_width - title_width) // 2
            title_y = (TITLEBAR_HEIGHT - (title_bbox[3] - title_bbox[1])) // 2
            draw.text(
                (title_x, title_y), self.title, fill=title_color, font=self.title_font
            )

        # Draw terminal content
        visible_lines = lines[-self.theme.rows :]

        for row_idx, line in enumerate(visible_lines):
            x = self.theme.padding
            y = self._content_y_offset + self.theme.padding + row_idx * self.char_height

            for text, color_hex in line:
                rgb = self.theme.hex_to_rgb(color_hex)
                draw.text((x, y), text, fill=rgb, font=self.font)
                x += len(text) * self.char_width

        # Draw cursor block if specified
        if cursor_pos is not None:
            crow, ccol = cursor_pos
            if 0 <= crow < len(visible_lines):
                cx = self.theme.padding + ccol * self.char_width
                cy = (
                    self._content_y_offset
                    + self.theme.padding
                    + crow * self.char_height
                )
                cursor_color = self.theme.hex_to_rgb(self.theme.foreground)
                draw.rectangle(
                    [cx, cy, cx + self.char_width, cy + self.char_height],
                    fill=cursor_color,
                )

        return img


def _draw_rounded_top(draw, width, height, fill_color, bg_color):
    """Draw rounded top corners on the title bar.

    Draws the corner arcs by overlaying background-colored circles at the
    top-left and top-right corners.
    """
    r = CORNER_RADIUS
    # Top-left corner: draw bg circle that "cuts" the corner
    draw.pieslice([0, 0, r * 2, r * 2], 180, 270, fill=bg_color)
    draw.rectangle([0, 0, r, r], fill=bg_color)
    draw.pieslice([0, 0, r * 2, r * 2], 180, 270, fill=fill_color)

    # Top-right corner
    draw.pieslice([width - r * 2, 0, width, r * 2], 270, 360, fill=bg_color)
    draw.rectangle([width - r, 0, width, r], fill=bg_color)
    draw.pieslice([width - r * 2, 0, width, r * 2], 270, 360, fill=fill_color)
