"""Tests for Plotly graph camera save/apply wiring."""
from __future__ import annotations

import importlib.util
import json
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


def _load_parser():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper_parser",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "lib" / "parser.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_plotly_camera_sync_snippet_posts_and_applies_camera():
    mod = _load_4dpaper()
    html = mod._plotly_camera_sync_snippet("fig-plot")
    assert "plotly_relayout" in html
    assert "4dpaper-camera" in html
    assert "4dpaper-camera-apply" in html
    assert "Plotly.relayout" in html


def test_plotly_camera_from_saved_state_maps_projection():
    mod = _load_4dpaper()
    result = mod._plotly_camera_from_saved_state(
        {
            "position": [1, 2, 3],
            "focal_point": [0.1, 0.2, 0.3],
            "view_up": [0, 1, 0],
            "parallel_projection": 1,
        }
    )
    assert result == {
        "eye": {"x": 1.0, "y": 2.0, "z": 3.0},
        "center": {"x": 0.1, "y": 0.2, "z": 0.3},
        "up": {"x": 0.0, "y": 1.0, "z": 0.0},
        "projection": {"type": "orthographic"},
    }


def test_apply_saved_plotly_camera_updates_scene_layout(tmp_path, monkeypatch):
    go = pytest.importorskip("plotly.graph_objects")
    mod = _load_4dpaper()

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "camera_fig-plot.json").write_text(
        """
        {
          "position": [1, 2, 3],
          "focal_point": [0.1, 0.2, 0.3],
          "view_up": [0, 1, 0],
          "parallel_projection": 1
        }
        """.strip()
    )
    monkeypatch.setattr(mod, "_project_root", tmp_path)

    fig = go.Figure(data=[go.Scatter3d(x=[0, 1], y=[0, 1], z=[0, 1])])
    assert mod._apply_saved_plotly_camera(fig, "fig-plot") is True
    assert fig.layout.scene.camera.eye.x == 1
    assert fig.layout.scene.camera.center.y == 0.2
    assert fig.layout.scene.camera.up.y == 1
    assert fig.layout.scene.camera.projection.type == "orthographic"


def test_graph_cache_includes_camera_dependency():
    content = (
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py"
    ).read_text()
    assert "is_cache_valid(out_html, src, camera_path=camera_path" in content
    assert "is_cache_valid(out_png, src, camera_path=camera_path" in content


def test_plotly_json_fixture_is_parseable_and_accepted_by_shortcode_parser():
    fixture = Path(__file__).parent.parent / "examples" / "heart" / "media" / "example_graph.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    assert isinstance(data.get("data"), list)
    assert isinstance(data.get("layout"), dict)

    parser = _load_parser()
    qmd = (
        '{{< 4d-graph id="pressure-curve" '
        'src="examples/heart/media/example_graph.json" '
        'caption="Pressure curve" >}}'
    )
    parsed = parser.parse_graph_shortcodes(qmd)
    assert parsed == [
        {
            "id": "pressure-curve",
            "src": "examples/heart/media/example_graph.json",
            "caption": "Pressure curve",
        }
    ]
