"""Real end-to-end tests for the compile / export-HTML / export-PDF pipeline.

`test_compile_plugin.py` only unit-tests pure string/path helpers, so the actual
render path (``quarto render`` + WeasyPrint) had zero coverage — it could break
completely while the suite stayed green. That is exactly what happened: the HTML
and PDF exports silently produced nothing in a real deployment while every test
passed.

These tests run the *real* pipeline against a minimal-but-real Quarto project
(reusing the repo's 4dpaper extension and render profiles) and assert that the
produced artifacts are genuinely valid. They are skipped only when the required
tooling (Quarto / WeasyPrint) is unavailable, and are wired to run in CI and in
the container image where that tooling is present.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("tornado")
weasyprint = pytest.importorskip("weasyprint")

_QUARTO = shutil.which("quarto")
pytestmark = pytest.mark.skipif(_QUARTO is None, reason="quarto executable not installed")

_REPO = Path(__file__).parent.parent

# Minimal but real paper: prose + heading + fenced code block. No figures and no
# jupyter kernel, so the render is fast and deterministic while still exercising
# the full Quarto → HTML → WeasyPrint path the dashboard uses.
_MINIMAL_QMD = """\
---
title: "Export Pipeline Smoke Paper"
author: "Test Harness"
format:
  html:
    toc: true
---

# Introduction

This paragraph is a unique sentinel: PIPELINE_SENTINEL_TEXT.

## A code block

```python
def hello():
    return "world"
```

Some **bold** and *italic* text to force real HTML rendering.
"""


@pytest.fixture()
def mini_project(tmp_path, monkeypatch):
    """A real, self-contained Quarto project wired to the 4dpaper extension."""
    proj = tmp_path / "proj"
    proj.mkdir()
    # Reuse the real extension + render profiles so we test the true pipeline.
    (proj / "_extensions").symlink_to(_REPO / "_extensions")
    for cfg in ("_quarto.yml", "_quarto-apphtml.yml", "_quarto-paperview.yml"):
        shutil.copy(_REPO / cfg, proj / cfg)
    (proj / "main.qmd").write_text(_MINIMAL_QMD, encoding="utf-8")
    (proj / "_output").mkdir()
    (proj / "state" / "figures").mkdir(parents=True)
    # The compile plugin resolves paths against PROJECT_ROOT; point it here so
    # the validators inspect this hermetic project rather than the real repo.
    monkeypatch.setenv("PROJECT_ROOT", str(proj))
    return proj


def _render(qmd: Path, fmt: str) -> tuple[int, list[str]]:
    from dashboard.utils import run_quarto_render

    log: list[str] = []
    rc = run_quarto_render(qmd, log, fmt)
    return rc, log


def test_compile_html_produces_valid_output(mini_project):
    """`format='html'` must produce a non-empty HTML file containing the content."""
    qmd = mini_project / "main.qmd"
    rc, log = _render(qmd, "html")
    assert rc == 0, "quarto html render failed:\n" + "\n".join(log[-25:])

    out = mini_project / "_output" / "main.html"
    assert out.exists(), "compile did not produce _output/main.html"
    text = out.read_text(encoding="utf-8")
    assert len(text) > 500
    assert "PIPELINE_SENTINEL_TEXT" in text
    assert "<html" in text.lower()


def test_export_standalone_html_is_valid_and_self_contained(mini_project):
    """`format='html-export'` must pass the standalone validator and embed assets."""
    from dashboard.compile_plugin import _validate_standalone_html_output

    qmd = mini_project / "main.qmd"
    rc, log = _render(qmd, "html-export")
    assert rc == 0, "quarto html-export render failed:\n" + "\n".join(log[-25:])

    out = mini_project / "_output" / "main-standalone.html"
    assert out.exists(), "export did not produce _output/main-standalone.html"
    text = out.read_text(encoding="utf-8")
    assert len(text) > 500
    assert "PIPELINE_SENTINEL_TEXT" in text
    # Must not leave unresolved figure placeholders or app-served asset refs.
    _validate_standalone_html_output(out)


def test_export_pdf_produces_valid_pdf(mini_project):
    """`format='paperview'` + WeasyPrint must produce a real, multi-byte PDF."""
    from dashboard.compile_plugin import (
        _rewrite_paperview_asset_urls_for_pdf,
        _validate_paperview_html_output,
    )

    qmd = mini_project / "main.qmd"
    rc, log = _render(qmd, "paperview")
    assert rc == 0, "quarto paperview render failed:\n" + "\n".join(log[-25:])

    html_path = mini_project / "_output" / "main-paperview.html"
    assert html_path.exists(), "export did not produce _output/main-paperview.html"
    _validate_paperview_html_output(html_path)

    html_text = _rewrite_paperview_asset_urls_for_pdf(
        html_path.read_text(encoding="utf-8")
    )
    pdf_bytes = weasyprint.HTML(
        string=html_text, base_url=str(html_path.parent)
    ).write_pdf()

    assert pdf_bytes[:5] == b"%PDF-", "output is not a PDF"
    assert b"%%EOF" in pdf_bytes[-1024:], "PDF is truncated / missing EOF"
    assert len(pdf_bytes) > 1000, "PDF is implausibly small (likely blank)"


def test_export_pdf_via_export_handler_streams_pdf(mini_project, monkeypatch):
    """The ExportHandler wiring must stream real PDF bytes end-to-end.

    Exercises the handler the frontend calls (`POST /api/export`) — reloaded so
    it binds to the hermetic PROJECT_ROOT — with a stubbed request object, to
    catch regressions in the handler's render→validate→WeasyPrint→stream path
    (not just the helpers).
    """
    import importlib

    import dashboard.compile_plugin as cp
    cp = importlib.reload(cp)

    handler = cp.ExportHandler.__new__(cp.ExportHandler)

    written = bytearray()
    headers: dict[str, str] = {}
    status = {"code": 200}

    class _Req:
        body = b"{}"
        headers = {"X-Forwarded-For": "127.0.0.1"}
        remote_ip = "127.0.0.1"

    handler.request = _Req()
    handler.check_auth = lambda: True
    handler.set_status = lambda c: status.__setitem__("code", c)
    handler.set_header = lambda k, v: headers.__setitem__(k, v)
    handler.write = lambda b: written.extend(b if isinstance(b, (bytes, bytearray)) else str(b).encode())

    import asyncio

    asyncio.run(handler.post())

    assert status["code"] == 200, f"export handler failed: {bytes(written)[:400]!r}"
    assert headers.get("Content-Type") == "application/pdf"
    assert bytes(written)[:5] == b"%PDF-", "handler did not stream a PDF"
