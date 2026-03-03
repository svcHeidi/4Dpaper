"""Tests for _extensions/4dpaper/4dpaper.py helper functions."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

# Make the extension importable
sys.path.insert(0, str(Path(__file__).parent.parent / "_extensions" / "4dpaper"))
import importlib
import importlib.util


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestParseShortcodes:
    def test_finds_single_shortcode(self):
        mod = _load_4dpaper()
        text = '{{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}'
        result = mod.parse_shortcodes(text)
        assert len(result) == 1
        assert result[0]["id"] == "fig-vm"
        assert result[0]["src"] == "case.foam"
        assert result[0]["field"] == "Vm"

    def test_finds_multiple_shortcodes(self):
        mod = _load_4dpaper()
        text = (
            '{{< 4d-image src="a.foam" field="Vm" id="fig-a" >}}\n'
            'some prose\n'
            '{{< 4d-image src="b.foam" field="activationTime" id="fig-b" time="last" >}}'
        )
        result = mod.parse_shortcodes(text)
        assert len(result) == 2
        assert result[1]["time"] == "last"

    def test_returns_empty_for_no_shortcodes(self):
        mod = _load_4dpaper()
        result = mod.parse_shortcodes("# Just a heading\n\nSome prose.")
        assert result == []

    def test_skips_shortcode_missing_required_keys(self):
        mod = _load_4dpaper()
        # Missing 'id'
        text = '{{< 4d-image src="case.foam" field="Vm" >}}'
        result = mod.parse_shortcodes(text)
        assert result == []

    def test_defaults_time_to_mid(self):
        mod = _load_4dpaper()
        text = '{{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}'
        result = mod.parse_shortcodes(text)
        assert result[0]["time"] == "mid"

    def test_ignores_shortcode_in_fenced_code_block(self):
        mod = _load_4dpaper()
        text = (
            "Here is an example:\n\n"
            "```\n"
            '{{< 4d-image src="case.foam" field="Vm" id="fig-example" >}}\n'
            "```\n\n"
            "The real figure:\n"
            '{{< 4d-image src="real.foam" field="Vm" id="fig-real" >}}'
        )
        result = mod.parse_shortcodes(text)
        assert len(result) == 1
        assert result[0]["id"] == "fig-real"

    def test_handles_single_quoted_attributes(self):
        mod = _load_4dpaper()
        text = "{{< 4d-image src='case.foam' field='Vm' id='fig-vm' >}}"
        result = mod.parse_shortcodes(text)
        assert len(result) == 1
        assert result[0]["src"] == "case.foam"
        assert result[0]["id"] == "fig-vm"


class TestIsCacheValid:
    def test_returns_false_when_fig_missing(self, tmp_path):
        mod = _load_4dpaper()
        src = tmp_path / "case.foam"
        src.write_text("")
        fig = tmp_path / "fig-vm.html"
        assert mod.is_cache_valid(fig, src) is False

    def test_returns_true_when_fig_newer_than_src(self, tmp_path):
        mod = _load_4dpaper()
        src = tmp_path / "case.foam"
        src.write_text("")
        time.sleep(0.05)
        fig = tmp_path / "fig-vm.html"
        fig.write_text("<html></html>")
        assert mod.is_cache_valid(fig, src) is True

    def test_returns_false_when_src_newer_than_fig(self, tmp_path):
        mod = _load_4dpaper()
        fig = tmp_path / "fig-vm.html"
        fig.write_text("<html></html>")
        time.sleep(0.05)
        src = tmp_path / "case.foam"
        src.write_text("")
        assert mod.is_cache_valid(fig, src) is False

    def test_returns_true_when_src_missing(self, tmp_path):
        mod = _load_4dpaper()
        fig = tmp_path / "fig-vm.html"
        fig.write_text("<html></html>")
        src = tmp_path / "no_such_file.foam"
        assert mod.is_cache_valid(fig, src) is True

    def test_stale_when_camera_newer_than_png(self, tmp_path):
        mod = _load_4dpaper()
        import os, time as _time
        now = _time.time()
        src = tmp_path / "case.foam"
        src.write_text("")
        fig = tmp_path / "fig.png"
        fig.write_text("")
        cam = tmp_path / "camera_fig.json"
        cam.write_text("{}")
        # Set src and fig older than cam — guaranteed distinct mtimes
        os.utime(src, (now - 2, now - 2))
        os.utime(fig, (now - 1, now - 1))
        os.utime(cam, (now, now))
        assert mod.is_cache_valid(fig, src, camera_path=cam) is False

    def test_valid_when_png_newer_than_camera(self, tmp_path):
        mod = _load_4dpaper()
        import os, time as _time
        now = _time.time()
        src = tmp_path / "case.foam"
        src.write_text("")
        cam = tmp_path / "camera_fig.json"
        cam.write_text("{}")
        fig = tmp_path / "fig.png"
        fig.write_text("")
        # Set src and cam older than fig — guaranteed distinct mtimes
        os.utime(src, (now - 2, now - 2))
        os.utime(cam, (now - 1, now - 1))
        os.utime(fig, (now, now))
        assert mod.is_cache_valid(fig, src, camera_path=cam) is True

    def test_valid_when_camera_file_absent(self, tmp_path):
        mod = _load_4dpaper()
        import os, time as _time
        now = _time.time()
        src = tmp_path / "case.foam"
        src.write_text("")
        fig = tmp_path / "fig.png"
        fig.write_text("")
        # Set src older than fig
        os.utime(src, (now - 1, now - 1))
        os.utime(fig, (now, now))
        cam = tmp_path / "nonexistent_camera.json"
        assert mod.is_cache_valid(fig, src, camera_path=cam) is True


class TestGenerateHtmlFigure:
    def test_creates_html_file(self, tmp_path):
        """Smoke test: verify generate_html_figure creates a non-empty .html file."""
        mod = _load_4dpaper()
        case_path = Path(
            "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam"
        )
        if not case_path.exists():
            pytest.skip("Niederer case not available")

        out = tmp_path / "fig-vm.html"
        mod.generate_html_figure(
            src_path=case_path,
            field="Vm",
            time_spec="mid",
            output_path=out,
        )
        assert out.exists(), "Output HTML file was not created"
        assert out.stat().st_size > 1000, "Output HTML is suspiciously small"
        content = out.read_text()
        assert "<html" in content.lower() or "<!DOCTYPE" in content.lower() or "vtk" in content.lower() or "script" in content.lower()
