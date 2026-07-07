"""Regression tests for the Insert Figure overlay wiring."""
from __future__ import annotations

from pathlib import Path


def test_insert_figure_overlay_targets_codemirror_editor():
    path = Path(__file__).parent.parent / "dashboard" / "static" / "js" / "insert-figure-overlay.js"
    text = path.read_text(encoding="utf-8")

    assert "state.codeEditor" in text
    assert "getCodeEditor" in text
    assert "getAceEditor" not in text
    assert "Ace editor not found" not in text


def test_insert_figure_overlay_is_labeled_openfoam_only():
    path = Path(__file__).parent.parent / "dashboard" / "static" / "js" / "insert-figure-overlay.js"
    text = path.read_text(encoding="utf-8")

    assert "Insert OpenFOAM Figure" in text
    assert "OpenFOAM <strong>case folder</strong>" in text
    assert "manual shortcodes" in text


def test_insert_figure_overlay_shows_rendered_preview_thumbnail():
    path = Path(__file__).parent.parent / "dashboard" / "static" / "js" / "insert-figure-overlay.js"
    text = path.read_text(encoding="utf-8")

    # The rendered PNG is served from /state/figures/<fig_id>.png; the overlay
    # must show it as a thumbnail using the fig_id from the finish response.
    assert "/state/figures/" in text
    assert "data.fig_id" in text
    assert "showPreview" in text

