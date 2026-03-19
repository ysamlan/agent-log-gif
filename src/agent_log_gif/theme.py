"""Terminal theme configuration: colors, font, dimensions."""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from pathlib import Path

_COLOR_SCHEMES_PATH = Path(__file__).parent / "color_schemes.json"
_color_schemes_cache: dict[str, dict[str, str]] | None = None


def _default_font_path() -> str:
    """Return path to the bundled DejaVu Sans Mono font.

    DejaVu is the default because it has excellent Unicode coverage
    (spinner stars, bullets, box-drawing characters). Other monospace
    fonts can be used via --font if preferred.
    """
    return str(Path(__file__).parent / "fonts" / "DejaVuSansMono.ttf")


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


def _load_color_schemes() -> dict[str, dict[str, str]]:
    """Load and cache the bundled color scheme data."""
    global _color_schemes_cache
    if _color_schemes_cache is None:
        _color_schemes_cache = json.loads(_COLOR_SCHEMES_PATH.read_text())
    return _color_schemes_cache


def list_color_schemes() -> list[str]:
    """Return sorted list of available color scheme names."""
    return sorted(_load_color_schemes().keys())


def get_color_scheme(name: str) -> dict[str, str] | None:
    """Look up a color scheme by name (case-insensitive).

    Returns the scheme dict or None if not found.
    """
    schemes = _load_color_schemes()
    # Exact match first
    if name in schemes:
        return schemes[name]
    # Case-insensitive fallback
    lower = name.lower()
    for key, value in schemes.items():
        if key.lower() == lower:
            return value
    return None


def _highlight_for_background(bg_hex: str) -> str:
    """Derive a subtle highlight bar color from the background.

    Uses the same approach as Codex: alpha-blend toward black on light
    backgrounds and toward white on dark backgrounds.
    """
    h = bg_hex.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    if luma > 128:
        # Light: blend 4% black
        top, alpha = (0, 0, 0), 0.06
    else:
        # Dark: blend 12% white
        top, alpha = (255, 255, 255), 0.12
    nr = int(top[0] * alpha + r * (1 - alpha))
    ng = int(top[1] * alpha + g * (1 - alpha))
    nb = int(top[2] * alpha + b * (1 - alpha))
    return f"#{nr:02x}{ng:02x}{nb:02x}"


@dataclass
class TerminalTheme:
    """Visual configuration for terminal frame rendering."""

    # Colors
    background: str = DRACULA["background"]
    foreground: str = DRACULA["foreground"]
    comment: str = DRACULA["comment"]
    prompt_color: str = DRACULA["cyan"]  # ❯ color
    assistant_color: str = DRACULA["foreground"]  # ● color (green only for tool calls)
    separator_color: str = DRACULA["comment"]  # ─── color
    titlebar_color: str = DRACULA["black"]  # title bar background
    selection_color: str = DRACULA["current_line"]  # highlighted line background

    # Font
    font_path: str = field(default_factory=_default_font_path)
    font_size: int = 16

    # Terminal dimensions (characters)
    cols: int = 80
    rows: int = 30

    # Pixel padding around terminal content
    padding: int = 28
    padding_bottom: int = 36  # extra space at bottom for the prompt line

    @classmethod
    def from_color_scheme(cls, name: str, **overrides) -> TerminalTheme:
        """Create a theme from a named color scheme.

        Raises ValueError if the scheme is not found.
        """
        scheme = get_color_scheme(name)
        if scheme is None:
            # Find close matches for the error message
            all_names = list_color_schemes()
            lower = name.lower()
            close = [n for n in all_names if lower in n.lower() or n.lower() in lower]
            if not close:
                # Try substring matching on words
                words = lower.split()
                close = [n for n in all_names if any(w in n.lower() for w in words)][:5]
            hint = f"  Similar: {', '.join(close)}" if close else ""
            raise ValueError(
                f"Unknown color scheme: {name!r}. "
                f"Use list_color_schemes() to see all {len(all_names)} available.{hint}"
            )

        fg = scheme["foreground"]
        bg = scheme["background"]
        kwargs = {
            "background": bg,
            "foreground": fg,
            "titlebar_color": scheme.get("ansi_0", bg),
            "selection_color": _highlight_for_background(bg),
            "comment": scheme.get("ansi_8", scheme.get("ansi_0", "#6272A4")),
            "prompt_color": scheme.get("ansi_6", "#8BE9FD"),
            "assistant_color": fg,
            "separator_color": scheme.get("ansi_8", scheme.get("ansi_0", "#6272A4")),
            **overrides,
        }
        return cls(**kwargs)

    @staticmethod
    @functools.lru_cache(maxsize=32)
    def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        """Convert hex color string to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )
