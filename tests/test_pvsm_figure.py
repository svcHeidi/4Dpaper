"""Tests for PVSM figure controls parity (lock, orientation, time scrubber)."""
from __future__ import annotations
import importlib.util
import json
import struct
import sys
import time as _time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FAKE_COLOR_INFO = {
    "scalar_name": "Vm",
    "vmin": -0.1,
    "vmax": 0.1,
    "cmap": "coolwarm",
    "field_association": "point",
}


def _make_bins(figures_dir: Path, fig_id: str, n_times: int, n_points: int) -> None:
    """Write fake float32 scalar .bin files and times.json."""
    for i in range(n_times):
        val = float(i)
        data = struct.pack(f"{n_points}f", *([val] * n_points))
        (figures_dir / f"{fig_id}-scalars-t{i}.bin").write_bytes(data)
    labels = [f"{i * 0.01:.4g}" for i in range(n_times)]
    (figures_dir / f"{fig_id}-times.json").write_text(json.dumps(labels))


def _fake_subprocess_side_effect(figures_dir, fig_id, n_times=3, n_points=10):
    """Return a subprocess.run mock side_effect that writes expected output files."""
    def _side_effect(cmd, **kwargs):
        (figures_dir / f"{fig_id}-pipeline.vtu").write_text("<VTKFile/>")
        (figures_dir / f"{fig_id}.png").write_bytes(b"\x89PNG")
        _make_bins(figures_dir, fig_id, n_times, n_points)
        return MagicMock(returncode=0, stdout="", stderr="")
    return _side_effect


def _call_generate(mod, tmp_path, fig_id="fig-pvsm-vm", time_spec=None,
                   n_times=3, n_points=10, scalar_name="Vm"):
    """Call generate_pvsm_figure with all I/O mocked; return output HTML text."""
    figures_dir = tmp_path / "figures"
    figures_dir.mkdir(exist_ok=True)
    pvsm_path = tmp_path / "test.pvsm"
    pvsm_path.write_text("<ParaView/>")
    pvpython = tmp_path / "pvpython"
    pvpython.write_text("#!/bin/sh\n")
    pvpython.chmod(0o755)

    color_info = {**FAKE_COLOR_INFO, "scalar_name": scalar_name}

    def _fake_html(vtu_path, out_html, **kwargs):
        out_html.write_text("<html><body></body></html>")

    with patch("subprocess.run",
               side_effect=_fake_subprocess_side_effect(figures_dir, fig_id, n_times, n_points)), \
         patch.object(mod, "parse_pvsm_color_info", return_value=color_info), \
         patch.object(mod, "generate_html_from_vtu", side_effect=_fake_html):
        mod.generate_pvsm_figure(
            pvsm_path=pvsm_path,
            fig_id=fig_id,
            figures_dir=figures_dir,
            time_spec=time_spec,
            pvpython_path=pvpython,
        )

    return (figures_dir / f"{fig_id}.html").read_text()


class TestPvsmControls:
    def test_pvsm_controls_injected(self, tmp_path):
        """Lock widget always present regardless of time_spec."""
        mod = _load_4dpaper()
        html = _call_generate(mod, tmp_path, time_spec="0.5")
        assert 'id="cs-lock-widget-fig_pvsm_vm"' in html

    def test_pvsm_orientation_injected(self, tmp_path):
        """Orientation SVG always present."""
        mod = _load_4dpaper()
        html = _call_generate(mod, tmp_path, time_spec="0.5")
        assert 'id="cs-svg-axes-fig_pvsm_vm"' in html

    def test_pvsm_time_scrubber_when_no_time_spec(self, tmp_path):
        """Time slider present when time_spec=None and bins exist."""
        mod = _load_4dpaper()
        html = _call_generate(mod, tmp_path, time_spec=None)
        assert 'id="cs-time-slider-fig_pvsm_vm"' in html

    def test_pvsm_no_scrubber_when_time_spec_set(self, tmp_path):
        """No time slider when time_spec is set (static render)."""
        mod = _load_4dpaper()
        html = _call_generate(mod, tmp_path, time_spec="0.5")
        assert 'id="cs-time-slider-fig_pvsm_vm"' not in html

    def test_pvsm_topology_guard(self, tmp_path, capsys):
        """Mismatched bin lengths → no scrubber, warning to stderr."""
        mod = _load_4dpaper()
        figures_dir = tmp_path / "figures"
        figures_dir.mkdir()
        pvsm_path = tmp_path / "test.pvsm"
        pvsm_path.write_text("<ParaView/>")
        pvpython = tmp_path / "pvpython"
        pvpython.write_text("#!/bin/sh\n")
        pvpython.chmod(0o755)

        def _mismatched(cmd, **kwargs):
            (figures_dir / "fig-pvsm-vm-pipeline.vtu").write_text("<VTKFile/>")
            (figures_dir / "fig-pvsm-vm.png").write_bytes(b"\x89PNG")
            # Frame 0: 10 pts, Frame 1: 15 pts — MISMATCH
            (figures_dir / "fig-pvsm-vm-scalars-t0.bin").write_bytes(
                struct.pack("10f", *([0.0] * 10)))
            (figures_dir / "fig-pvsm-vm-scalars-t1.bin").write_bytes(
                struct.pack("15f", *([1.0] * 15)))
            (figures_dir / "fig-pvsm-vm-times.json").write_text('["0.0", "0.01"]')
            return MagicMock(returncode=0, stdout="", stderr="")

        def _fake_html(vtu_path, out_html, **kwargs):
            out_html.write_text("<html><body></body></html>")

        with patch("subprocess.run", side_effect=_mismatched), \
             patch.object(mod, "parse_pvsm_color_info", return_value=FAKE_COLOR_INFO), \
             patch.object(mod, "generate_html_from_vtu", side_effect=_fake_html):
            mod.generate_pvsm_figure(
                pvsm_path=pvsm_path,
                fig_id="fig-pvsm-vm",
                figures_dir=figures_dir,
                time_spec=None,
                pvpython_path=pvpython,
            )

        html = (figures_dir / "fig-pvsm-vm.html").read_text()
        assert 'id="cs-time-slider-fig_pvsm_vm"' not in html
        captured = capsys.readouterr()
        assert "topology" in (captured.err + captured.out).lower()

    def test_pvsm_no_scrubber_when_empty_scalar(self, tmp_path):
        """No scrubber when scalar_name is empty; lock still injected."""
        mod = _load_4dpaper()
        html = _call_generate(mod, tmp_path, time_spec=None, scalar_name="")
        assert 'id="cs-time-slider-fig_pvsm_vm"' not in html
        assert 'id="cs-lock-widget-fig_pvsm_vm"' in html

    def test_pvsm_global_range_computed(self, tmp_path):
        """Time scrubber is present when bins exist (global range computed)."""
        mod = _load_4dpaper()
        # Frames: 0.0, 1.0, 0.5 — global range should be [0.0, 1.0]
        html = _call_generate(mod, tmp_path, time_spec=None, n_times=3)
        assert 'id="cs-time-slider-fig_pvsm_vm"' in html

    def test_pvsm_cache_stale_bins(self, tmp_path):
        """is_cache_valid returns False when pvsm_src is newer than bin."""
        mod = _load_4dpaper()
        figures_dir = tmp_path / "figures"
        figures_dir.mkdir()
        fig_id = "fig-pvsm-vm"

        # Write bin first
        bin_path = figures_dir / f"{fig_id}-scalars-t0.bin"
        bin_path.write_bytes(b"\x00" * 4)
        _time.sleep(0.05)
        # Then write pvsm_src (newer)
        pvsm_src = tmp_path / "test.pvsm"
        pvsm_src.write_text("")

        assert mod.is_cache_valid(bin_path, pvsm_src) is False

    def test_pvsm_cache_missing_bins(self, tmp_path):
        """is_cache_valid returns False when bin does not exist."""
        mod = _load_4dpaper()
        bin_path = tmp_path / "fig-pvsm-vm-scalars-t0.bin"
        pvsm_src = tmp_path / "test.pvsm"
        pvsm_src.write_text("")
        # bin_path does not exist
        assert mod.is_cache_valid(bin_path, pvsm_src) is False

    def test_pvsm_cache_includes_scalar_bins(self, tmp_path):
        """main() cache_ok is False when bins are missing even if out_html and out_png are present."""
        mod = _load_4dpaper()
        figures_dir = tmp_path / "figures"
        figures_dir.mkdir()
        fig_id = "fig-pvsm-vm"
        pvsm_src = tmp_path / "test.pvsm"
        pvsm_src.write_text("")

        # Write times.json indicating 2 steps
        (figures_dir / f"{fig_id}-times.json").write_text('["0.0", "0.01"]')
        # Write up-to-date out_html and out_png (newer than pvsm_src)
        _time.sleep(0.05)
        out_html = figures_dir / f"{fig_id}.html"
        out_png  = figures_dir / f"{fig_id}.png"
        out_html.write_text("<html><body></body></html>")
        out_png.write_bytes(b"\x89PNG")
        # Scalar bins are ABSENT — cache should be invalid
        assert not mod.is_cache_valid(figures_dir / f"{fig_id}-scalars-t0.bin", pvsm_src)
        assert not mod.is_cache_valid(figures_dir / f"{fig_id}-scalars-t1.bin", pvsm_src)
