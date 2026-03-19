"""Terminal theme configuration: colors, font, dimensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _default_font_path() -> str:
    """Return path to the bundled JetBrains Mono Regular font."""
    return str(Path(__file__).parent / "fonts" / "JetBrainsMono-Regular.ttf")


# Dracula color palette (official spec)
DRACULA = {
    "background": "#282A36",
    "foreground": "#F8F8F2",
    "comment": "#6272A4",
    "current_line": "#44475A",
    "selection": "#44475A",
    "red": "#FF5555",
    "orange": "#FFB86C",
    "yellow": "#F1FA8C",
    "green": "#50FA7B",
    "cyan": "#8BE9FD",
    "purple": "#BD93F9",
    "pink": "#FF79C6",
    # Standard ANSI mapping
    "black": "#21222C",
    "bright_black": "#6272A4",
    "bright_red": "#FF6E6E",
    "bright_green": "#69FF94",
    "bright_yellow": "#FFFFA5",
    "bright_blue": "#D6ACFF",
    "bright_magenta": "#FF92DF",
    "bright_cyan": "#A4FFFF",
    "white": "#F8F8F2",
    "bright_white": "#FFFFFF",
}


@dataclass
class TerminalTheme:
    """Visual configuration for terminal frame rendering."""

    # Colors
    background: str = DRACULA["background"]
    foreground: str = DRACULA["foreground"]
    comment: str = DRACULA["comment"]
    prompt_color: str = DRACULA["cyan"]  # ❯ color
    assistant_color: str = DRACULA["green"]  # ● color
    separator_color: str = DRACULA["comment"]  # ─── color

    # Font
    font_path: str = field(default_factory=_default_font_path)
    font_size: int = 16

    # Terminal dimensions (characters)
    cols: int = 80
    rows: int = 30

    # Pixel padding around terminal content
    padding: int = 20

    def hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        """Convert hex color string to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )
