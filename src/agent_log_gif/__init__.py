"""Convert Claude Code or Codex session logs to animated GIFs."""

import platform
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
    # Get token
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

    # Get org UUID
    if org_uuid is None:
        org_uuid = get_org_uuid_from_config()
        if org_uuid is None:
            raise click.ClickException(
                "Could not find organization UUID in ~/.claude.json. "
                "Provide --org-uuid with your organization UUID."
            )

    return token, org_uuid


@click.group(cls=DefaultGroup, default="local", default_if_no_args=True)
@click.version_option(None, "-v", "--version", package_name="agent-log-gif")
def cli():
    """Convert Claude Code or Codex session logs to animated GIFs."""
    pass


@cli.command("local")
@click.option(
    "--limit",
    default=10,
    help="Maximum number of sessions to show (default: 10)",
)
def local_cmd(limit):
    """Select a local Claude Code session and generate a GIF."""
    from datetime import datetime

    projects_folder = Path.home() / ".claude" / "projects"

    if not projects_folder.exists():
        click.echo(f"Projects folder not found: {projects_folder}")
        click.echo("No local Claude Code sessions available.")
        return

    click.echo("Loading local sessions...")
    results = find_local_sessions(projects_folder, limit=limit)

    if not results:
        click.echo("No local sessions found.")
        return

    # Build choices for questionary
    choices = []
    for filepath, summary in results:
        stat = filepath.stat()
        mod_time = datetime.fromtimestamp(stat.st_mtime)
        size_kb = stat.st_size / 1024
        date_str = mod_time.strftime("%Y-%m-%d %H:%M")
        # Truncate summary if too long
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

    click.echo(f"Selected session: {selected}")
    click.echo("GIF output not yet implemented.")


@cli.command("json")
@click.argument("json_file", type=click.Path())
def json_cmd(json_file):
    """Convert a Claude Code or Codex session JSON/JSONL file to a GIF."""
    # Handle URL input
    if is_url(json_file):
        click.echo(f"Fetching {json_file}...")
        temp_file = fetch_url_to_tempfile(json_file)
        json_file_path = temp_file
    else:
        # Validate that local file exists
        json_file_path = Path(json_file)
        if not json_file_path.exists():
            raise click.ClickException(f"File not found: {json_file}")

    click.echo(f"Session file: {json_file_path}")
    click.echo("GIF output not yet implemented.")


@cli.command("web")
@click.argument("session_id", required=False)
@click.option("--token", help="API access token (auto-detected from keychain on macOS)")
@click.option(
    "--org-uuid", help="Organization UUID (auto-detected from ~/.claude.json)"
)
@click.option(
    "--repo",
    help="GitHub repo (owner/name). Filters session list.",
)
def web_cmd(session_id, token, org_uuid, repo):
    """Fetch a web session from the Claude API and generate a GIF."""
    try:
        token, org_uuid = resolve_credentials(token, org_uuid)
    except click.ClickException:
        raise

    # If no session ID provided, show interactive picker
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

        # Enrich sessions with repo information (extracted from session metadata)
        sessions = enrich_sessions_with_repos(sessions)

        # Filter by repo if specified
        if repo:
            sessions = filter_sessions_by_repo(sessions, repo)
            if not sessions:
                raise click.ClickException(f"No sessions found for repo: {repo}")

        # Build choices for questionary
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

    # Fetch the session
    click.echo(f"Fetching session {session_id}...")
    try:
        fetch_session(token, org_uuid, session_id)
    except httpx.HTTPStatusError as e:
        raise click.ClickException(
            f"API request failed: {e.response.status_code} {e.response.text}"
        )
    except httpx.RequestError as e:
        raise click.ClickException(f"Network error: {e}")

    click.echo("GIF output not yet implemented.")


def main():
    cli()
