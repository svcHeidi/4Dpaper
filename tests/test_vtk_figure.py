"""Tests for the VTU/render-spec 4DPaper path."""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import pytest


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pv = pytest.importorskip("pyvista")


def _write_sample_mesh(mesh_path: Path) -> None:
    mesh = pv.Sphere(theta_resolution=16, phi_resolution=16).cast_to_unstructured_grid()
    mesh.point_data["Vm"] = mesh.points[:, 2]
    mesh.cell_data["CellValue"] = list(range(mesh.n_cells))
    mesh.save(str(mesh_path))


class TestParseVtkShortcodes:
    def test_finds_basic_shortcode(self):
        mod = _load_4dpaper()
        text = '{{< 4d-vtk spec="state/figures/fig-vm.render.json" id="fig-vm" >}}'
        result = mod.parse_vtk_shortcodes(text)
        assert result == [
            {"spec": "state/figures/fig-vm.render.json", "id": "fig-vm", "caption": ""}
        ]

    def test_parses_optional_caption(self):
        mod = _load_4dpaper()
        text = '{{< 4d-vtk spec="state/figures/fig-vm.render.json" id="fig-vm" caption="Vm field" >}}'
        result = mod.parse_vtk_shortcodes(text)
        assert result[0]["caption"] == "Vm field"

    def test_skips_missing_id(self):
        mod = _load_4dpaper()
        text = '{{< 4d-vtk spec="state/figures/fig-vm.render.json" >}}'
        assert mod.parse_vtk_shortcodes(text) == []

    def test_skips_missing_spec(self):
        mod = _load_4dpaper()
        text = '{{< 4d-vtk id="fig-vm" >}}'
        assert mod.parse_vtk_shortcodes(text) == []

    def test_ignores_shortcode_in_fenced_code_block(self):
        mod = _load_4dpaper()
        text = (
            "```md\n"
            '{{< 4d-vtk spec="skip.render.json" id="skip-me" >}}\n'
            "```\n"
            '{{< 4d-vtk spec="use.render.json" id="use-me" >}}'
        )
        result = mod.parse_vtk_shortcodes(text)
        assert len(result) == 1
        assert result[0]["id"] == "use-me"


class TestLoadRenderSpec:
    def test_loads_valid_spec_and_resolves_mesh_path(self, tmp_path):
        mod = _load_4dpaper()
        mesh_path = tmp_path / "fig-vm.surface.vtu"
        _write_sample_mesh(mesh_path)
        spec_path = tmp_path / "fig-vm.render.json"
        spec_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "mesh": "fig-vm.surface.vtu",
                    "field": {"name": "Vm"},
                }
            )
        )

        spec = mod.load_render_spec(spec_path)
        assert spec["mesh_path"] == mesh_path.resolve()
        assert spec["field"]["association"] == "point"
        assert spec["field"]["colormap"] == "coolwarm"
        assert spec["filter"]["kind"] == "none"
        assert spec["display"]["background"] == "#1a1a2e"
        assert spec["display"]["show_scalar_bar"] is True

    def test_requires_mesh(self, tmp_path):
        mod = _load_4dpaper()
        spec_path = tmp_path / "bad.render.json"
        spec_path.write_text(json.dumps({"version": 1, "field": {"name": "Vm"}}))
        with pytest.raises(RuntimeError, match="missing required 'mesh'"):
            mod.load_render_spec(spec_path)

    def test_requires_field_name(self, tmp_path):
        mod = _load_4dpaper()
        spec_path = tmp_path / "bad.render.json"
        spec_path.write_text(json.dumps({"version": 1, "mesh": "mesh.vtu", "field": {}}))
        with pytest.raises(RuntimeError, match="missing required 'field.name'"):
            mod.load_render_spec(spec_path)

    def test_rejects_invalid_filter_kind(self, tmp_path):
        mod = _load_4dpaper()
        spec_path = tmp_path / "bad.render.json"
        spec_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "mesh": "mesh.vtu",
                    "field": {"name": "Vm"},
                    "filter": {"kind": "outer_shell"},
                }
            )
        )
        with pytest.raises(RuntimeError, match="filter.kind"):
            mod.load_render_spec(spec_path)


class TestPrepareRenderMesh:
    def test_none_returns_original_mesh(self):
        mod = _load_4dpaper()
        mesh = pv.ImageData(dimensions=(3, 3, 3))
        out = mod.prepare_render_mesh(mesh, "none")
        assert out is mesh

    def test_surface_extracts_boundary(self):
        mod = _load_4dpaper()
        mesh = pv.ImageData(dimensions=(3, 3, 3))
        out = mod.prepare_render_mesh(mesh, "surface")
        assert out.n_cells > 0
        assert out.n_cells != mesh.n_cells

    def test_invalid_kind_raises(self):
        mod = _load_4dpaper()
        mesh = pv.Sphere()
        with pytest.raises(ValueError, match="Unsupported filter kind"):
            mod.prepare_render_mesh(mesh, "bad")


class TestGenerateFromRenderSpec:
    def _make_spec(self, tmp_path, *, filter_kind: str = "none") -> Path:
        mesh_path = tmp_path / "fig-vm.surface.vtu"
        _write_sample_mesh(mesh_path)
        spec_path = tmp_path / "fig-vm.render.json"
        spec_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "mesh": mesh_path.name,
                    "field": {
                        "name": "Vm",
                        "association": "point",
                        "range": [-1.0, 1.0],
                        "colormap": "coolwarm",
                    },
                    "filter": {"kind": filter_kind},
                    "display": {
                        "background": "#1a1a2e",
                        "show_scalar_bar": True,
                    },
                }
            )
        )
        return spec_path

    def test_generates_html_with_camera_sync(self, tmp_path, monkeypatch):
        mod = _load_4dpaper()
        spec_path = self._make_spec(tmp_path)
        monkeypatch.setattr(mod, "_project_root", tmp_path)
        out_html = tmp_path / "fig-vm.html"

        mod.generate_html_from_render_spec(spec_path, out_html, fig_id="fig-vm")

        assert out_html.exists()
        content = out_html.read_text()
        assert "parent.postMessage" in content
        assert "4dpaper-camera" in content
        assert "camera-badge-fig-vm" in content

    def test_generates_png(self, tmp_path, monkeypatch):
        mod = _load_4dpaper()
        spec_path = self._make_spec(tmp_path, filter_kind="surface")
        monkeypatch.setattr(mod, "_project_root", tmp_path)
        out_png = tmp_path / "fig-vm.png"

        mod.generate_png_from_render_spec(spec_path, out_png, fig_id="fig-vm")

        assert out_png.exists()
        assert out_png.stat().st_size > 500

    def test_falls_back_to_geometry_only_when_field_missing(self, tmp_path, monkeypatch, capsys):
        mod = _load_4dpaper()
        mesh_path = tmp_path / "fig-vm.surface.vtu"
        _write_sample_mesh(mesh_path)
        spec_path = tmp_path / "fig-vm.render.json"
        spec_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "mesh": mesh_path.name,
                    "field": {"name": "MissingField", "association": "point"},
                }
            )
        )
        monkeypatch.setattr(mod, "_project_root", tmp_path)
        out_html = tmp_path / "fig-vm.html"

        mod.generate_html_from_render_spec(spec_path, out_html, fig_id="fig-vm")

        captured = capsys.readouterr()
        assert "rendering geometry only" in captured.err.lower()
        assert out_html.exists()


class TestVtkCache:
    def test_extra_deps_newer_than_output_invalidates_cache(self, tmp_path):
        mod = _load_4dpaper()
        spec_path = tmp_path / "fig-vm.render.json"
        spec_path.write_text("{}")
        output_path = tmp_path / "fig-vm.html"
        output_path.write_text("<html></html>")
        time.sleep(0.05)
        mesh_path = tmp_path / "fig-vm.surface.vtu"
        mesh_path.write_text("mesh")

        assert mod.is_cache_valid(output_path, spec_path, extra_deps=[mesh_path]) is False

    def test_output_newer_than_spec_mesh_and_camera_is_valid(self, tmp_path):
        mod = _load_4dpaper()
        spec_path = tmp_path / "fig-vm.render.json"
        mesh_path = tmp_path / "fig-vm.surface.vtu"
        camera_path = tmp_path / "camera_fig-vm.json"
        spec_path.write_text("{}")
        mesh_path.write_text("mesh")
        camera_path.write_text("{}")
        time.sleep(0.05)
        output_path = tmp_path / "fig-vm.png"
        output_path.write_text("png")

        assert mod.is_cache_valid(
            output_path,
            spec_path,
            camera_path=camera_path,
            extra_deps=[mesh_path],
        ) is True
