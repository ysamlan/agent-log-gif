"""Playwright configuration for e2e tests."""

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Configure Chromium launch args for the current environment.

    Auto-detects whether a GPU is available and disables GPU compositing
    if not (common in containers / CI).
    """
    chrome_args = []

    if not Path("/dev/dri").exists():
        chrome_args.append("--disable-gpu")

    # Allow overriding the executable path (e.g. for system Chromium)
    args = {}
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    if executable:
        args["executable_path"] = executable

    if chrome_args:
        args["args"] = chrome_args

    return args
