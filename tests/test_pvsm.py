# tests/test_pvsm.py
"""Tests for PVSM figure support."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest

import importlib.util

PVSM_RENDER = Path(__file__).parent.parent / "_extensions" / "4dpaper" / "pvsm_render.py"
EXAMPLE_PVSM = Path("/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/example_state.pvsm")
PVPYTHON = Path("/Applications/ParaView-6.0.1.app/Contents/bin/pvpython")

def pvpython_available():
    return PVPYTHON.exists() and EXAMPLE_PVSM.exists()


class TestPvsmRenderCLI:
    def test_missing_required_args_exits_nonzero(self):
        """Running pvsm_render.py without --pvsm should exit non-zero."""
        result = subprocess.run(
            [sys.executable, str(PVSM_RENDER), "--out-vtu", "/tmp/x.vtu", "--out-png", "/tmp/x.png"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_missing_pvsm_file_exits_nonzero(self, tmp_path):
        """Running with a non-existent PVSM file should exit non-zero."""
        result = subprocess.run(
            [sys.executable, str(PVSM_RENDER),
             "--pvsm", str(tmp_path / "nonexistent.pvsm"),
             "--out-vtu", str(tmp_path / "out.vtu"),
             "--out-png", str(tmp_path / "out.png")],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPvsmColorParsing:
    def test_scalar_name_at_element_4(self):
        mod = _load_4dpaper()
        info = mod.parse_pvsm_color_info(EXAMPLE_PVSM)
        # The example PVSM colors by "Vm"
        assert info["scalar_name"] == "Vm"

    def test_field_association_is_point_or_cell(self):
        mod = _load_4dpaper()
        info = mod.parse_pvsm_color_info(EXAMPLE_PVSM)
        assert info["field_association"] in ("point", "cell")

    def test_vmin_less_than_vmax(self):
        mod = _load_4dpaper()
        info = mod.parse_pvsm_color_info(EXAMPLE_PVSM)
        assert info["vmin"] < info["vmax"]

    def test_cmap_returned(self):
        mod = _load_4dpaper()
        info = mod.parse_pvsm_color_info(EXAMPLE_PVSM)
        # cmap is either a string name or a matplotlib colormap object
        assert info["cmap"] is not None

    def test_fallback_on_missing_file(self):
        mod = _load_4dpaper()
        info = mod.parse_pvsm_color_info(Path("/nonexistent/file.pvsm"))
        # Should return safe defaults, not raise
        assert info["scalar_name"] == ""
        assert info["cmap"] == "coolwarm"
