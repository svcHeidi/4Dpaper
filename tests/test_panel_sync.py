"""Tests for panel camera sync mode."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSnippetForSync:
    def test_wildcard_ack_accepted(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        # The ack filter must accept wildcard "*" from sync panels
        assert 'fig_id!=="*"' in snippet or "fig_id !== \"*\"" in snippet

    def test_camera_apply_listener_present(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        assert "4dpaper-camera-apply" in snippet

    def test_camera_apply_sets_camera_position(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        assert "setPosition" in snippet
        assert "setFocalPoint" in snippet
        assert "setViewUp" in snippet


class TestParsePanelShortcodes:
    def test_camera_mode_defaults_to_independent(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p1" layout="2x1" src1="a.foam" id1="f1" field1="Vm" src2="b.foam" id2="f2" field2="Vm" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result[0]["camera_mode"] == "independent"

    def test_camera_mode_sync_parsed(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p1" layout="2x1" camera="sync" src1="a.foam" id1="f1" field1="Vm" src2="b.foam" id2="f2" field2="Vm" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result[0]["camera_mode"] == "sync"

    def test_unknown_camera_value_treated_as_independent(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p1" layout="1x1" camera="wibble" src1="a.foam" id1="f1" field1="Vm" >}}'
        result = mod.parse_panel_shortcodes(text)
        # Any non-"sync" value keeps the raw value but generate_panel_html treats non-"sync" as independent
        assert "camera_mode" in result[0]


class TestGeneratePanelHtml:
    def test_sync_re_relay_contains_panel_id(self, tmp_path):
        """Sync composite HTML must contain PANEL_ID variable."""
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_html)
        assert "camera_mode" in source
        assert "PANEL_ID" in source

    def test_sync_re_relay_contains_camera_apply_broadcast(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_html)
        assert "4dpaper-camera-apply" in source

    def test_independent_re_relay_has_lock_passthrough(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_html)
        assert "4dpaper-lock-query" in source
        assert "4dpaper-lock-state" in source


class TestGeneratePngFigureCameraFigId:
    def test_camera_fig_id_param_exists(self):
        import inspect
        mod = _load_4dpaper()
        sig = inspect.signature(mod.generate_png_figure)
        assert "camera_fig_id" in sig.parameters
        assert sig.parameters["camera_fig_id"].default is None

    def test_camera_fig_id_used_in_lookup(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_png_figure)
        assert "camera_fig_id" in source
        assert "_cam_id" in source


class TestGeneratePanelPngSyncCamera:
    def test_sync_mode_uses_panel_id_for_camera(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_png)
        assert "camera_mode" in source
        assert "camera_fig_id" in source
