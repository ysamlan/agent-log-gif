#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""Fetch a Lucide icon SVG by name from the official repository.

Usage:
    uv run get_icon.py <icon-name>            # Print SVG to stdout
    uv run get_icon.py --search <term>        # Search icons by name substring
    uv run get_icon.py <icon-name> --size 16  # Override width/height attributes

Sparse-clones the Lucide icons directory on first use (shallow, cached at /tmp/lucide-icons/).
"""

import argparse
import subprocess
import sys
from pathlib import Path

CACHE_DIR = Path("/tmp/lucide-icons")
ICONS_DIR = CACHE_DIR / "icons"
REPO_URL = "https://github.com/lucide-icons/lucide.git"


def ensure_icons():
    """Sparse-checkout just the icons/ directory if not cached."""
    if ICONS_DIR.exists() and any(ICONS_DIR.glob("*.svg")):
        return

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "git",
            "clone",
            "--depth=1",
            "--filter=blob:none",
            "--sparse",
            REPO_URL,
            str(CACHE_DIR),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(CACHE_DIR), "sparse-checkout", "set", "icons"],
        check=True,
        capture_output=True,
    )


def search_icons(term):
    """Return icon names containing the search term."""
    ensure_icons()
    term_lower = term.lower()
    return sorted(
        p.stem for p in ICONS_DIR.glob("*.svg") if term_lower in p.stem.lower()
    )


def get_icon_svg(name):
    """Return the raw SVG content for an icon."""
    ensure_icons()
    svg_path = ICONS_DIR / f"{name}.svg"
    if not svg_path.exists():
        return None
    return svg_path.read_text()


def main():
    parser = argparse.ArgumentParser(description="Fetch Lucide icon SVGs")
    parser.add_argument("name", nargs="?", help="Icon name (e.g. 'package-open')")
    parser.add_argument("--search", "-s", help="Search icons by name substring")
    parser.add_argument("--size", type=int, default=None, help="Override width/height")
    args = parser.parse_args()

    if args.search:
        matches = search_icons(args.search)
        if not matches:
            print(f"No icons matching '{args.search}'", file=sys.stderr)
            sys.exit(1)
        for name in matches:
            print(name)
        return

    if not args.name:
        parser.print_help()
        sys.exit(1)

    svg = get_icon_svg(args.name)
    if svg is None:
        matches = search_icons(args.name)
        print(f"Icon '{args.name}' not found.", file=sys.stderr)
        if matches:
            print(f"Did you mean: {', '.join(matches[:10])}", file=sys.stderr)
        sys.exit(1)

    if args.size:
        svg = svg.replace('width="24"', f'width="{args.size}"')
        svg = svg.replace('height="24"', f'height="{args.size}"')

    print(svg, end="")


if __name__ == "__main__":
    main()
