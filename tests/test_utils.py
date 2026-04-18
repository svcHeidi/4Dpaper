"""Tests for dashboard/utils.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make dashboard importable
sys.path.insert(0, str(Path(__file__).parent.parent))

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


class TestRunQuartoRenderPaperview:
    def test_paperview_sets_env_vars_and_profile(self, tmp_path):
        from unittest.mock import patch, MagicMock
        from dashboard.utils import run_quarto_render

        qmd = tmp_path / "paper.qmd"
        qmd.write_text("# Test\n")
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env", {})
            proc = MagicMock()
            proc.stdout.__iter__ = lambda s: iter([])
            proc.wait.return_value = None
            proc.returncode = 0
            return proc

        with patch("subprocess.Popen", fake_popen):
            run_quarto_render(qmd, [], output_format="paperview")

        assert "--profile" in captured["cmd"]
        profile_idx = captured["cmd"].index("--profile")
        assert captured["cmd"][profile_idx + 1] == "paperview"
        assert captured["env"].get("FOURD_PAPER_VIEW") == "1"
        assert captured["env"].get("FOURD_APP_MODE") == "1"
