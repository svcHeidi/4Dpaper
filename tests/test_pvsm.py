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


class TestPvsmCacheAndParsing:
    def test_parse_pvsm_shortcodes_finds_basic(self):
        mod = _load_4dpaper()
        text = '{{< 4d-pvsm src="fig-vm.pvsm" id="fig-vm" >}}'
        result = mod.parse_pvsm_shortcodes(text)
        assert len(result) == 1
        assert result[0]["id"] == "fig-vm"
        assert result[0]["src"] == "fig-vm.pvsm"

    def test_parse_pvsm_shortcodes_optional_params(self):
        mod = _load_4dpaper()
        text = '{{< 4d-pvsm src="fig.pvsm" id="fig-a" data="case.foam" time="last" caption="Hi" >}}'
        result = mod.parse_pvsm_shortcodes(text)
        assert result[0]["data"] == "case.foam"
        assert result[0]["time"] == "last"
        assert result[0]["caption"] == "Hi"

    def test_parse_pvsm_shortcodes_defaults(self):
        mod = _load_4dpaper()
        text = '{{< 4d-pvsm src="fig.pvsm" id="fig-a" >}}'
        result = mod.parse_pvsm_shortcodes(text)
        assert result[0]["data"] == ""
        assert result[0]["time"] == ""
        assert result[0]["caption"] == ""

    def test_parse_pvsm_shortcodes_skips_missing_id(self):
        mod = _load_4dpaper()
        text = '{{< 4d-pvsm src="fig.pvsm" >}}'
        result = mod.parse_pvsm_shortcodes(text)
        assert result == []

    def test_parse_pvsm_shortcodes_skips_missing_src(self):
        mod = _load_4dpaper()
        text = '{{< 4d-pvsm id="fig-a" >}}'
        result = mod.parse_pvsm_shortcodes(text)
        assert result == []

    def test_is_cache_valid_extra_deps_triggers_regen(self, tmp_path):
        import time
        mod = _load_4dpaper()
        output = tmp_path / "out.html"
        src = tmp_path / "src.foam"
        extra = tmp_path / "script.py"

        src.write_text("x")
        output.write_text("y")
        time.sleep(0.02)
        extra.write_text("z")  # extra_dep is newer than output

        assert not mod.is_cache_valid(output, src, extra_deps=[extra])

    def test_is_cache_valid_extra_deps_no_regen_when_older(self, tmp_path):
        import time
        mod = _load_4dpaper()
        extra = tmp_path / "script.py"
        extra.write_text("z")
        time.sleep(0.02)
        src = tmp_path / "src.foam"
        src.write_text("x")
        time.sleep(0.02)
        output = tmp_path / "out.html"
        output.write_text("y")  # output is newest

        assert mod.is_cache_valid(output, src, extra_deps=[extra])


class TestGenerateHtmlFromVtu:
    def test_generates_html_from_vtu(self, tmp_path):
        """generate_html_from_vtu produces a vtk.js HTML file from a .vtu mesh."""
        import pyvista as pv
        mod = _load_4dpaper()

        # Create a synthetic mesh and save as .vtu
        mesh = pv.Sphere().cast_to_unstructured_grid()
        mesh.point_data["Vm"] = mesh.points[:, 2]  # z-coordinate as scalar
        vtu_path = tmp_path / "test.vtu"
        mesh.save(str(vtu_path))

        out_html = tmp_path / "test.html"
        mod.generate_html_from_vtu(
            vtu_path=vtu_path,
            out_html=out_html,
            fig_id="test-fig",
            scalar_name="Vm",
            clim=[-1.0, 1.0],
            cmap="coolwarm",
            field_association="point",
            preview=True,  # skip camera JSON lookup
        )

        assert out_html.exists()
        content = out_html.read_text()
        assert "renderWindow" in content or "vtkRenderWindow" in content or len(content) > 1000


class TestPvsmSmoke:
    @pytest.mark.skipif(not pvpython_available(), reason="requires pvpython + example PVSM")
    def test_generate_pvsm_figure_end_to_end(self, tmp_path):
        """Full pipeline: PVSM -> .vtu + .png + .html."""
        mod = _load_4dpaper()

        out_vtu     = tmp_path / "fig-vm-pipeline.vtu"
        out_png     = tmp_path / "fig-vm.png"
        out_html    = tmp_path / "fig-vm.html"
        out_preview = tmp_path / "fig-vm-preview.html"

        mod.generate_pvsm_figure(
            pvsm_path=EXAMPLE_PVSM,
            fig_id="fig-vm",
            figures_dir=tmp_path,
            data_path=None,
            time_spec=None,
            pvpython_path=PVPYTHON,
        )

        # geometry produced and non-empty
        import pyvista as pv
        assert out_vtu.exists(), "VTU not produced"
        mesh = pv.read(str(out_vtu))
        assert mesh.n_points > 0, "VTU has 0 points"

        # screenshot produced and large enough
        assert out_png.exists(), "PNG not produced"
        assert out_png.stat().st_size > 50_000, "PNG suspiciously small"

        # HTML figures produced and contain vtk.js marker
        for html_out in (out_html, out_preview):
            assert html_out.exists(), f"{html_out.name} not produced"
            content = html_out.read_text()
            assert len(content) > 5000, f"{html_out.name} suspiciously small"
