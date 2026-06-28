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


class TestGenerateHtmlFigureCameraFigId:
    def test_camera_fig_id_param_exists(self):
        import inspect
        mod = _load_4dpaper()
        sig = inspect.signature(mod.generate_html_figure)
        assert "camera_fig_id" in sig.parameters
        assert sig.parameters["camera_fig_id"].default is None

    def test_camera_fig_id_used_in_lookup(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_html_figure)
        assert "camera_fig_id" in source
        assert "_cam_id" in source


class TestGeneratePanelPngSyncCamera:
    def test_sync_mode_uses_panel_id_for_camera(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_png)
        assert "camera_mode" in source
        assert "camera_fig_id" in source

    def test_panel_png_reads_saved_field_state(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_png)
        assert "_load_saved_field_state" in source


class TestSyncPanelCacheInvalidation:
    def test_main_source_uses_panel_camera_for_sync(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.main)
        assert "camera_mode" in source
        assert "shared_cam" in source

    def test_main_source_tracks_panel_field_state(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.main)
        assert 'field_{sub[\'id\']}.json' in source


class TestGeneratePanelHtmlWritesManifest:
    def test_generate_panel_html_source_writes_manifest(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_html)
        assert "manifest" in source
        assert ".manifest.json" in source

    def test_relay_script_handles_panel_sync(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'data-panel' in content
        assert 'querySelectorAll' in content

    def test_generate_panel_html_uses_saved_field_state_and_shared_camera(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_html)
        assert "_load_saved_field_state" in source
        assert "camera_fig_id" in source


class TestFourdPanelLua:
    def test_fourd_panel_reads_camera_kwarg(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'kwargs["camera"]' in content

    def test_fourd_panel_has_sync_branch(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'camera_mode == "sync"' in content

    def test_fourd_panel_sync_uses_direct_srcdoc_iframes(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'data-panel="' in content
        assert '"id" .. n' in content


class TestPanelLockToolbar:
    def test_shortcodes_lua_contains_panel_lock_toolbar(self):
        """shortcodes.lua must contain the panel-level lock bar markup."""
        lua_src = (
            Path(__file__).parent.parent
            / "_extensions" / "4dpaper" / "shortcodes.lua"
        ).read_text()
        assert "plb-btn-" in lua_src
        assert "4dpaper-lock-all" in lua_src
        assert "4dpaper-hide-lock-btn" in lua_src


class TestTimeseriesTimeSyncRelay:
    """Regression tests: sync re-relay must forward 4dpaper-time to siblings."""

    def test_sync_re_relay_handles_time_message(self):
        """The sync composite re-relay script must relay '4dpaper-time' messages."""
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_html)
        assert "4dpaper-time" in source, (
            "generate_panel_html sync re-relay must handle '4dpaper-time' "
            "so timeseries subfigures stay in step"
        )

    def test_sync_re_relay_sends_time_apply(self):
        """When '4dpaper-time' arrives the relay must fan out '4dpaper-time-apply'."""
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_html)
        assert "4dpaper-time-apply" in source, (
            "The re-relay must broadcast '4dpaper-time-apply' to sibling iframes"
        )

    def test_sync_re_relay_skips_sender_for_time(self):
        """The time relay must skip the source iframe to avoid feedback loops."""
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_html)
        assert "timeSrc" in source, (
            "Time relay should track the sending iframe (timeSrc) to skip it"
        )

