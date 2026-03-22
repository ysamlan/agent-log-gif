"""Tests for README demo generation settings."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "generate_demos.py"


def _load_generate_demos_module():
    spec = importlib.util.spec_from_file_location("generate_demos", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_main_readme_demo_uses_rounded_mac_and_slower_timing():
    module = _load_generate_demos_module()
    main_demo = module.DEMOS[0]
    args = main_demo["args"]

    assert main_demo["output"].name == "demo.avif"

    chrome_index = args.index("--chrome")
    assert args[chrome_index + 1] == "mac"

    format_index = args.index("--format")
    assert args[format_index + 1] == "avif"

    speed_index = args.index("--speed")
    assert args[speed_index + 1] == "1.0"

    spinner_index = args.index("--spinner-time")
    assert args[spinner_index + 1] == "1.0"


def test_main_readme_demo_uses_white_canvas_background():
    module = _load_generate_demos_module()
    main_demo = module.DEMOS[0]
    args = main_demo["args"]

    canvas_index = args.index("--canvas-bg")
    assert args[canvas_index + 1] == "#FFFFFF"


def test_readme_embeds_avif_demo():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "![demo](demo.avif)" in readme


def test_demo_session_uses_reserved_example_email():
    session = (ROOT / "scripts" / "demo_session.jsonl").read_text(encoding="utf-8")
    assert "user@gmail.com" not in session
    assert "user@example.com" in session


def test_windows_codex_demo_uses_avif_output():
    module = _load_generate_demos_module()
    windows_demo = module.DEMOS[1]
    args = windows_demo["args"]

    assert windows_demo["output"].name == "demo-windows-codex.avif"
    format_index = args.index("--format")
    assert args[format_index + 1] == "avif"


def test_readme_embeds_avif_windows_demo():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "![windows-codex](docs/demo-windows-codex.avif)" in readme
