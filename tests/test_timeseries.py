"""Tests for 4d-timeseries shortcode parsing and step expansion."""
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
        assert "panels.append(ts)" in source


class TestFourdTimeseriesLua:
    def test_fourd_timeseries_function_exists(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert "fourd_timeseries" in content

    def test_fourd_timeseries_registered(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert '["4d-timeseries"]' in content

    def test_fourd_timeseries_embeds_composite_html(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'state/figures/" .. id .. ".html"' in content

    def test_fourd_timeseries_pdf_uses_90_percent_width(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'width = "90%"' in content
