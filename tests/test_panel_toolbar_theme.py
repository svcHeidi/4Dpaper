"""Tests for the shared panel toolbar theme."""
from pathlib import Path


def _shortcodes_source() -> str:
    return (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()


def test_panel_toolbar_uses_shared_theme_classes():
    content = _shortcodes_source()
    assert "plb-toolbar" in content
    assert "class=\"plb-play\"" in content
    assert "class=\"plb-lock\"" in content
    assert "class=\"plb-transport\"" in content


def test_panel_toolbar_is_play_only_without_top_seek_slider():
    content = _shortcodes_source()
    assert 'id="plb-play-' in content
    assert 'id="plb-time-' not in content
    assert 'id="plb-time-val-' not in content
    assert 'var sl=document.getElementById("plb-time-"+PID);' not in content
