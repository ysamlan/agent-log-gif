"""End-to-end tests for the static web UI.

Uses pytest-playwright to test the web UI served locally.
Run with: just test-web
"""

import subprocess
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SESSION = Path(__file__).parent / "sample_session.jsonl"
WEB_DIR = Path(__file__).parent.parent / "web"
PORT = 8089


@pytest.fixture(scope="module")
def web_server():
    """Build the web bundle and serve it for the test session."""
    # Build the zip bundle
    subprocess.run(
        ["bash", "scripts/build_web.sh"],
        cwd=WEB_DIR.parent,
        check=True,
        capture_output=True,
    )

    # Start the server
    proc = subprocess.Popen(
        ["python3", "-m", "http.server", str(PORT)],
        cwd=WEB_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)  # let it bind
    yield f"http://localhost:{PORT}"
    proc.terminate()
    proc.wait()


@pytest.fixture()
def page(browser, web_server):
    """Create a fresh page pointing at the local server."""
    p = browser.new_page()
    p.goto(web_server)
    p.wait_for_load_state("networkidle")
    yield p
    p.close()


# ---------------------------------------------------------------------------
# Page load
# ---------------------------------------------------------------------------


class TestPageLoad:
    def test_title_and_dropzone_visible(self, page: Page):
        expect(page.locator("h1")).to_contain_text("agent-log-gif")
        expect(page.locator(".dropzone")).to_be_visible()

    def test_upload_tab_active_by_default(self, page: Page):
        expect(page.locator(".tab-btn.active")).to_contain_text("Upload file")
        expect(page.locator("#panel-upload")).to_be_visible()
        expect(page.locator("#panel-compose")).not_to_be_visible()

    def test_options_panel_collapsed_by_default(self, page: Page):
        details = page.locator("details.options")
        assert details.get_attribute("open") is None

    def test_options_panel_expands(self, page: Page):
        page.locator("details.options summary").click()
        expect(page.locator("#opt-chrome")).to_be_visible()
        expect(page.locator("#opt-speed")).to_be_visible()
        expect(page.locator("#opt-turns")).to_be_visible()
        expect(page.locator("#opt-scheme")).to_be_visible()

    def test_footer_attribution(self, page: Page):
        footer = page.locator("footer")
        expect(footer).to_contain_text("Pyodide")
        expect(footer).to_contain_text("gifsicle")
        expect(footer).to_contain_text("Lucide")
        expect(footer).to_contain_text("GPL v2")


# ---------------------------------------------------------------------------
# Tab switching
# ---------------------------------------------------------------------------


class TestTabSwitching:
    def test_switch_to_compose_and_back(self, page: Page):
        page.locator("[data-tab='compose']").click()
        expect(page.locator("#panel-upload")).not_to_be_visible()
        expect(page.locator("#panel-compose")).to_be_visible()

        page.locator("[data-tab='upload']").click()
        expect(page.locator("#panel-upload")).to_be_visible()
        expect(page.locator("#panel-compose")).not_to_be_visible()


# ---------------------------------------------------------------------------
# Compose tab
# ---------------------------------------------------------------------------


class TestCompose:
    @pytest.fixture(autouse=True)
    def _open_compose(self, page: Page):
        page.locator("[data-tab='compose']").click()

    def test_starts_with_two_rows(self, page: Page):
        rows = page.locator(".compose-row")
        expect(rows).to_have_count(2)
        expect(rows.nth(0).locator("select")).to_have_value("user")
        expect(rows.nth(1).locator("select")).to_have_value("assistant")

    def test_add_row_alternates_role(self, page: Page):
        page.locator("#compose-add").click()
        rows = page.locator(".compose-row")
        expect(rows).to_have_count(3)
        # Last was agent, so new should be user
        expect(rows.nth(2).locator("select")).to_have_value("user")

        page.locator("#compose-add").click()
        expect(rows).to_have_count(4)
        expect(rows.nth(3).locator("select")).to_have_value("assistant")

    def test_delete_disabled_at_two_rows(self, page: Page):
        buttons = page.locator(".compose-row-delete")
        expect(buttons.nth(0)).to_be_disabled()
        expect(buttons.nth(1)).to_be_disabled()

    def test_delete_enabled_at_three_rows(self, page: Page):
        page.locator("#compose-add").click()
        buttons = page.locator(".compose-row-delete")
        expect(buttons.nth(0)).to_be_enabled()
        expect(buttons.nth(1)).to_be_enabled()
        expect(buttons.nth(2)).to_be_enabled()

    def test_delete_removes_row(self, page: Page):
        page.locator("#compose-add").click()
        expect(page.locator(".compose-row")).to_have_count(3)

        page.locator(".compose-row-delete").nth(2).click()
        expect(page.locator(".compose-row")).to_have_count(2)
        # Back to 2, buttons disabled again
        expect(page.locator(".compose-row-delete").nth(0)).to_be_disabled()

    def test_generate_empty_shows_error(self, page: Page):
        page.locator("#compose-generate").click()
        expect(page.locator("#error")).to_be_visible()
        expect(page.locator("#error-text")).to_contain_text("at least one message")

    def test_format_dropdown_options(self, page: Page):
        select = page.locator("#compose-format")
        expect(select).to_have_value("claude")
        expect(select.locator("option")).to_have_count(2)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_invalid_file_type(self, page: Page):
        page.evaluate(
            """() => {
            const file = new File(['hello'], 'test.txt', {type: 'text/plain'});
            handleFile(file);
        }"""
        )
        expect(page.locator("#error")).to_be_visible()
        expect(page.locator("#error-text")).to_contain_text(".jsonl or .json")


# ---------------------------------------------------------------------------
# Full pipeline e2e (slow — loads Pyodide)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestGifGeneration:
    """Full pipeline tests. These load Pyodide + Pillow (~10-15s), render
    frames, and run gifsicle.wasm. Use ``pytest -m slow`` to run only these,
    or ``pytest -m 'not slow'`` to skip them.
    """

    def test_upload_generates_gif(self, page: Page):
        jsonl_content = SAMPLE_SESSION.read_text()

        page.evaluate(
            """(content) => {
            const file = new File([content], 'sample_session.jsonl', {type: 'text/plain'});
            handleFile(file);
        }""",
            jsonl_content,
        )

        # Status should appear
        expect(page.locator("#status")).to_be_visible()

        # Wait for result (Pyodide load + render + gifsicle)
        expect(page.locator("#result")).to_be_visible(timeout=180_000)

        # Should have a blob image
        img = page.locator("#result-img")
        expect(img).to_be_visible()
        assert page.locator("#result-img").get_attribute("src").startswith("blob:")

        # Download button should have correct filename
        btn = page.locator("#download-btn")
        expect(btn).to_be_visible()
        assert btn.get_attribute("href").startswith("blob:")
        assert btn.get_attribute("download") == "sample_session.gif"

        # Metadata should show size, frames, gifsicle savings
        meta = page.locator("#result-meta")
        expect(meta).to_contain_text("KB")
        expect(meta).to_contain_text("frames")
        expect(meta).to_contain_text("gifsicle")

    def test_compose_generates_gif(self, page: Page):
        page.locator("[data-tab='compose']").click()

        rows = page.locator(".compose-row")
        rows.nth(0).locator("textarea").fill("What is 2+2?")
        rows.nth(1).locator("textarea").fill("The answer is 4.")

        page.locator("#compose-generate").click()

        expect(page.locator("#status")).to_be_visible()
        expect(page.locator("#result")).to_be_visible(timeout=180_000)

        assert page.locator("#result-img").get_attribute("src").startswith("blob:")
        expect(page.locator("#result-meta")).to_contain_text("frames")
