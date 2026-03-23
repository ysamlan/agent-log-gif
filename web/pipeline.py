"""Web pipeline: runs the agent-log-gif rendering pipeline inside Pyodide.

Called by worker.js with JSONL content and options set as global variables.
Stubs out CLI-only dependencies (click, __init__.py) so the pure-Python
pipeline submodules can be imported directly.
"""

import sys
from pathlib import Path
from types import ModuleType

# ---------------------------------------------------------------------------
# 1. Stub the top-level package so Python never executes the real __init__.py
#    (which imports click, httpx, questionary at module level).
# ---------------------------------------------------------------------------
pkg = ModuleType("agent_log_gif")
pkg.__path__ = ["/home/pyodide/agent_log_gif"]
pkg.__package__ = "agent_log_gif"
sys.modules["agent_log_gif"] = pkg

# Also stub the backends sub-package since its __init__ is harmless but
# we want a clean path.
backends_pkg = ModuleType("agent_log_gif.backends")
backends_pkg.__path__ = ["/home/pyodide/agent_log_gif/backends"]
backends_pkg.__package__ = "agent_log_gif.backends"
sys.modules["agent_log_gif.backends"] = backends_pkg

# Stub click (only used by _optimize_with_gifsicle, which we bypass)
click_mod = ModuleType("click")
click_mod.echo = lambda *a, **kw: None
click_mod.ClickException = type("ClickException", (Exception,), {})
sys.modules["click"] = click_mod

# ---------------------------------------------------------------------------
# 2. Now we can safely import the pipeline submodules.
# ---------------------------------------------------------------------------
import js  # noqa: E402

# JS interop — set by worker.js before running this script
# js_report_status(message: str) — status update
# js_report_progress(current: int, total: int) — frame progress
# jsonl_content: str — the JSONL file content
# render_options: dict — {chrome, speed, max_turns, color_scheme, show, shimmer}
from pyodide.ffi import to_js  # noqa: E402

from agent_log_gif.animator import generate_frames  # noqa: E402
from agent_log_gif.backends.gif import save_gif  # noqa: E402
from agent_log_gif.chrome import (  # noqa: E402
    MAC_TRAFFIC_COLORS,
    ChromeStyle,
)
from agent_log_gif.parsers import parse_session_file  # noqa: E402
from agent_log_gif.renderer import TerminalRenderer  # noqa: E402
from agent_log_gif.spinner import (  # noqa: E402
    CLAUDE_SHIMMER,
    CODEX_SHIMMER,
    SPINNER_COLOR,
    TOOL_DONE_COLOR,
    blend_rgb,
)
from agent_log_gif.theme import TerminalTheme  # noqa: E402
from agent_log_gif.timeline import (  # noqa: E402
    EventType,
    loglines_to_timeline,
    parse_show_flag,
    visible_events,
)

DEFAULT_MAX_TURNS = 10


def _palette_seed_colors(theme, transcript_source, shimmer, canvas_bg=None):
    """Compute seed colors that must appear in the GIF palette."""
    seeds = set()
    for attr in (
        "background",
        "foreground",
        "comment",
        "prompt_color",
        "assistant_color",
        "separator_color",
        "titlebar_color",
        "selection_color",
    ):
        seeds.add(theme.hex_to_rgb(getattr(theme, attr)))
    if canvas_bg:
        seeds.add(theme.hex_to_rgb(canvas_bg))
    seeds.add(theme.hex_to_rgb(SPINNER_COLOR))
    seeds.add(theme.hex_to_rgb(TOOL_DONE_COLOR))
    for c in MAC_TRAFFIC_COLORS:
        seeds.add(theme.hex_to_rgb(c))
    if shimmer:
        profiles = [(SPINNER_COLOR, CLAUDE_SHIMMER)]
        if transcript_source == "codex":
            profiles.append((theme.comment, CODEX_SHIMMER))
        for base, profile in profiles:
            base_rgb = theme.hex_to_rgb(base)
            highlight_rgb = theme.hex_to_rgb(profile.highlight_color)
            for i in range(16):
                t = (i / 15) * profile.max_intensity
                seeds.add(blend_rgb(base_rgb, highlight_rgb, t))
    return list(seeds)


def render_gif(jsonl_content, options):
    """Main entry point: JSONL string + options dict -> JS {gif, frames}.

    Mirrors _session_to_media() from __init__.py but adapted for Pyodide:
    stubs click, uses parallel=1, smaller terminal defaults (72x16 vs 80x18),
    and lower default max turns (10 vs CLI's 20) to keep wasm render times
    manageable.
    """
    chrome = options.get("chrome", "mac")
    speed = options.get("speed", 1.0)
    max_turns = options.get("max_turns", DEFAULT_MAX_TURNS)
    color_scheme = options.get("color_scheme", "")
    show = options.get("show", "")
    shimmer = options.get("shimmer", True)

    session_path = Path("/tmp/session.jsonl")
    session_path.write_text(jsonl_content)

    show_extras = None
    if show:
        show_extras = parse_show_flag(show)

    js.js_report_status("Parsing session...")
    data = parse_session_file(session_path)
    events = loglines_to_timeline(data.get("loglines", []))
    events = visible_events(events, show=show_extras)

    if not events:
        raise ValueError("No visible messages found in session.")

    turn_groups = []
    current_turn = []
    for event in events:
        if event.type == EventType.USER_MESSAGE and current_turn:
            turn_groups.append(current_turn)
            current_turn = []
        current_turn.append(event)
    if current_turn:
        turn_groups.append(current_turn)

    if max_turns and len(turn_groups) > max_turns:
        turn_groups = turn_groups[:max_turns]
    selected_events = [e for group in turn_groups for e in group]
    shown_turns = len(turn_groups)

    js.js_report_status(
        f"Rendering {shown_turns} turn{'s' if shown_turns != 1 else ''}..."
    )

    # Smaller terminal than CLI defaults to reduce frame size in wasm
    theme_kwargs = {"cols": 72, "rows": 16}
    if color_scheme:
        try:
            theme = TerminalTheme.from_color_scheme(color_scheme, **theme_kwargs)
        except ValueError:
            theme = TerminalTheme(**theme_kwargs)
    else:
        theme = TerminalTheme(**theme_kwargs)
    chrome_style = ChromeStyle(chrome.lower())
    renderer = TerminalRenderer(theme, chrome=chrome_style)

    transcript_source = data.get("transcript_source", "claude")
    anim_kwargs = {}
    if speed != 1.0:
        anim_kwargs["speed"] = speed
    if not shimmer:
        anim_kwargs["shimmer"] = False

    def _report_progress(done, total):
        js.js_report_progress(done, total)

    frames = generate_frames(
        selected_events,
        renderer=renderer,
        transcript_source=transcript_source,
        on_turn=_report_progress,
        on_progress=_report_progress,
        parallel=1,
        **anim_kwargs,
    )

    if not frames:
        raise ValueError("No frames generated.")

    js.js_report_status(f"Encoding GIF ({len(frames)} frames)...")

    output_path = Path("/tmp/output.gif")
    save_gif(
        frames,
        output_path,
        palette_seeds=_palette_seed_colors(theme, transcript_source, shimmer),
        gifsicle=False,
    )

    result = {"gif": to_js(output_path.read_bytes()), "frames": len(frames)}
    return to_js(result, dict_converter=js.Object.fromEntries)
