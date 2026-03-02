"""Tests for dashboard/utils.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Make dashboard importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.utils import load_config, load_manifest, resolve_param_paths


class TestLoadConfig:
    def test_returns_dict_with_tutorials_key(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "cardiacfoam_root: /foo\nquarto_paper_path: /bar.qmd\ntutorials: {}\n"
        )
        with patch("dashboard.utils.CONFIG_PATH", cfg_file):
            cfg = load_config()
        assert "tutorials" in cfg
        assert cfg["cardiacfoam_root"] == "/foo"

    def test_raises_on_missing_file(self, tmp_path):
        missing = tmp_path / "no_such.yaml"
        with patch("dashboard.utils.CONFIG_PATH", missing):
            with pytest.raises(FileNotFoundError):
                load_config()


class TestLoadManifest:
    def test_returns_artifacts_list(self, tmp_path):
        manifest = {
            "schema_version": "1.0",
            "tutorial": "test",
            "output_dir": str(tmp_path),
            "generated_at_utc": "2026-01-01T00:00:00+00:00",
            "artifact_count": 1,
            "artifacts": [{"path": "foo.html", "kind": "plot", "format": "html", "label": "Foo"}],
        }
        manifest_path = tmp_path / "plots.json"
        manifest_path.write_text(json.dumps(manifest))
        result = load_manifest(manifest_path)
        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["format"] == "html"

    def test_returns_none_when_missing(self, tmp_path):
        result = load_manifest(tmp_path / "plots.json")
        assert result is None


class TestResolveParamPaths:
    def test_resolves_relative_paths_to_absolute(self, tmp_path):
        root = tmp_path
        params = {
            "output_dir": "some/relative",
            "show": False,
        }
        resolved = resolve_param_paths(params, root=root)
        assert resolved["output_dir"] == str(root / "some/relative")
        assert resolved["show"] is False

    def test_leaves_absolute_paths_unchanged(self, tmp_path):
        params = {"output_dir": "/abs/path"}
        resolved = resolve_param_paths(params, root=tmp_path)
        assert resolved["output_dir"] == "/abs/path"


# ── New tests for Task 3 ──────────────────────────────────────────────────────

class TestSaveCameraState:
    def test_writes_json_with_correct_keys(self, tmp_path):
        from dashboard.utils import save_camera_state
        path = tmp_path / "cam.json"
        save_camera_state(
            position=[1.0, 2.0, 3.0],
            focal_point=[0.01, 0.0015, 0.0035],
            view_up=[0.19, 0.91, -0.37],
            parallel_scale=None,
            output_path=path,
        )
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["position"] == [1.0, 2.0, 3.0]
        assert data["focal_point"] == [0.01, 0.0015, 0.0035]
        assert data["view_up"] == [0.19, 0.91, -0.37]
        assert "parallel_scale" not in data

    def test_includes_parallel_scale_when_provided(self, tmp_path):
        from dashboard.utils import save_camera_state
        path = tmp_path / "cam.json"
        save_camera_state(
            position=[0.0, 0.0, 1.0],
            focal_point=[0.0, 0.0, 0.0],
            view_up=[0.0, 1.0, 0.0],
            parallel_scale=0.05,
            output_path=path,
        )
        data = json.loads(path.read_text())
        assert data["parallel_scale"] == pytest.approx(0.05)

    def test_creates_parent_directory(self, tmp_path):
        from dashboard.utils import save_camera_state
        nested = tmp_path / "deep" / "nested" / "cam.json"
        save_camera_state(
            position=[0.0, 0.0, 1.0],
            focal_point=[0.0, 0.0, 0.0],
            view_up=[0.0, 1.0, 0.0],
            parallel_scale=None,
            output_path=nested,
        )
        assert nested.exists()


class TestLoadCameraState:
    def test_returns_dict_for_existing_file(self, tmp_path):
        from dashboard.utils import load_camera_state
        path = tmp_path / "cam.json"
        path.write_text(
            json.dumps({"position": [1, 2, 3], "focal_point": [0, 0, 0], "view_up": [0, 1, 0]})
        )
        result = load_camera_state(path)
        assert result is not None
        assert result["position"] == [1, 2, 3]

    def test_returns_none_when_missing(self, tmp_path):
        from dashboard.utils import load_camera_state
        result = load_camera_state(tmp_path / "no_such_file.json")
        assert result is None
