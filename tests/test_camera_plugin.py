"""Tests for the camera sync Tornado plugin."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_handler(body_bytes: bytes) -> "CameraHandler":
    """Create a minimal CameraHandler with mocked request and response methods."""
    from dashboard.camera_plugin import CameraHandler
    request = MagicMock()
    request.body = body_bytes
    handler = CameraHandler.__new__(CameraHandler)
    handler.request = request
    handler.write = MagicMock()
    handler.set_status = MagicMock()
    handler.finish = MagicMock()
    return handler


def test_camera_plugin_imports():
    from dashboard.camera_plugin import CameraHandler, ROUTES
    assert CameraHandler is not None
    assert len(ROUTES) == 2
    assert "/camera/" in ROUTES[0][0]
    assert "/camera-lock/" in ROUTES[1][0]


def test_camera_handler_post_writes_json(tmp_path):
    """Happy path: POST writes camera state JSON to correct path."""
    body = json.dumps({
        "position": [1.0, 2.0, 3.0],
        "focal_point": [0.0, 0.0, 0.0],
        "view_up": [0.0, 1.0, 0.0],
    }).encode()
    handler = _make_handler(body)
    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.post("fig-vm")
    cam_path = tmp_path / "state" / "camera_fig-vm.json"
    assert cam_path.exists(), "camera JSON not written"
    data = json.loads(cam_path.read_text())
    assert data["position"] == [1.0, 2.0, 3.0]
    assert data["focal_point"] == [0.0, 0.0, 0.0]
    assert data["view_up"] == [0.0, 1.0, 0.0]
    handler.write.assert_called_once_with({"status": "ok"})


def test_camera_handler_post_invalid_json(tmp_path):
    """POST with non-JSON body returns 400."""
    handler = _make_handler(b"not json")
    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.post("fig-vm")
    handler.set_status.assert_called_once_with(400)
    written = handler.write.call_args[0][0]
    assert written["status"] == "error"


def test_camera_handler_post_missing_key(tmp_path):
    """POST with missing required field returns 400."""
    body = json.dumps({"position": [0, 0, 1]}).encode()  # missing focal_point and view_up
    handler = _make_handler(body)
    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.post("fig-vm")
    handler.set_status.assert_called_once_with(400)
    written = handler.write.call_args[0][0]
    assert written["status"] == "error"
    assert "focal_point" in written["detail"] or "view_up" in written["detail"]


def test_camera_handler_post_invalid_fig_id(tmp_path):
    """POST with path-traversal fig_id returns 400."""
    body = json.dumps({
        "position": [0, 0, 1],
        "focal_point": [0, 0, 0],
        "view_up": [0, 1, 0],
    }).encode()
    handler = _make_handler(body)
    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.post("../../etc/passwd")
    handler.set_status.assert_called_once_with(400)
    # No file should be written
    assert not (tmp_path / "state").exists()
