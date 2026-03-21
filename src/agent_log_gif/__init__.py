"""Convert Claude Code or Codex session logs to animated GIFs."""

import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import click
import httpx
import questionary
from click_default_group import DefaultGroup

from agent_log_gif.analysis import (  # noqa: F401 - re-exported for backward compat
    COMMIT_PATTERN,
    GITHUB_REPO_PATTERN,
    LONG_TEXT_THRESHOLD,
    analyze_conversation,
    detect_github_repo,
    enrich_sessions_with_repos,
    extract_repo_from_session,
    filter_sessions_by_repo,
    format_tool_stats,
    is_tool_result_message,
)
from agent_log_gif.parsers import (  # noqa: F401 - re-exported for backward compat
    _extract_codex_message_texts,
    _extract_codex_reasoning_summary,
    _get_codex_jsonl_summary,
    _is_codex_setup_text,
    _is_codex_transport_text,
    _parse_codex_jsonl_file,
    _parse_codex_tool_arguments,
    _parse_jsonl_file,
    extract_text_from_content,
    get_transcript_label,
    is_codex_jsonl,
    parse_session_file,
    read_first_jsonl_object,
    truncate_text,
)
from agent_log_gif.session import (  # noqa: F401 - re-exported for backward compat
    _get_jsonl_summary,
    find_all_sessions,
    find_local_sessions,
    format_session_for_display,
    get_project_display_name,
    get_session_summary,
)
from agent_log_gif.web import (  # noqa: F401 - re-exported for backward compat
    ANTHROPIC_VERSION,
    API_BASE_URL,
    CredentialsError,
    fetch_session,
    fetch_sessions,
    get_access_token_from_keychain,
    get_api_headers,
    get_org_uuid_from_config,
)

# Default turn cap for GIF output
DEFAULT_MAX_TURNS = 20

# GIF files larger than this skip gifsicle optimization.
# Frame diffing produces ~4x smaller intermediates, so 200 MB covers very
# long sessions that would have been skipped before.
GIFSICLE_SIZE_LIMIT_MB = 200

# Warn about GIF size when session exceeds this many turns
GIF_TURN_WARNING_THRESHOLD = 10

_MEDIA_KWARG_NAMES = (
    "fmt",
    "music",
    "loop_music",
    "font",
    "chrome",
    "canvas_bg",
    "color_scheme",
    "cols",
    "rows",
    "font_size",
    "show",
    "speed",
    "spinner_time",
    "thinking_verbs",
    "shimmer",
    "colors",
    "parallel",
    "gifsicle",
    "lossy",
)


def _collect_media_kwargs(turns, **kwargs):
    """Build the shared kwargs dict for _session_to_media from Click params."""
    result = {k: kwargs[k] for k in _MEDIA_KWARG_NAMES}
    result["turns"] = _parse_turns(turns) if turns else None
    # parallel=None from CLI means "auto" → pass 0 to generate_frames
    if result.get("parallel") is None:
        result["parallel"] = 0
    return result


def _normalize_hex_color(value: str | None, flag_name: str) -> str | None:
    """Normalize a CLI hex color to #RRGGBB."""
    if value is None:
        return None
    normalized = value.strip()
    if normalized.startswith("#"):
        normalized = normalized[1:]
    if not re.fullmatch(r"[0-9a-fA-F]{6}", normalized):
        raise click.ClickException(f"{flag_name} must be a hex color like #FFFFFF")
    return f"#{normalized.upper()}"


def _palette_seed_colors(theme, transcript_source, shimmer, canvas_bg=None):
    """Compute seed colors that must appear in the GIF palette.

    Returns a list of RGB tuples covering theme colors, special UI colors,
    and shimmer gradient stops so the global palette includes them even if
    they don't appear in the first frame.
    """
    from agent_log_gif.chrome import MAC_TRAFFIC_COLORS
    from agent_log_gif.spinner import (
        CLAUDE_SHIMMER,
        CODEX_SHIMMER,
        SPINNER_COLOR,
        TOOL_DONE_COLOR,
        blend_rgb,
    )

    seeds = set()
    # All theme colors
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
    # Canvas background (for rounded mac chrome)
    if canvas_bg:
        seeds.add(theme.hex_to_rgb(canvas_bg))
    # Special colors
    seeds.add(theme.hex_to_rgb(SPINNER_COLOR))
    seeds.add(theme.hex_to_rgb(TOOL_DONE_COLOR))
    for c in MAC_TRAFFIC_COLORS:
        seeds.add(theme.hex_to_rgb(c))
    # Shimmer gradient samples (16 stops per profile)
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


def _session_to_media(
    session_path,
    output_path,
    turns=None,
    fmt="gif",
    music=None,
    loop_music=False,
    font=None,
    chrome="mac",
    canvas_bg=None,
    color_scheme=None,
    cols=None,
    rows=None,
    font_size=None,
    show=None,
    speed=None,
    spinner_time=None,
    thinking_verbs=None,
    shimmer=True,
    colors=None,
    parallel=0,
    gifsicle=True,
    lossy=None,
):
    """Core pipeline: session file → animated media."""
    from agent_log_gif.animator import generate_frames
    from agent_log_gif.backends.gif import save_gif
    from agent_log_gif.chrome import ChromeStyle
    from agent_log_gif.renderer import TerminalRenderer
    from agent_log_gif.theme import TerminalTheme
    from agent_log_gif.timeline import (
        EventType,
        loglines_to_timeline,
        parse_show_flag,
        visible_events,
    )

    # Validate format + audio combination
    if music and fmt != "mp4":
        raise click.ClickException("--music is only supported with --format mp4")

    # Parse --show flag
    show_extras = None
    if show:
        try:
            show_extras = parse_show_flag(show)
        except ValueError as e:
            raise click.ClickException(str(e))

    _check_optional_tools(fmt)

    click.echo(f"Parsing {session_path}...")
    data = parse_session_file(session_path)
    loglines = data.get("loglines", [])

    events = loglines_to_timeline(loglines)
    events = visible_events(events, show=show_extras)

    if not events:
        raise click.ClickException("No visible messages found in session.")

    # Group events into turns (user message + following assistant messages)
    turn_groups = []
    current_turn = []
    for event in events:
        if event.type == EventType.USER_MESSAGE and current_turn:
            turn_groups.append(current_turn)
            current_turn = []
        current_turn.append(event)
    if current_turn:
        turn_groups.append(current_turn)

    total_turns = len(turn_groups)

    # Apply turn selection
    if turns is not None:
        if isinstance(turns, tuple):
            start, end = turns
            turn_groups = turn_groups[start - 1 : end]
        else:
            turn_groups = turn_groups[:turns]
    elif total_turns > DEFAULT_MAX_TURNS:
        click.echo(
            f"Session has {total_turns} turns. Showing first {DEFAULT_MAX_TURNS}. "
            f"Use --turns to adjust."
        )
        turn_groups = turn_groups[:DEFAULT_MAX_TURNS]

    # Flatten back to event list
    selected_events = [e for group in turn_groups for e in group]
    shown_turns = len(turn_groups)

    if fmt == "gif" and shown_turns > GIF_TURN_WARNING_THRESHOLD:
        click.echo(
            f"Heads up: {shown_turns} turns will produce a large GIF. "
            f"Consider --format mp4 or --turns {GIF_TURN_WARNING_THRESHOLD} "
            f"for a smaller file.",
            err=True,
        )

    click.echo(
        f"Generating animation ({shown_turns} turn{'s' if shown_turns != 1 else ''})..."
    )
    theme_kwargs = {}
    if font:
        font_path = Path(font)
        if not font_path.exists():
            raise click.ClickException(f"Font file not found: {font}")
        theme_kwargs["font_path"] = str(font_path)
    if cols is not None:
        theme_kwargs["cols"] = cols
    if rows is not None:
        theme_kwargs["rows"] = rows
    if font_size is not None:
        theme_kwargs["font_size"] = font_size
    if color_scheme:
        try:
            theme = TerminalTheme.from_color_scheme(color_scheme, **theme_kwargs)
        except ValueError as e:
            raise click.ClickException(str(e))
    else:
        theme = TerminalTheme(**theme_kwargs)
    chrome_style = ChromeStyle(chrome.lower())
    canvas_bg = _normalize_hex_color(canvas_bg, "--canvas-bg")
    renderer = TerminalRenderer(
        theme,
        chrome=chrome_style,
        canvas_background=canvas_bg,
    )

    transcript_source = data.get("transcript_source", "claude")
    anim_kwargs = {}
    if speed is not None:
        anim_kwargs["speed"] = speed
    if spinner_time is not None:
        anim_kwargs["spinner_time"] = spinner_time
    if thinking_verbs is not None:
        anim_kwargs["thinking_verbs"] = [v.strip() for v in thinking_verbs.split(",")]
    if not shimmer:
        anim_kwargs["shimmer"] = False

    bar_width = 20

    def _report_turn(turn: int, total: int) -> None:
        if total <= 1:
            return
        filled = bar_width * turn // total
        bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
        click.echo(f"\r  {bar} {turn}/{total}", nl=turn == total)

    frames = generate_frames(
        selected_events,
        renderer=renderer,
        transcript_source=transcript_source,
        on_turn=_report_turn,
        parallel=parallel,
        **anim_kwargs,
    )

    if not frames:
        raise click.ClickException("No frames generated.")

    click.echo(f"Writing {output_path}...")

    if fmt == "gif":
        save_gif(
            frames,
            output_path,
            size_limit_mb=GIFSICLE_SIZE_LIMIT_MB,
            colors=colors,
            palette_seeds=_palette_seed_colors(
                theme, transcript_source, shimmer, canvas_bg
            ),
            gifsicle=gifsicle,
            lossy=lossy,
        )
    elif fmt == "mp4":
        from agent_log_gif.backends.video import save_mp4

        save_mp4(frames, output_path)

        if music:
            from agent_log_gif.backends.audio import mix_audio

            # Mix audio into a temp file, then replace
            mixed_path = Path(str(output_path) + ".mixed.mp4")
            mix_audio(output_path, music, mixed_path, loop=loop_music)
            mixed_path.replace(output_path)
            click.echo(f"Audio mixed from {music}")
    elif fmt == "avif":
        from agent_log_gif.backends.video import save_avif

        save_avif(frames, output_path)
    else:
        raise click.ClickException(f"Unknown format: {fmt}")

    size_kb = Path(output_path).stat().st_size / 1024
    click.echo(f"Done! {output_path} ({size_kb:.0f} KB, {len(frames)} frames)")


def _parse_turns(turns_str):
    """Parse --turns value into int or (start, end) tuple.

    Examples: "5" → 5, "3,8" → (3, 8)
    """
    if "," in turns_str:
        parts = turns_str.split(",", 1)
        return (int(parts[0]), int(parts[1]))
    return int(turns_str)


def is_url(path):
    """Check if a path is a URL (starts with http:// or https://)."""
    return path.startswith("http://") or path.startswith("https://")


def fetch_url_to_tempfile(url):
    """Fetch a URL and save to a temporary file.

    Returns the Path to the temporary file.
    Raises click.ClickException on network errors.
    """
    try:
        response = httpx.get(url, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
    except httpx.RequestError as e:
        raise click.ClickException(f"Failed to fetch URL: {e}")
    except httpx.HTTPStatusError as e:
        raise click.ClickException(
            f"Failed to fetch URL: {e.response.status_code} {e.response.reason_phrase}"
        )

    # Determine file extension from URL
    url_path = url.split("?")[0]  # Remove query params
    if url_path.endswith(".jsonl"):
        suffix = ".jsonl"
    elif url_path.endswith(".json"):
        suffix = ".json"
    else:
        suffix = ".jsonl"  # Default to JSONL

    # Extract a name from the URL for the temp file
    url_name = Path(url_path).stem or "session"

    temp_dir = Path(tempfile.gettempdir())
    temp_file = temp_dir / f"claude-url-{url_name}{suffix}"
    temp_file.write_text(response.text, encoding="utf-8")
    return temp_file


def resolve_credentials(token, org_uuid):
    """Resolve token and org_uuid from arguments or auto-detect.

    Returns (token, org_uuid) tuple.
    Raises click.ClickException if credentials cannot be resolved.
    """
    if token is None:
        token = get_access_token_from_keychain()
        if token is None:
            if platform.system() == "Darwin":
                raise click.ClickException(
                    "Could not retrieve access token from macOS keychain. "
                    "Make sure you are logged into Claude Code, or provide --token."
                )
            else:
                raise click.ClickException(
                    "On non-macOS platforms, you must provide --token with your access token."
                )

    if org_uuid is None:
        org_uuid = get_org_uuid_from_config()
        if org_uuid is None:
            raise click.ClickException(
                "Could not find organization UUID in ~/.claude.json. "
                "Provide --org-uuid with your organization UUID."
            )

    return token, org_uuid


def _list_sessions(source: str) -> None:
    """List recent sessions for the given source (claude or codex)."""
    for filepath, summary, label in _gather_sessions(source, limit=20):
        _echo_session(filepath, summary)


def _search_sessions(keyword: str, source: str | None) -> None:
    """Search sessions by keyword across the given source(s)."""
    sources = [source] if source else ["claude", "codex"]
    found = 0

    for src in sources:
        folder = _session_folder(src)
        if not folder or not folder.exists():
            continue

        for filepath in folder.glob("**/*.jsonl"):
            if filepath.name.startswith("agent-"):
                continue
            try:
                needle = keyword.lower()
                matched = False
                with open(filepath, encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if needle in line.lower():
                            matched = True
                            break
                if not matched:
                    continue
                summary = get_session_summary(filepath)
                if summary == "(no summary)":
                    continue
                _echo_session(filepath, summary)
                found += 1
                if found >= 20:
                    return
            except OSError:
                continue

    if found == 0:
        click.echo(f'No sessions found matching "{keyword}".')


def _session_folder(source: str) -> Path | None:
    """Return the session folder path for a source, or None."""
    if source == "claude":
        return Path.home() / ".claude" / "projects"
    if source == "codex":
        return Path.home() / ".codex" / "sessions"
    return None


def _gather_sessions(source: str, limit: int = 20):
    """Yield (filepath, summary, label) tuples for a source."""
    folder = _session_folder(source)
    label = "Claude Code" if source == "claude" else "Codex"

    if not folder or not folder.exists():
        click.echo(f"No {label} sessions found ({folder} does not exist).")
        return

    results = find_local_sessions(folder, limit=limit)
    if not results:
        click.echo(f"No {label} sessions found.")
        return

    click.echo(f"{label} sessions ({len(results)} most recent):\n")
    for filepath, summary in results:
        yield filepath, summary, label


def _echo_session(filepath: Path, summary: str) -> None:
    """Print a single session entry with date, size, summary, and path."""
    from datetime import datetime

    stat = filepath.stat()
    mod_time = datetime.fromtimestamp(stat.st_mtime)
    size_kb = stat.st_size / 1024
    date_str = mod_time.strftime("%Y-%m-%d %H:%M")
    if len(summary) > 60:
        summary = summary[:57] + "..."
    click.echo(f"  {date_str}  {size_kb:5.0f} KB  {summary}")
    click.echo(f"    {filepath}")


def _check_optional_tools(fmt: str) -> None:
    """Warn or error about missing optional tools based on output format.

    GIF: warn if gifsicle is missing (output works, just larger).
    MP4: error if ffmpeg is missing (cannot proceed).
    AVIF: ffmpeg must be present and include a supported AV1 encoder.
    """
    import shutil

    if fmt in ("mp4", "avif") and not shutil.which("ffmpeg"):
        raise click.ClickException(
            "ffmpeg is required for video output but was not found on PATH.\n"
            "Install it: apt install ffmpeg (Linux), brew install ffmpeg (macOS),\n"
            "or download from https://ffmpeg.org/download.html"
        )
    if fmt == "avif":
        from agent_log_gif.backends.video import _select_av1_encoder

        if _select_av1_encoder() is None:
            raise click.ClickException(
                "AVIF output requires an ffmpeg build with an AV1 encoder.\n"
                "Supported encoders: libsvtav1 (preferred) or libaom-av1.\n"
                "Check with: ffmpeg -encoders | rg 'av1|svt|aom'"
            )

    if fmt == "gif" and not shutil.which("gifsicle"):
        click.echo(
            "Tip: install gifsicle for 80-85% smaller GIFs. "
            "See https://www.lcdf.org/gifsicle/",
            err=True,
        )


def _tool_status() -> str:
    """Return status lines showing optional tools and detected sessions."""
    import shutil

    gifsicle = "installed" if shutil.which("gifsicle") else "not found"
    ffmpeg = "installed" if shutil.which("ffmpeg") else "not found"
    lines = [f"  gifsicle: {gifsicle}  |  ffmpeg: {ffmpeg}"]

    sources = []
    for src, label in [("claude", "Claude Code"), ("codex", "Codex")]:
        folder = _session_folder(src)
        if folder and folder.exists():
            sources.append(label)
    if sources:
        lines.append(f"  Sessions: {', '.join(sources)}")
    else:
        lines.append("  Sessions: none detected")

    return "\n".join(lines)


@click.group(cls=DefaultGroup, default="local", default_if_no_args=True)
@click.version_option(None, "-v", "--version", package_name="agent-log-gif")
def cli():
    """Convert Claude Code or Codex session logs to animated GIFs.

    \b
    Optional tools:
    """
    pass


class _LazyHelp:
    """Defer tool-status computation until help text is actually displayed."""

    def __init__(self, base: str):
        self._base = base
        self._full: str | None = None

    def __str__(self) -> str:
        if self._full is None:
            self._full = self._base.rstrip() + "\n" + _tool_status()
        return self._full

    # Click checks truthiness and calls format_help which uses str()
    def __bool__(self) -> bool:
        return True


cli.help = _LazyHelp(cli.help)


def _media_options(fn):
    """Shared Click options for commands that produce animated media."""
    for decorator in reversed(
        [
            click.option(
                "--format",
                "fmt",
                type=click.Choice(["gif", "mp4", "avif"], case_sensitive=False),
                default="gif",
                help="Output format (default: gif). mp4/avif require ffmpeg.",
            ),
            click.option(
                "--turns",
                type=str,
                default=None,
                help="Turn selection: N for first N turns, M,N for turns M through N.",
            ),
            click.option(
                "--music",
                type=click.Path(exists=True),
                default=None,
                help="Music track to mix into video (mp4 only).",
            ),
            click.option(
                "--loop-music",
                is_flag=True,
                default=False,
                help="Loop the music track if shorter than the video.",
            ),
            click.option(
                "--font",
                type=click.Path(exists=True),
                default=None,
                help="Path to a TTF font file (default: bundled DejaVu Sans Mono).",
            ),
            click.option(
                "--chrome",
                type=click.Choice(
                    ["none", "mac", "mac-square", "windows", "linux"],
                    case_sensitive=False,
                ),
                default="mac",
                help="Window chrome style (default: mac).",
            ),
            click.option(
                "--canvas-bg",
                default=None,
                help="Outer canvas color outside rounded macOS corners (#RRGGBB).",
            ),
            click.option(
                "--color-scheme",
                default=None,
                help="Terminal color scheme (e.g. Dracula, 'Gruvbox Dark', Nord).",
            ),
            click.option(
                "--cols",
                type=int,
                default=None,
                help="Terminal width in columns (default: 80).",
            ),
            click.option(
                "--rows",
                type=int,
                default=None,
                help="Terminal height in rows (default: 30).",
            ),
            click.option(
                "--font-size",
                type=int,
                default=None,
                help="Font size in pixels (default: 16).",
            ),
            click.option(
                "--show",
                default=None,
                help="Extra content to show: tools, calls, thinking, all (comma-separated).",
            ),
            click.option(
                "--speed",
                type=float,
                default=None,
                help="Typing speed multiplier (default: 1.0, higher = faster).",
            ),
            click.option(
                "--spinner-time",
                type=float,
                default=None,
                help="Spinner duration multiplier (default: 1.0, lower = shorter).",
            ),
            click.option(
                "--thinking-verbs",
                default=None,
                help="Comma-separated spinner verbs (e.g. Reticulating,Sleeping).",
            ),
            click.option(
                "--shimmer/--no-shimmer",
                default=True,
                help="Enable/disable loading line shimmer effect (default: on).",
            ),
            click.option(
                "--colors",
                type=int,
                default=None,
                help="GIF palette size, 2-256 (default: 256). Try 128 for smaller files.",
            ),
            click.option(
                "--parallel",
                type=int,
                default=None,
                help="Parallel rendering workers (0=auto, 1=off, 2+=explicit). "
                "Auto-detects from CPU count by default.",
            ),
            click.option(
                "--gifsicle/--no-gifsicle",
                default=True,
                help="Enable/disable gifsicle post-processing (default: on). "
                "Disabling produces larger GIFs but skips the gifsicle step.",
            ),
            click.option(
                "--lossy",
                type=int,
                default=None,
                help="Lossy tolerance (0-200, default: off). Treats pixels that "
                "changed by less than this per-channel value as unchanged, "
                "producing smaller files. Try 30 for a good size/quality balance.",
            ),
        ]
    ):
        fn = decorator(fn)
    return fn


@cli.command("local")
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    help="Output file path. Defaults to temp file.",
)
@_media_options
@click.option(
    "--open/--no-open",
    "open_browser",
    default=None,
    help="Open the generated file in your default viewer.",
)
@click.option(
    "--limit",
    default=10,
    help="Maximum number of sessions to show (default: 10)",
)
def local_cmd(
    output,
    fmt,
    turns,
    music,
    loop_music,
    font,
    chrome,
    canvas_bg,
    color_scheme,
    cols,
    rows,
    font_size,
    show,
    speed,
    spinner_time,
    thinking_verbs,
    shimmer,
    colors,
    parallel,
    gifsicle,
    lossy,
    open_browser,
    limit,
):
    """Select a local Claude Code or Codex session and generate a GIF."""
    from datetime import datetime

    claude_folder = Path.home() / ".claude" / "projects"
    codex_folder = Path.home() / ".codex" / "sessions"
    has_claude = claude_folder.exists()
    has_codex = codex_folder.exists()

    if not has_claude and not has_codex:
        click.echo("No local sessions found.")
        click.echo(f"  Claude Code: {claude_folder} (not found)")
        click.echo(f"  Codex:       {codex_folder} (not found)")
        return

    # Determine which source(s) to search
    source = None
    if has_claude and has_codex:
        source = questionary.select(
            "Session source:",
            choices=[
                questionary.Choice("Claude Code", value="claude"),
                questionary.Choice("Codex", value="codex"),
            ],
        ).ask()
        if source is None:
            return
    elif has_claude:
        source = "claude"
    else:
        source = "codex"

    folder = claude_folder if source == "claude" else codex_folder
    click.echo(f"Loading {source.title()} sessions...")
    results = find_local_sessions(folder, limit=limit)

    if not results:
        click.echo(f"No {source.title()} sessions found.")
        return

    # Build choices for questionary
    choices = []
    for filepath, summary in results:
        stat = filepath.stat()
        mod_time = datetime.fromtimestamp(stat.st_mtime)
        size_kb = stat.st_size / 1024
        date_str = mod_time.strftime("%Y-%m-%d %H:%M")
        if len(summary) > 50:
            summary = summary[:47] + "..."
        display = f"{date_str}  {size_kb:5.0f} KB  {summary}"
        choices.append(questionary.Choice(title=display, value=filepath))

    selected = questionary.select(
        "Select a session to convert:",
        choices=choices,
    ).ask()

    if selected is None:
        click.echo("No session selected.")
        return

    # Interactive prompts for options not provided via CLI flags
    if fmt == "gif" and not output:
        fmt = questionary.select(
            "Output format:",
            choices=[
                questionary.Choice("GIF (default)", value="gif"),
                questionary.Choice("MP4 (requires ffmpeg)", value="mp4"),
                questionary.Choice("AVIF (requires ffmpeg)", value="avif"),
            ],
            default="GIF (default)",
        ).ask()
        if fmt is None:
            return

    if chrome == "mac":
        chrome = questionary.select(
            "Window chrome:",
            choices=[
                questionary.Choice("macOS (default)", value="mac"),
                questionary.Choice("macOS square corners", value="mac-square"),
                questionary.Choice("Windows 11", value="windows"),
                questionary.Choice("Linux / GNOME", value="linux"),
                questionary.Choice("None", value="none"),
            ],
            default="macOS (default)",
        ).ask()
        if chrome is None:
            return

    if show is None:
        show = questionary.select(
            "Content to show:",
            choices=[
                questionary.Choice("Conversation only (default)", value=""),
                questionary.Choice("+ Tool call names", value="calls"),
                questionary.Choice("+ Tool calls and results", value="tools"),
                questionary.Choice("Everything (tools + thinking)", value="all"),
            ],
            default="Conversation only (default)",
        ).ask()
        if show is None:
            return
        show = show or None

    # Determine output path
    if output is None:
        output = Path(tempfile.gettempdir()) / f"{selected.stem}.{fmt}"
        should_open = open_browser if open_browser is not None else True
    else:
        output = Path(output)
        should_open = open_browser if open_browser is not None else False

    _session_to_media(
        selected,
        output,
        **_collect_media_kwargs(
            turns,
            fmt=fmt,
            music=music,
            loop_music=loop_music,
            font=font,
            chrome=chrome,
            canvas_bg=canvas_bg,
            color_scheme=color_scheme,
            cols=cols,
            rows=rows,
            font_size=font_size,
            show=show,
            speed=speed,
            spinner_time=spinner_time,
            thinking_verbs=thinking_verbs,
            shimmer=shimmer,
            colors=colors,
            parallel=parallel,
            gifsicle=gifsicle,
            lossy=lossy,
        ),
    )

    if should_open:
        _open_file(output)


@cli.command("json")
@click.argument("json_file", type=click.Path(), required=False)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    help="Output file path. Defaults to <input-stem>.<format>.",
)
@click.option(
    "--list",
    "list_sessions",
    type=click.Choice(["claude", "codex"], case_sensitive=False),
    default=None,
    help="List recent sessions (claude or codex) instead of converting.",
)
@_media_options
@click.option(
    "--open/--no-open",
    "open_browser",
    default=False,
    help="Open the generated file in your default viewer.",
)
def json_cmd(
    json_file,
    output,
    list_sessions,
    fmt,
    turns,
    music,
    loop_music,
    font,
    chrome,
    canvas_bg,
    color_scheme,
    cols,
    rows,
    font_size,
    show,
    speed,
    spinner_time,
    thinking_verbs,
    shimmer,
    colors,
    parallel,
    gifsicle,
    lossy,
    open_browser,
):
    """Convert a Claude Code or Codex session JSON/JSONL file to a GIF."""
    if list_sessions:
        _list_sessions(list_sessions)
        return

    if json_file is None:
        raise click.ClickException(
            "Missing argument 'JSON_FILE'. Use --list=claude or --list=codex to browse sessions."
        )

    # Handle URL input
    if is_url(json_file):
        click.echo(f"Fetching {json_file}...")
        json_file_path = fetch_url_to_tempfile(json_file)
    else:
        json_file_path = Path(json_file)
        if not json_file_path.exists():
            raise click.ClickException(f"File not found: {json_file}")

    # Determine output path
    if output is None:
        output = Path(json_file_path.stem + f".{fmt}")

    _session_to_media(
        json_file_path,
        output,
        **_collect_media_kwargs(
            turns,
            fmt=fmt,
            music=music,
            loop_music=loop_music,
            font=font,
            chrome=chrome,
            canvas_bg=canvas_bg,
            color_scheme=color_scheme,
            cols=cols,
            rows=rows,
            font_size=font_size,
            show=show,
            speed=speed,
            spinner_time=spinner_time,
            thinking_verbs=thinking_verbs,
            shimmer=shimmer,
            colors=colors,
            parallel=parallel,
            gifsicle=gifsicle,
            lossy=lossy,
        ),
    )

    if open_browser:
        _open_file(output)


@cli.command("web")
@click.argument("session_id", required=False)
@click.option("--token", help="API access token (auto-detected from keychain on macOS)")
@click.option(
    "--org-uuid", help="Organization UUID (auto-detected from ~/.claude.json)"
)
@click.option("--repo", help="GitHub repo (owner/name). Filters session list.")
def web_cmd(session_id, token, org_uuid, repo):
    """Fetch a web session from the Claude API and generate a GIF.

    NOTE: This command is best-effort/unsupported due to changes in the
    unofficial API.
    """
    try:
        token, org_uuid = resolve_credentials(token, org_uuid)
    except click.ClickException:
        raise

    if session_id is None:
        try:
            sessions_data = fetch_sessions(token, org_uuid)
        except httpx.HTTPStatusError as e:
            raise click.ClickException(
                f"API request failed: {e.response.status_code} {e.response.text}"
            )
        except httpx.RequestError as e:
            raise click.ClickException(f"Network error: {e}")

        sessions = sessions_data.get("data", [])
        if not sessions:
            raise click.ClickException("No sessions found.")

        sessions = enrich_sessions_with_repos(sessions)

        if repo:
            sessions = filter_sessions_by_repo(sessions, repo)
            if not sessions:
                raise click.ClickException(f"No sessions found for repo: {repo}")

        choices = []
        for s in sessions:
            sid = s.get("id", "unknown")
            display = format_session_for_display(s)
            choices.append(questionary.Choice(title=display, value=sid))

        selected = questionary.select(
            "Select a session to import:",
            choices=choices,
        ).ask()

        if selected is None:
            raise click.ClickException("No session selected.")

        session_id = selected

    click.echo(f"Fetching session {session_id}...")
    try:
        fetch_session(token, org_uuid, session_id)
    except httpx.HTTPStatusError as e:
        raise click.ClickException(
            f"API request failed: {e.response.status_code} {e.response.text}"
        )
    except httpx.RequestError as e:
        raise click.ClickException(f"Network error: {e}")

    click.echo("GIF output for web sessions not yet implemented.")


@cli.command("search")
@click.argument("keyword")
@click.option(
    "--source",
    type=click.Choice(["claude", "codex"], case_sensitive=False),
    default=None,
    help="Search only Claude Code or Codex sessions. Default: search both.",
)
def search_cmd(keyword, source):
    """Search sessions by keyword.

    Searches session content (user messages, assistant responses, tool output)
    for the given keyword across Claude Code and/or Codex sessions.
    """
    _search_sessions(keyword, source)


def _open_file(path):
    """Open a file with the system default viewer."""
    path = str(path)
    if sys.platform == "darwin":
        subprocess.run(["open", path])
    elif sys.platform == "win32":
        # start treats first quoted arg as window title; empty "" avoids that
        subprocess.run(f'start "" "{path}"', shell=True)
    else:
        subprocess.run(["xdg-open", path])


def main():
    cli()
