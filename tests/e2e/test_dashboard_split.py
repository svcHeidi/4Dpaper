"""E2E: split gutters show resize cursor and dragging changes pane width (pixel check)."""
from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def _dashboard_root() -> Path:
    env = os.environ.get("FOURDPAPERS_DASHBOARD_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_http_ok(url: str, timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            time.sleep(0.25)
    raise RuntimeError(f"server did not respond at {url}: {last_err}")


@pytest.fixture(scope="module")
def dashboard_e2e():
    if os.environ.get("PLAYWRIGHT_E2E", "").strip().lower() not in ("1", "true", "yes"):
        pytest.skip("Set PLAYWRIGHT_E2E=1 to run dashboard E2E tests")

    pytest.importorskip("playwright.sync_api")

    root = _dashboard_root()
    app = root / "dashboard" / "app.py"
    if not app.is_file():
        pytest.skip(f"No dashboard/app.py under {root} — set FOURDPAPERS_DASHBOARD_ROOT")

    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "_output").mkdir(parents=True, exist_ok=True)

    port = _free_port()
    url = f"http://127.0.0.1:{port}/"

    py = Path(__file__).resolve().parent.parent.parent / ".venv" / "bin" / "python"
    if not py.is_file():
        import sys

        py = Path(sys.executable)

    static = root / "dashboard" / "static"
    cmd = [
        str(py),
        "-m",
        "panel",
        "serve",
        str(app),
        "--plugins",
        "dashboard.plugins",
        "--static-dirs",
        f"output={root / '_output'}",
        f"assets={static}",
        f"state={root / 'state'}",
        "--port",
        str(port),
        "--allow-websocket-origin",
        f"127.0.0.1:{port}",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env["BROWSER"] = "none"
    proc = subprocess.Popen(
        cmd,
        cwd=str(root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_http_ok(url, timeout_s=90.0)
    except Exception:
        proc.terminate()
        err = proc.stderr.read() if proc.stderr else ""
        pytest.fail(f"panel serve failed to start: {err[:4000]}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(90_000)
        try:
            yield page, url
        finally:
            browser.close()
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_split_gutter_cursor_and_drag(dashboard_e2e):
    page, base_url = dashboard_e2e
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(base_url, wait_until="load", timeout=120_000)
    # Persisted widths can clamp the left pane at max so a "grow left" drag is a no-op.
    page.evaluate(
        """() => {
          localStorage.removeItem('4dpapers.pane.leftWidth');
          localStorage.removeItem('4dpapers.pane.rightWidth');
        }"""
    )
    page.reload(wait_until="load", timeout=120_000)

    # Bokeh/Panel paint after WS; gutters are the stable hook (not only #split-status text).
    page.wait_for_selector(
        '[class*="split-gutter--between-left-center"]',
        state="visible",
        timeout=120_000,
    )
    page.wait_for_function("() => window.__splitDone === true", timeout=120_000)

    gutter = page.locator('[class*="split-gutter--between-left-center"]').first
    gutter.wait_for(state="visible", timeout=60_000)
    box = gutter.bounding_box()
    assert box is not None
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2

    # Prefer cursor on the gutter node (child __split_handle may be elementFromPoint target).
    cursor_on_gutter = gutter.evaluate("el => getComputedStyle(el).cursor")
    assert cursor_on_gutter in (
        "ew-resize",
        "col-resize",
        "w-resize",
        "e-resize",
    ), f"expected horizontal resize cursor on gutter, got {cursor_on_gutter!r}"

    cursor_at_point = page.evaluate(
        """([x, y]) => {
          const el = document.elementFromPoint(x, y);
          if (!el) return '';
          return getComputedStyle(el).cursor;
        }""",
        [cx, cy],
    )
    assert cursor_at_point in (
        "ew-resize",
        "col-resize",
        "w-resize",
        "e-resize",
        "auto",
    ), f"unexpected elementFromPoint cursor {cursor_at_point!r}"

    left = page.locator(".pane-left").first
    b0 = left.bounding_box()
    assert b0 is not None
    w0 = b0["width"]

    # Drag the left gutter leftward (shrink explorer) — avoids max-width clamp when already wide.
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx - 45, cy, steps=8)
    page.mouse.up()

    page.wait_for_timeout(400)
    b1 = left.bounding_box()
    assert b1 is not None
    dw = b1["width"] - w0
    assert -55 <= dw <= -20, f"expected ~45px narrower left pane after drag, got Δ={dw}"
