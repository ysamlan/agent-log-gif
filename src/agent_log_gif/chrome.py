"""Window chrome styles: macOS, Windows, Linux, or none."""

from __future__ import annotations

from enum import Enum

from PIL import ImageDraw, ImageFont

from agent_log_gif.theme import TerminalTheme


class ChromeStyle(str, Enum):
    """Window chrome style for the terminal frame."""

    NONE = "none"
    MAC = "mac"
    MAC_SQUARE = "mac-square"
    WINDOWS = "windows"
    LINUX = "linux"


def get_titlebar_height(style: ChromeStyle) -> int:
    """Return title bar height in 1x pixels for the given chrome style."""
    if style == ChromeStyle.NONE:
        return 0
    return 36


def get_corner_radius(style: ChromeStyle) -> int:
    """Return corner radius in 1x pixels for the given chrome style."""
    if style in (ChromeStyle.NONE, ChromeStyle.MAC_SQUARE):
        return 0
    if style == ChromeStyle.WINDOWS:
        return 8
    return 10  # mac, linux


def draw_titlebar(
    draw: ImageDraw.Draw,
    style: ChromeStyle,
    width: int,
    height: int,
    titlebar_color: tuple[int, int, int],
    bg_color: tuple[int, int, int],
    ss: int,
    title: str = "",
    title_font: ImageFont.FreeTypeFont | None = None,
    comment_color: tuple[int, int, int] = (98, 114, 164),
) -> None:
    """Draw window chrome onto the title bar area.

    All coordinates are in supersampled (ss×) pixels.
    """
    if style == ChromeStyle.NONE:
        return

    # Title bar background
    draw.rectangle([0, 0, width, height], fill=titlebar_color)

    # Rounded corners
    cr = get_corner_radius(style) * ss
    if cr > 0:
        _draw_rounded_top(draw, width, height, titlebar_color, bg_color, cr)

    # Style-specific window controls
    if style in (ChromeStyle.MAC, ChromeStyle.MAC_SQUARE):
        _draw_mac_controls(draw, ss)
    elif style == ChromeStyle.WINDOWS:
        _draw_windows_controls(draw, width, height, ss, comment_color)
    elif style == ChromeStyle.LINUX:
        _draw_linux_controls(draw, width, height, ss, comment_color)

    # Title text
    if title and title_font:
        _draw_title_text(
            draw, title, title_font, width, height, comment_color, style, ss
        )


# -- macOS ----------------------------------------------------------------

_MAC_TRAFFIC_Y = 18
_MAC_TRAFFIC_X_START = 18
_MAC_TRAFFIC_SPACING = 22
_MAC_TRAFFIC_RADIUS = 6
_MAC_TRAFFIC_COLORS = ("#FF5F56", "#FFBD2E", "#27C93F")


def _draw_mac_controls(draw: ImageDraw.Draw, ss: int) -> None:
    """Draw macOS traffic-light buttons (close, minimize, maximize)."""
    for i, hex_color in enumerate(_MAC_TRAFFIC_COLORS):
        cx = _MAC_TRAFFIC_X_START * ss + i * _MAC_TRAFFIC_SPACING * ss
        cy = _MAC_TRAFFIC_Y * ss
        r = _MAC_TRAFFIC_RADIUS * ss
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_hex_rgb(hex_color))


# -- Windows 11 -----------------------------------------------------------

_WIN_BTN_W = 46
_WIN_ICON_SIZE = 10


def _draw_windows_controls(
    draw: ImageDraw.Draw,
    width: int,
    titlebar_h: int,
    ss: int,
    icon_color: tuple[int, int, int],
) -> None:
    """Draw Windows 11 style minimize/maximize/close buttons on the right.

    Default state: no background on any button, just muted icons.
    """
    btn_w = _WIN_BTN_W * ss
    half = (_WIN_ICON_SIZE * ss) // 2
    lw = max(2, ss)
    cy = titlebar_h // 2

    # Close (rightmost) — just the × icon, no background
    x0 = width - btn_w
    cx = x0 + btn_w // 2
    draw.line(
        [(cx - half, cy - half), (cx + half, cy + half)], fill=icon_color, width=lw
    )
    draw.line(
        [(cx - half, cy + half), (cx + half, cy - half)], fill=icon_color, width=lw
    )

    # Maximize — □ outline
    x0 = width - 2 * btn_w
    cx = x0 + btn_w // 2
    draw.rectangle(
        [cx - half, cy - half, cx + half, cy + half], outline=icon_color, width=lw
    )

    # Minimize — ─ line
    x0 = width - 3 * btn_w
    cx = x0 + btn_w // 2
    draw.line([(cx - half, cy), (cx + half, cy)], fill=icon_color, width=lw)


# -- Linux / GNOME --------------------------------------------------------

_LINUX_ICON_SIZE = 10
_LINUX_BTN_SPACING = 28
_LINUX_BTN_X_END = 26  # more padding from right edge


def _draw_linux_controls(
    draw: ImageDraw.Draw,
    width: int,
    titlebar_h: int,
    ss: int,
    icon_color: tuple[int, int, int],
) -> None:
    """Draw GNOME header bar style controls — simple glyph icons on the right."""
    spacing = _LINUX_BTN_SPACING * ss
    half = (_LINUX_ICON_SIZE * ss) // 2
    lw = max(2, ss)
    cy = titlebar_h // 2
    x_close = width - _LINUX_BTN_X_END * ss

    # Close (rightmost) — ×
    draw.line(
        [(x_close - half, cy - half), (x_close + half, cy + half)],
        fill=icon_color,
        width=lw,
    )
    draw.line(
        [(x_close - half, cy + half), (x_close + half, cy - half)],
        fill=icon_color,
        width=lw,
    )

    # Maximize — □
    cx = x_close - spacing
    draw.rectangle(
        [cx - half, cy - half, cx + half, cy + half], outline=icon_color, width=lw
    )

    # Minimize — ─
    cx = x_close - 2 * spacing
    draw.line([(cx - half, cy), (cx + half, cy)], fill=icon_color, width=lw)


# -- Shared helpers -------------------------------------------------------


def _draw_title_text(
    draw: ImageDraw.Draw,
    title: str,
    font: ImageFont.FreeTypeFont,
    width: int,
    titlebar_h: int,
    color: tuple[int, int, int],
    style: ChromeStyle,
    ss: int,
) -> None:
    """Draw title text in the title bar."""
    bbox = font.getbbox(title)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    if style == ChromeStyle.WINDOWS:
        tx = 16 * ss  # left-aligned
    else:
        tx = (width - tw) // 2  # centered

    ty = (titlebar_h - th) // 2
    draw.text((tx, ty), title, fill=color, font=font)


def _draw_rounded_top(
    draw: ImageDraw.Draw,
    width: int,
    height: int,
    fill_color: tuple[int, int, int],
    bg_color: tuple[int, int, int],
    corner_radius: int,
) -> None:
    """Draw rounded top corners by overlaying background-colored arcs."""
    r = corner_radius
    # Top-left
    draw.pieslice([0, 0, r * 2, r * 2], 180, 270, fill=bg_color)
    draw.rectangle([0, 0, r, r], fill=bg_color)
    draw.pieslice([0, 0, r * 2, r * 2], 180, 270, fill=fill_color)
    # Top-right
    draw.pieslice([width - r * 2, 0, width, r * 2], 270, 360, fill=bg_color)
    draw.rectangle([width - r, 0, width, r], fill=bg_color)
    draw.pieslice([width - r * 2, 0, width, r * 2], 270, 360, fill=fill_color)


def _hex_rgb(h: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple (delegates to shared cached converter)."""
    return TerminalTheme.hex_to_rgb(h)
