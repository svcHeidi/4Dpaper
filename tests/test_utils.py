"""Tests for dashboard/utils.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

class TestSaveCameraState:
    def test_writes_json_with_correct_keys(self, tmp_path):
        from dashboard.utils import save_camera_state
        path = tmp_path / "cam.json"
        changed = save_camera_state(
            position=[1.0, 2.0, 3.0],
            focal_point=[0.01, 0.0015, 0.0035],
            view_up=[0.19, 0.91, -0.37],
            parallel_scale=None,
            output_path=path,
        )
        assert changed is True
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["position"] == [1.0, 2.0, 3.0]
        assert data["focal_point"] == [0.01, 0.0015, 0.0035]
        assert data["view_up"] == [0.19, 0.91, -0.37]
        assert "parallel_scale" not in data

    def test_includes_parallel_scale_when_provided(self, tmp_path):
        from dashboard.utils import save_camera_state
        path = tmp_path / "cam.json"
        changed = save_camera_state(
            position=[0.0, 0.0, 1.0],
            focal_point=[0.0, 0.0, 0.0],
            view_up=[0.0, 1.0, 0.0],
            parallel_scale=0.05,
            output_path=path,
        )
        assert changed is True
        data = json.loads(path.read_text())
        assert data["parallel_scale"] == pytest.approx(0.05)

    def test_creates_parent_directory(self, tmp_path):
        from dashboard.utils import save_camera_state
        nested = tmp_path / "deep" / "nested" / "cam.json"
        changed = save_camera_state(
            position=[0.0, 0.0, 1.0],
            focal_point=[0.0, 0.0, 0.0],
            view_up=[0.0, 1.0, 0.0],
            parallel_scale=None,
            output_path=nested,
        )
        assert changed is True
        assert nested.exists()

    def test_does_not_rewrite_when_payload_is_identical(self, tmp_path):
        from dashboard.utils import save_camera_state

        path = tmp_path / "cam.json"
        first = save_camera_state(
            position=[1.0, 2.0, 3.0],
            focal_point=[0.0, 0.0, 0.0],
            view_up=[0.0, 1.0, 0.0],
            parallel_scale=0.25,
            parallel_projection=1,
            output_path=path,
        )
        mtime_ns = path.stat().st_mtime_ns
        second = save_camera_state(
            position=[1.0, 2.0, 3.0],
            focal_point=[0.0, 0.0, 0.0],
            view_up=[0.0, 1.0, 0.0],
            parallel_scale=0.25,
            parallel_projection=1,
            output_path=path,
        )

        assert first is True
        assert second is False
        assert path.stat().st_mtime_ns == mtime_ns


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
        assert captured["env"].get("FOURD_STRICT_STATIC_EXPORT") == "1"


class TestRunQuartoRenderHtmlExport:
    def test_html_export_uses_standalone_output_without_app_mode(self, tmp_path):
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
            run_quarto_render(qmd, [], output_format="html-export")

        assert "--profile" not in captured["cmd"]
        assert "--output" in captured["cmd"]
        output_idx = captured["cmd"].index("--output")
        assert captured["cmd"][output_idx + 1] == "paper-standalone.html"
        assert "FOURD_APP_MODE" not in captured["env"]


class TestMaybeSignRenderedHtml:
    def test_appends_log_when_signing_occurs(self, tmp_path):
        from unittest.mock import patch
        from dashboard.utils import maybe_sign_rendered_html

        html = tmp_path / "paper.html"
        html.write_text("<html></html>")
        log_lines = []

        with patch("dashboard.utils.sign_html_file_if_configured", return_value=True):
            signed = maybe_sign_rendered_html(html, log_lines)

        assert signed is True
        assert log_lines == ["Signed HTML output: paper.html"]

    def test_raises_when_rendered_html_is_missing(self, tmp_path):
        from dashboard.utils import maybe_sign_rendered_html

        with pytest.raises(FileNotFoundError):
            maybe_sign_rendered_html(tmp_path / "missing.html", [])
