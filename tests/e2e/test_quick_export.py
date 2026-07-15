"""Opt-in browser E2E checks for the isolated Quick Export container."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def quick_page():
    url = os.environ.get("FOURD_QUICK_URL", "").strip()
    if not url:
        pytest.skip("Set FOURD_QUICK_URL to a running isolated Quick Export page")

    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(accept_downloads=True)
        page.set_default_timeout(300_000)
        try:
            yield page, url
        finally:
            browser.close()


def test_quick_preview_and_browser_download(quick_page, tmp_path):
    page, url = quick_page
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    page.goto(url, wait_until="load")
    page.locator("#btn-export").wait_for(state="visible")
    page.wait_for_function(
        "() => !document.querySelector('#btn-export').disabled",
        timeout=300_000,
    )
    assert "Ready" in page.locator("#status-text").inner_text()
    page.frame_locator("#preview-iframe").locator("canvas").wait_for(
        state="visible", timeout=120_000
    )

    page.locator("#f-title").fill("Browser Quick audit")
    with page.expect_download(timeout=300_000) as download_info:
        page.locator("#btn-export").click()
    download = download_info.value
    downloaded = tmp_path / download.suggested_filename
    download.save_as(downloaded)

    html = downloaded.read_text(encoding="utf-8")
    assert downloaded.stat().st_size > 100_000
    assert "/state/figures/" not in html
    assert "../state/figures/" not in html
    assert page_errors == []


def test_retained_standalone_html_opens_with_interactive_canvas(quick_page):
    standalone = os.environ.get("FOURD_QUICK_STANDALONE", "").strip()
    if not standalone:
        pytest.skip("Set FOURD_QUICK_STANDALONE to the retained HTML artifact")

    page, _ = quick_page
    path = Path(standalone).resolve()
    assert path.is_file()

    page.goto(path.as_uri(), wait_until="load")
    page.frame_locator('iframe[srcdoc]').locator("canvas").wait_for(
        state="visible", timeout=120_000
    )
