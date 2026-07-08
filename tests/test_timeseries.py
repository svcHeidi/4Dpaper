"""Tests for 4d-timeseries shortcode parsing and step expansion."""
from __future__ import annotations

import importlib.util
import importlib
from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "_extensions" / "4dpaper"))


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_frontend():
    spec = importlib.util.spec_from_file_location(
        "fourd_frontend",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "lib" / "frontend.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_render():
    return importlib.import_module("lib.render")


class TestParseTimeseriesShortcodes:
    def test_basic_parse(self):
        mod = _load_4dpaper()
        text = '{{< 4d-timeseries src="case.foam" field="Vm" id="ts-vm" steps="4" caption="My cap" >}}'
        result = mod.parse_timeseries_shortcodes(text)
        assert len(result) == 1
        r = result[0]
        assert r["id"] == "ts-vm"
        assert r["src"] == "case.foam"
        assert r["field"] == "Vm"
        assert r["steps"] == "4"
        assert r["caption"] == "My cap"
        assert r["camera_mode"] == "sync"
        assert r["timeseries"] is True

    def test_times_param_parsed(self):
        mod = _load_4dpaper()
        text = '{{< 4d-timeseries src="c.foam" field="Vm" id="ts1" times="first,5,last" >}}'
        result = mod.parse_timeseries_shortcodes(text)
        assert result[0]["times"] == "first,5,last"

    def test_missing_id_skipped(self):
        mod = _load_4dpaper()
        text = '{{< 4d-timeseries src="c.foam" field="Vm" >}}'
        result = mod.parse_timeseries_shortcodes(text)
        assert result == []

    def test_default_steps_is_four(self):
        mod = _load_4dpaper()
        text = '{{< 4d-timeseries src="c.foam" field="Vm" id="ts1" >}}'
        result = mod.parse_timeseries_shortcodes(text)
        assert result[0]["steps"] == "4"

    def test_subfigures_initially_empty(self):
        mod = _load_4dpaper()
        text = '{{< 4d-timeseries src="c.foam" field="Vm" id="ts1" >}}'
        result = mod.parse_timeseries_shortcodes(text)
        assert result[0]["subfigures"] == []
        assert result[0]["layout"] is None


class TestExpandTimeseriesSteps:
    def test_steps_4_divides_evenly(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": ""}
        result = mod._expand_timeseries_steps(ts, 100)
        assert len(result) == 4
        assert result[0] == 0
        assert result[-1] == 99

    def test_times_first_and_last(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": "first,last"}
        result = mod._expand_timeseries_steps(ts, 50)
        assert result == [0, 49]

    def test_times_explicit_indices(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": "0,5,10"}
        result = mod._expand_timeseries_steps(ts, 20)
        assert result == [0, 5, 10]

    def test_times_clamps_to_max(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": "0,999"}
        result = mod._expand_timeseries_steps(ts, 10)
        assert result[1] == 9  # clamped to n_steps - 1

    def test_times_invalid_falls_back_to_steps(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "3", "times": "abc,xyz"}
        result = mod._expand_timeseries_steps(ts, 10)
        assert len(result) == 3  # falls back to steps=3

    def test_steps_1_treated_as_2(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "1", "times": ""}
        result = mod._expand_timeseries_steps(ts, 10)
        assert len(result) == 2  # max(2, 1) = 2

    def test_n_steps_1_returns_single_frame(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": ""}
        result = mod._expand_timeseries_steps(ts, 1)
        assert result == [0]

    def test_n_steps_0_returns_single_frame(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": ""}
        result = mod._expand_timeseries_steps(ts, 0)
        assert result == [0]


class TestMainTimeseriesIntegration:
    def test_main_source_has_parse_timeseries(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.main)
        assert "parse_timeseries_shortcodes" in source
        assert "ts_raw" in source

    def test_main_guard_includes_ts_raw(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.main)
        # The early-exit guard must check ts_raw too
        assert "ts_raw" in source

    def test_main_merges_timeseries_into_panels(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.main)
        assert "panels.append(ts_panel)" in source

    def test_main_timeseries_panel_forces_camera_sync(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.main)
        # A 4d-timeseries is a *mandatory* camera-synced panel: every frame must
        # share one camera file (camera_<panel_id>.json) so rotating one frame
        # moves all of them, the saved viewpoint survives a rebuild, and the
        # static PDF/PNG frames export from the same viewpoint. The ts_panel dict
        # built here must therefore carry camera_mode="sync".
        ts_block = source.split("ts_panel = {", 1)[1].split("panels.append(ts_panel)", 1)[0]
        assert '"camera_mode": "sync"' in ts_block

    def test_render_timeseries_uses_lock_only_parent_toolbar(self):
        render = _load_render()
        import inspect
        source = inspect.getsource(render.generate_panel_html)
        assert "show_transport=not panel.get(\"timeseries\", False)" in source
        assert 'show_lock_btn=not is_timeseries and camera_mode != "sync"' in source


class TestFourdTimeseriesLua:
    def test_fourd_timeseries_function_exists(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert "fourd_timeseries" in content

    def test_fourd_timeseries_registered(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert '["4d-timeseries"]' in content

    def test_fourd_timeseries_reads_manifest(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        # Uses manifest file for subfigure IDs (avoids data: URL iframes which break WebGL)
        assert '.manifest.json"' in content
        assert 'data-panel="' in content

    def test_fourd_timeseries_frames_are_static_no_time_sync(self):
        """Timeseries frames are static per-timestep views: each frame shows its
        own assigned timestep, so they must NOT peer-broadcast a frame index to
        each other. Time/frame sync is a 4d-panel feature (the master transport
        toolbar), not a timeseries one. Camera sync, however, IS mandatory and is
        wired separately via the data-panel attribute + relay.js fan-out."""
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        # Isolate just the fourd_timeseries function body.
        ts_fn = content.split('local function fourd_timeseries(args, kwargs)', 1)[1]
        ts_fn = ts_fn.split('\nlocal function ', 1)[0]
        # Frames must NOT opt into peer time-broadcast …
        assert 'data-panel-time-sync' not in ts_fn
        # … but camera sync must still go through the shared sync-panel helper.
        assert '_build_sync_iframe_panel' in ts_fn

    def test_fourd_timeseries_pdf_uses_90_percent_width(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'width = "90%"' in content

    def test_fourd_timeseries_manifest_carries_time_indices(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert '"time_indices"' in content
        assert "_manifest_time_indices" in content

    def test_fourd_timeseries_toolbar_maps_actual_indices(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert "ACTUAL=" in content
        assert "_fromActual" in content

    def test_fourd_timeseries_uses_panel_lock_toolbar(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert "return _build_sync_iframe_panel(id, caption, height, ncols, 1, subfig_ids, false, time_indices)" in content

    def test_fourd_timeseries_reuses_shared_sync_wrapper(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert "local function _build_sync_iframe_panel(id, caption, height, ncols, nrows, subfig_ids, show_transport, time_indices)" in content
        assert "return _build_sync_iframe_panel(id, caption, height, ncols, nrows, sync_ids, true, nil)" in content

    def test_fourd_timeseries_does_not_use_custom_direct_camera_sync(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'var TS_ID="' not in content
        assert "__fourd_ts_sync" not in content

    def test_panel_toolbar_helper_supports_lock_only_mode(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert "local function _panel_toolbar_html(id, frame_count, time_indices, show_transport)" in content
        assert "if show_transport == nil then" in content
        assert "if show_transport and transport_count > 1 then" in content


class TestTimeseriesMeshSync:
    def test_timeseries_children_keep_hidden_lock_infrastructure(self):
        frontend = _load_frontend()
        import inspect
        source = inspect.getsource(frontend._controls_strip_snippet)
        assert 'html_block_lock = (' in source
        assert 'if show_lock_btn:' not in source.split('html_block_lock = (', 1)[0].rsplit('\n', 6)[-1]

    def test_lock_state_is_reapplied_after_renderer_ready(self):
        frontend = _load_frontend()
        assert 'if(_locked)_setLocked(true);' in frontend._GOLDEN_TOPBAR_JS

    def test_camera_sync_watches_camera_state_not_only_mouseup(self):
        frontend = _load_frontend()
        assert 'function _watchCam()' in frontend._GOLDEN_TOPBAR_JS
        assert '_camWatchSig=_camSig(r);_watchCam();' in frontend._GOLDEN_TOPBAR_JS
        assert '_markCamApplied(cam);' in frontend._GOLDEN_TOPBAR_JS

    def test_orientation_svg_wiring_is_guarded(self):
        # Receiver frames (show_orientation=False, e.g. timeseries frames 1..N)
        # have no cs-svg-axes element. Without a null guard, _svg.addEventListener
        # throws and aborts the whole IIFE — killing camera send/receive setup and
        # breaking sync. The wiring must be guarded so setup completes regardless.
        frontend = _load_frontend()
        assert (
            '_svg=document.getElementById("cs-svg-axes-__FIGSAFE__");if(_svg){'
            in frontend._GOLDEN_TOPBAR_JS
        )
        # The message listener (camera-apply receiver) must not be gated on _svg.
        assert '_svg.addEventListener("click"' not in frontend._GOLDEN_TOPBAR_JS.replace(
            'if(_svg){_svg.addEventListener("click"', ''
        )

    def test_camera_apply_receiver_registers_for_orientationless_frame(self):
        # Generate a strip with show_orientation=False and confirm the golden
        # camera-apply message handler is still present (setup reaches the end).
        frontend = _load_frontend()
        strip = frontend._controls_strip_snippet(
            "recv-frame", show_lock_btn=False, show_orientation=False,
            fields_to_embed=["Vm", "p"], active_field="Vm",
        )
        # No orientation widget markup is emitted (corner div omitted)...
        assert 'id="cs-svg-axes-recv_frame"' not in strip
        # ...but the JS still references the (absent) element, so the guard is
        # what keeps setup alive: the camera-apply receiver must still be emitted.
        assert 'if(_svg){' in strip
        assert '4dpaper-camera-apply' in strip

    def test_reference_sampling_remaps_geometry_from_original_point_ids(self):
        pv = pytest.importorskip("pyvista")
        render = _load_render()

        faces = np.array([3, 0, 1, 2])
        reference = pv.PolyData(
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
            faces,
        )
        reference.point_data["vtkOriginalPointIds"] = np.array([0, 1, 2])

        moved = pv.PolyData(
            np.array([[10.0, 0.0, 0.0], [11.0, 0.0, 0.0], [10.0, 1.0, 0.0]]),
            faces,
        )
        moved.point_data["Vm"] = np.array([1.0, 2.0, 3.0])

        sampled = render._sample_on_reference(reference, moved)

        assert np.allclose(sampled.points, moved.points)
