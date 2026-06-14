"""Tests for _extensions/4dpaper/4dpaper.py helper functions."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

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
        text = '{{< 4d-image src="case.foam" field="Vm" >}}'
        result = mod.parse_shortcodes(text)
        assert result == []

    def test_defaults_time_to_mid(self):
        mod = _load_4dpaper()
        text = '{{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}'
        result = mod.parse_shortcodes(text)
        assert result[0]["time"] == "mid"

    def test_parses_fields_attribute(self):
        mod = _load_4dpaper()
        text = '{{< 4d-image src="case.foam" field="Vm" fields="Vm,activationTime" id="fig-vm" >}}'
        result = mod.parse_shortcodes(text)
        assert result[0]["fields"] == "Vm,activationTime"

    def test_defaults_fields_to_empty(self):
        mod = _load_4dpaper()
        text = '{{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}'
        result = mod.parse_shortcodes(text)
        assert result[0]["fields"] == ""

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


class TestParsePanelShortcodes:
    def test_finds_single_panel(self):
        mod = _load_4dpaper()
        text = (
            '{{< 4d-panel id="panel-1" layout="2x2" '
            'src1="a.foam" id1="fig-a" field1="Vm" '
            'src2="b.stl" id2="fig-b" field2="" >}}'
        )
        result = mod.parse_panel_shortcodes(text)
        assert len(result) == 1
        p = result[0]
        assert p["id"] == "panel-1"
        assert p["layout"] == "2x2"
        assert len(p["subfigures"]) == 2
        assert p["subfigures"][0] == {"src": "a.foam", "id": "fig-a", "field": "Vm", "time": "mid", "fields": ""}
        assert p["subfigures"][1] == {"src": "b.stl",  "id": "fig-b", "field": "",   "time": "mid", "fields": ""}

    def test_defaults_height_and_caption(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p" layout="1x1" src1="a.foam" id1="fig-a" field1="" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result[0]["height"] == "800px"
        assert result[0]["caption"] == ""

    def test_reads_custom_height_and_caption(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p" layout="1x1" height="600px" caption="My panel" src1="a.foam" id1="fig-a" field1="" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result[0]["height"] == "600px"
        assert result[0]["caption"] == "My panel"

    def test_reads_time_per_subfigure(self):
        mod = _load_4dpaper()
        text = (
            '{{< 4d-panel id="p" layout="1x2" '
            'src1="a.foam" id1="fig-a" field1="" time1="first" '
            'src2="b.foam" id2="fig-b" field2="" time2="last" >}}'
        )
        result = mod.parse_panel_shortcodes(text)
        subs = result[0]["subfigures"]
        assert subs[0]["time"] == "first"
        assert subs[1]["time"] == "last"

    def test_skips_panel_missing_id(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel layout="1x1" src1="a.foam" id1="fig-a" field1="" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result == []

    def test_skips_panel_with_no_subfigures(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p" layout="1x1" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result == []

    def test_ignores_panel_in_fenced_code_block(self):
        mod = _load_4dpaper()
        text = (
            "```\n"
            '{{< 4d-panel id="p" layout="1x1" src1="a.foam" id1="fig-a" field1="" >}}\n'
            "```\n"
            '{{< 4d-panel id="real" layout="1x1" src1="b.foam" id1="fig-b" field1="" >}}'
        )
        result = mod.parse_panel_shortcodes(text)
        assert len(result) == 1
        assert result[0]["id"] == "real"

    def test_finds_multiple_panels(self):
        mod = _load_4dpaper()
        text = (
            '{{< 4d-panel id="p1" layout="1x1" src1="a.foam" id1="fig-a" field1="" >}}\n'
            '{{< 4d-panel id="p2" layout="2x1" src1="b.stl" id1="fig-b" field1="" src2="c.stl" id2="fig-c" field2="" >}}'
        )
        result = mod.parse_panel_shortcodes(text)
        assert len(result) == 2
        assert result[0]["id"] == "p1"
        assert result[1]["id"] == "p2"
        assert len(result[1]["subfigures"]) == 2


class TestGeneratePanelHtml:
    """generate_panel_html() composes sub-figure HTMLs into a CSS grid."""

    def _make_panel(self, layout="2x1", subfigures=None):
        if subfigures is None:
            subfigures = [
                {"src": "a.foam", "id": "fig-a", "field": "", "time": "mid", "fields": ""},
                {"src": "b.stl",  "id": "fig-b", "field": "", "time": "mid", "fields": ""},
            ]
        return {
            "id": "panel-test",
            "layout": layout,
            "height": "800px",
            "caption": "",
            "subfigures": subfigures,
        }

    def test_creates_composite_html(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None, **kwargs):
            output_path.write_text(f"<html>content-{fig_id}</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            mod.generate_panel_html(self._make_panel(), tmp_path)

        out = tmp_path / "panel-test.html"
        assert out.exists()

    def test_composite_contains_css_grid(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None, **kwargs):
            output_path.write_text("<html>x</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            mod.generate_panel_html(self._make_panel("2x1"), tmp_path)

        html = (tmp_path / "panel-test.html").read_text()
        assert "display:grid" in html
        assert "grid-template-columns:repeat(2,1fr)" in html
        assert "grid-template-rows:repeat(1,1fr)" in html

    def test_composite_contains_re_relay_script(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None, **kwargs):
            output_path.write_text("<html>x</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            mod.generate_panel_html(self._make_panel(), tmp_path)

        html = (tmp_path / "panel-test.html").read_text()
        assert "top.postMessage" in html           # upward relay
        assert "4dpaper-camera-ack" in html        # downward ack relay
        assert "querySelectorAll" in html          # broadcast to child iframes

    def test_composite_contains_subfigure_content(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None, **kwargs):
            output_path.write_text(f"<html>unique-{fig_id}</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            mod.generate_panel_html(self._make_panel(), tmp_path)

        import base64, re
        html = (tmp_path / "panel-test.html").read_text()
        # Content is base64-encoded in data URLs — decode to verify sub-figure content
        b64_chunks = re.findall(r'data:text/html;base64,([A-Za-z0-9+/=]+)', html)
        decoded = [base64.b64decode(b).decode() for b in b64_chunks]
        assert any("unique-fig-a" in d for d in decoded)
        assert any("unique-fig-b" in d for d in decoded)

    def test_composite_html_is_passed_to_signing_hook(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None, **kwargs):
            output_path.write_text("<html>x</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html), patch.object(
            mod, "_maybe_sign_output_html"
        ) as mock_sign:
            mod.generate_panel_html(self._make_panel(), tmp_path)

        mock_sign.assert_called_once_with(tmp_path / "panel-test.html")

    def test_invalid_layout_raises(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None, **kwargs):
            output_path.write_text("<html>x</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            with pytest.raises(ValueError, match="layout"):
                mod.generate_panel_html(self._make_panel("bad"), tmp_path)

    def test_3x1_layout_has_three_columns(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()
        subs = [{"src": f"{i}.stl", "id": f"fig-{i}", "field": "", "time": "mid"} for i in range(3)]

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None, **kwargs):
            output_path.write_text("<html>x</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            mod.generate_panel_html(self._make_panel("3x1", subs), tmp_path)

        html = (tmp_path / "panel-test.html").read_text()
        assert "grid-template-columns:repeat(3,1fr)" in html


class TestGeneratePanelPng:
    """generate_panel_png() composes sub-figure PNGs into a 1920×1080 grid."""

    def _make_panel(self, layout="2x1", n_subs=2):
        return {
            "id": "panel-test",
            "layout": layout,
            "height": "800px",
            "caption": "",
            "subfigures": [
                {"src": f"{i}.stl", "id": f"fig-{i}", "field": "", "time": "mid"}
                for i in range(n_subs)
            ],
        }

    def _fake_png_gen(self, color):
        """Return a side_effect that writes a solid-color 1920×1080 PNG."""
        from PIL import Image
        def _write(src, field, time_spec, output_path, fig_id=None, **kwargs):
            img = Image.new("RGB", (1920, 1080), color=color)
            img.save(str(output_path))
        return _write

    def test_creates_composite_png(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()
        with patch.object(mod, "generate_png_figure", side_effect=self._fake_png_gen("red")):
            mod.generate_panel_png(self._make_panel(), tmp_path)
        assert (tmp_path / "panel-test.png").exists()

    def test_composite_2x1_is_correct_size(self, tmp_path):
        from unittest.mock import patch
        from PIL import Image
        mod = _load_4dpaper()
        # Subfigures are 1920×1080; 2x1 → 2 cols × 1 row = 3840×1080
        with patch.object(mod, "generate_png_figure", side_effect=self._fake_png_gen("blue")):
            mod.generate_panel_png(self._make_panel("2x1", 2), tmp_path)
        img = Image.open(tmp_path / "panel-test.png")
        assert img.size == (1920 * 2, 1080 * 1)

    def test_2x2_layout_produces_correct_size(self, tmp_path):
        from unittest.mock import patch
        from PIL import Image
        mod = _load_4dpaper()
        # Subfigures are 1920×1080; 2x2 → 2 cols × 2 rows = 3840×2160
        with patch.object(mod, "generate_png_figure", side_effect=self._fake_png_gen("green")):
            mod.generate_panel_png(self._make_panel("2x2", 4), tmp_path)
        img = Image.open(tmp_path / "panel-test.png")
        assert img.size == (1920 * 2, 1080 * 2)

    def test_invalid_layout_raises(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()
        with patch.object(mod, "generate_png_figure", side_effect=self._fake_png_gen("red")):
            with pytest.raises(ValueError, match="layout"):
                mod.generate_panel_png(self._make_panel("bad"), tmp_path)


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


class TestParseVideoShortcodes:
    def test_finds_shortcode(self):
        mod = _load_4dpaper()
        text = '{{< 4d-video src="case.foam" field="Vm" fps="10" id="vid-vm" >}}'
        result = mod.parse_video_shortcodes(text)
        assert len(result) == 1
        assert result[0]["id"] == "vid-vm"
        assert result[0]["src"] == "case.foam"
        assert result[0]["field"] == "Vm"

    def test_parses_fps(self):
        mod = _load_4dpaper()
        text = '{{< 4d-video src="case.foam" field="Vm" fps="24" id="vid-vm" >}}'
        result = mod.parse_video_shortcodes(text)
        assert result[0]["fps"] == "24"

    def test_defaults_fps_to_10(self):
        mod = _load_4dpaper()
        text = '{{< 4d-video src="case.foam" field="Vm" id="vid-vm" >}}'
        result = mod.parse_video_shortcodes(text)
        assert result[0]["fps"] == "10"

    def test_defaults_time_to_mid(self):
        mod = _load_4dpaper()
        text = '{{< 4d-video src="case.foam" field="Vm" id="vid-vm" >}}'
        result = mod.parse_video_shortcodes(text)
        assert result[0]["time"] == "mid"

    def test_skips_missing_id(self):
        mod = _load_4dpaper()
        text = '{{< 4d-video src="case.foam" field="Vm" >}}'
        result = mod.parse_video_shortcodes(text)
        assert result == []

    def test_skips_missing_src(self):
        mod = _load_4dpaper()
        text = '{{< 4d-video field="Vm" id="vid-vm" >}}'
        result = mod.parse_video_shortcodes(text)
        assert result == []

    def test_ignores_4d_image_shortcodes(self):
        mod = _load_4dpaper()
        text = (
            '{{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}\n'
            '{{< 4d-video src="case.foam" field="Vm" id="vid-vm" >}}'
        )
        result = mod.parse_video_shortcodes(text)
        assert len(result) == 1
        assert result[0]["id"] == "vid-vm"

    def test_ignores_shortcode_in_fenced_code_block(self):
        mod = _load_4dpaper()
        text = (
            "```\n"
            '{{< 4d-video src="case.foam" field="Vm" id="vid-example" >}}\n'
            "```\n"
            '{{< 4d-video src="real.foam" field="Vm" id="vid-real" >}}'
        )
        result = mod.parse_video_shortcodes(text)
        assert len(result) == 1
        assert result[0]["id"] == "vid-real"

    def test_accepts_single_quoted_attributes(self):
        mod = _load_4dpaper()
        text = "{{< 4d-video src='case.foam' field='Vm' id='vid-vm' >}}"
        result = mod.parse_video_shortcodes(text)
        assert len(result) == 1
        assert result[0]["src"] == "case.foam"


class TestApplyCameraFromDict:
    def test_falls_back_to_isometric_when_none(self):
        mod = _load_4dpaper()

        class MockCam:
            position = None
            focal_point = None
            up = None
            parallel_scale = None
            parallel_projection = False

        class MockPlotter:
            camera = MockCam()
            _isometric_called = False

            def isometric_view(self):
                self._isometric_called = True

        pl = MockPlotter()
        mod._apply_camera_from_dict(pl, "fig-vm", None)
        assert pl._isometric_called

    def test_applies_position_focal_view_up(self):
        mod = _load_4dpaper()

        class MockCam:
            position = None
            focal_point = None
            up = None
            parallel_scale = None
            parallel_projection = False

        class MockPlotter:
            camera = MockCam()
            _isometric_called = False

            def isometric_view(self):
                self._isometric_called = True

        pl = MockPlotter()
        data = {
            "position": [1.0, 2.0, 3.0],
            "focal_point": [0.0, 0.0, 0.0],
            "view_up": [0.0, 1.0, 0.0],
        }
        mod._apply_camera_from_dict(pl, "fig-vm", data)
        assert not pl._isometric_called
        assert pl.camera.position == [1.0, 2.0, 3.0]
        assert pl.camera.focal_point == [0.0, 0.0, 0.0]
        assert pl.camera.up == [0.0, 1.0, 0.0]

    def test_falls_back_on_missing_key(self):
        mod = _load_4dpaper()

        class MockCam:
            position = None
            focal_point = None
            up = None

        class MockPlotter:
            camera = MockCam()
            _isometric_called = False

            def isometric_view(self):
                self._isometric_called = True

        pl = MockPlotter()
        # Missing "view_up" key → should fall back to isometric
        data = {"position": [1.0, 2.0, 3.0], "focal_point": [0.0, 0.0, 0.0]}
        mod._apply_camera_from_dict(pl, "fig-vm", data)
        assert pl._isometric_called


class TestVideoCacheLogic:
    def test_mp4_stale_when_missing(self, tmp_path):
        mod = _load_4dpaper()
        src = tmp_path / "case.foam"
        src.write_text("")
        mp4 = tmp_path / "vid-vm-video.mp4"
        assert mod.is_cache_valid(mp4, src) is False

    def test_mp4_valid_when_newer_than_src(self, tmp_path):
        mod = _load_4dpaper()
        import os
        import time as _time
        now = _time.time()
        src = tmp_path / "case.foam"
        src.write_text("")
        mp4 = tmp_path / "vid-vm-video.mp4"
        mp4.write_bytes(b"")
        os.utime(src, (now - 1, now - 1))
        os.utime(mp4, (now, now))
        assert mod.is_cache_valid(mp4, src) is True

    def test_mp4_stale_when_camera_newer(self, tmp_path):
        mod = _load_4dpaper()
        import os
        import time as _time
        now = _time.time()
        src = tmp_path / "case.foam"
        src.write_text("")
        mp4 = tmp_path / "vid-vm-video.mp4"
        mp4.write_bytes(b"")
        cam = tmp_path / "camera_vid-vm.json"
        cam.write_text("{}")
        os.utime(src, (now - 2, now - 2))
        os.utime(mp4, (now - 1, now - 1))
        os.utime(cam, (now, now))
        assert mod.is_cache_valid(mp4, src, camera_path=cam) is False

    def test_frame_stale_when_missing(self, tmp_path):
        mod = _load_4dpaper()
        src = tmp_path / "case.foam"
        src.write_text("")
        frame = tmp_path / "vid-vm-frame.png"
        assert mod.is_cache_valid(frame, src) is False


class TestGenerateVideoFigure:
    def test_creates_mp4_frame_and_html(self, tmp_path):
        mod = _load_4dpaper()
        case_path = Path(
            "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam"
        )
        if not case_path.exists():
            pytest.skip("Niederer case not available")

        mp4_path = tmp_path / "vid-vm-video.mp4"
        frame_path = tmp_path / "vid-vm-frame.png"
        html_path = tmp_path / "vid-vm-video.html"
        preview_path = tmp_path / "vid-vm-preview.html"

        mod.generate_video_figure(
            src_path=case_path,
            field="Vm",
            fps=5,
            time_spec="mid",
            mp4_path=mp4_path,
            frame_path=frame_path,
            video_html_path=html_path,
            fig_id="vid-vm",
            preview_html_path=preview_path,
        )

        assert mp4_path.exists(), "MP4 not created"
        assert mp4_path.stat().st_size > 1000, "MP4 suspiciously small"
        assert frame_path.exists(), "Frame PNG not created"
        assert frame_path.stat().st_size > 500, "Frame PNG suspiciously small"
        assert html_path.exists(), "Video HTML not created"
        content = html_path.read_text()
        assert "data:video/mp4;base64," in content, "HTML does not contain base64 MP4"
        assert "<video" in content, "HTML does not contain <video> element"
        assert preview_path.exists(), "Preview HTML not created"

    def test_mp4_is_valid_h264(self, tmp_path):
        mod = _load_4dpaper()
        case_path = Path(
            "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam"
        )
        if not case_path.exists():
            pytest.skip("Niederer case not available")

        try:
            import imageio.v3 as iio
        except ImportError:
            pytest.skip("imageio.v3 not available")

        try:
            import av  # pyav backend required for plugin="pyav"
        except ImportError:
            pytest.skip("pyav not installed — run: pip install imageio[pyav]")

        mp4_path = tmp_path / "vid-vm-video.mp4"
        frame_path = tmp_path / "vid-vm-frame.png"
        html_path = tmp_path / "vid-vm-video.html"

        mod.generate_video_figure(
            src_path=case_path,
            field="Vm",
            fps=5,
            time_spec="mid",
            mp4_path=mp4_path,
            frame_path=frame_path,
            video_html_path=html_path,
            fig_id="vid-vm",
        )

        props = iio.improps(str(mp4_path), plugin="pyav")
        assert props.n_frames > 0, "MP4 has no frames"


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


class TestVideoCameraViewModal:
    """Integration tests for camera sync in generated video HTML (foam case required)."""

    def test_preview_html_has_camera_sync(self, tmp_path):
        mod = _load_4dpaper()
        case_path = Path(
            "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam"
        )
        if not case_path.exists():
            pytest.skip("Niederer case not available")

        preview_path = tmp_path / "vid-vm-preview.html"
        mod.generate_video_figure(
            src_path=case_path,
            field="Vm",
            fps=3,
            time_spec="mid",
            mp4_path=tmp_path / "vid-vm-video.mp4",
            frame_path=tmp_path / "vid-vm-frame.png",
            video_html_path=tmp_path / "vid-vm-video.html",
            fig_id="vid-vm",
            preview_html_path=preview_path,
        )
        assert preview_path.exists(), "Preview HTML not created"
        preview_content = preview_path.read_text()
        assert "4dpaper-camera" in preview_content, "Preview HTML missing camera sync postMessage"
        assert "parent.postMessage" in preview_content, "Preview HTML missing postMessage call"


class TestCameraSyncIntegration:
    """Integration tests: camera saved via the server flows into PNG generation."""

    def test_saved_camera_used_for_png(self, tmp_path, monkeypatch):
        """Camera JSON saved by the server is read back and applied during PNG generation."""
        import json

        mod = _load_4dpaper()
        case_path = Path(
            "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam"
        )
        if not case_path.exists():
            pytest.skip("Niederer case not available")

        # 1) Save a camera state file (as the server handler would)
        camera_data = {
            "position": [0.05, 0.03, 0.15],
            "focal_point": [0.005, 0.0035, 0.005],
            "view_up": [0, 1, 0],
        }
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        cam_file = state_dir / "camera_fig-vm.json"
        cam_file.write_text(json.dumps(camera_data))

        # 2) Patch _project_root so generate_png_figure finds our camera file
        monkeypatch.setattr(mod, "_project_root", tmp_path)

        # 3) Generate PNG with the saved camera
        png_out = tmp_path / "fig-vm.png"
        mod.generate_png_figure(
            src_path=case_path,
            field="Vm",
            time_spec="mid",
            output_path=png_out,
            fig_id="fig-vm",
        )
        assert png_out.exists(), "PNG was not created"
        assert png_out.stat().st_size > 500, "PNG is suspiciously small"


class TestPanelEndToEnd:
    """End-to-end integration tests for generate_panel_html/png with real test data."""

    _PANEL = {
        "id": "panel-e2e",
        "layout": "2x1",
        "height": "600px",
        "caption": "",
        "subfigures": [
            {"src": "tests/data/base.stl",    "id": "e2e-stl", "field": "", "time": "mid", "fields": ""},
            {"src": "tests/data/airplane.ply", "id": "e2e-ply", "field": "", "time": "mid", "fields": ""},
        ],
    }

    def test_generate_panel_html_real_files(self, tmp_path):
        """generate_panel_html creates composite HTML and sub-figure HTMLs from real STL/PLY files."""
        pytest.importorskip("pyvista")
        mod = _load_4dpaper()
        stl_path = Path(__file__).parent / "data" / "base.stl"
        ply_path = Path(__file__).parent / "data" / "airplane.ply"
        if not stl_path.exists() or not ply_path.exists():
            pytest.skip("Test data files not found")

        mod.generate_panel_html(self._PANEL, tmp_path)

        assert (tmp_path / "panel-e2e.html").exists(), "Composite panel HTML not created"
        assert (tmp_path / "e2e-stl.html").exists(), "Sub-figure e2e-stl.html not created"
        assert (tmp_path / "e2e-ply.html").exists(), "Sub-figure e2e-ply.html not created"

        html = (tmp_path / "panel-e2e.html").read_text()
        assert "grid-template-columns:repeat(2,1fr)" in html, "CSS grid columns not found"
        assert "4dpaper-camera-ack" in html, "Bidirectional re-relay script not found"

    def test_generate_panel_png_real_files(self, tmp_path):
        """generate_panel_png creates composite PNG whose size matches subfig dims × layout."""
        pytest.importorskip("pyvista")
        from PIL import Image

        mod = _load_4dpaper()
        stl_path = Path(__file__).parent / "data" / "base.stl"
        ply_path = Path(__file__).parent / "data" / "airplane.ply"
        if not stl_path.exists() or not ply_path.exists():
            pytest.skip("Test data files not found")

        mod.generate_panel_png(self._PANEL, tmp_path)

        assert (tmp_path / "panel-e2e.png").exists(), "Composite panel PNG not created"
        img = Image.open(tmp_path / "panel-e2e.png")
        sub_img = Image.open(tmp_path / "e2e-stl.png")
        # 2x1 layout: width = 2 × subfig_width, height = 1 × subfig_height
        assert img.size == (sub_img.size[0] * 2, sub_img.size[1] * 1), (
            f"Expected {(sub_img.size[0]*2, sub_img.size[1])}, got {img.size}"
        )


class TestGeneratePngWindowSize:
    """Verify generate_png_figure uses 900x600 (matching HTML aspect ratio)."""

    def test_png_figure_uses_900x600(self, tmp_path, monkeypatch):
        import importlib.util
        import sys
        from pathlib import Path
        from unittest.mock import MagicMock

        # Stub pyvista BEFORE loading the module
        fake_pv = MagicMock()
        fake_pl = MagicMock()
        fake_pl.screenshot.return_value = None
        fake_pv.Plotter.return_value = fake_pl
        monkeypatch.setitem(sys.modules, "pyvista", fake_pv)

        # Stub SimulationData
        fake_sim = MagicMock()
        fake_sim.n_steps = 3
        fake_mesh = MagicMock()
        fake_surface = MagicMock()
        fake_surface.point_data.__contains__ = lambda self, k: True
        fake_surface.point_data.__getitem__ = lambda self, k: MagicMock()
        fake_surface.cell_data.__contains__ = lambda self, k: False
        fake_mesh.extract_surface.return_value = fake_surface
        fake_sim.get_mesh.return_value = fake_mesh
        fake_loader_mod = MagicMock()
        fake_loader_mod.SimulationData = MagicMock(
            return_value=MagicMock(load=MagicMock(return_value=fake_sim))
        )
        monkeypatch.setitem(sys.modules, "scripts.data_loader", fake_loader_mod)

        spec = importlib.util.spec_from_file_location(
            "fourDpaper_ws",
            Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out_png = tmp_path / "fig.png"

        try:
            mod.generate_png_figure(
                src_path=Path("/fake/case.foam"),
                field="Vm",
                time_spec="mid",
                output_path=out_png,
                fig_id="fig-test",
            )
        except Exception:
            pass  # Only care about the Plotter call args

        fake_pv.Plotter.assert_called_once()
        _, kwargs = fake_pv.Plotter.call_args
        assert kwargs.get("window_size") == (900, 600), (
            f"Expected (900, 600) but got {kwargs.get('window_size')}"
        )
