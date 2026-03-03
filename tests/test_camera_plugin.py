"""Tests for the camera sync Tornado plugin."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_camera_plugin_imports():
    from dashboard.camera_plugin import CameraHandler, ROUTES
    assert CameraHandler is not None
    assert len(ROUTES) == 1
    assert "/camera/" in ROUTES[0][0]


def test_camera_handler_post_writes_json(tmp_path):
    """CameraHandler.post() writes camera state JSON to state/camera_<fig_id>.json."""
    from dashboard.camera_plugin import CameraHandler

    body = json.dumps({
        "position": [1.0, 2.0, 3.0],
        "focal_point": [0.0, 0.0, 0.0],
        "view_up": [0.0, 1.0, 0.0],
    }).encode()

    request = MagicMock()
    request.body = body

    handler = CameraHandler.__new__(CameraHandler)
    handler.request = request
    handler._finished = False
    handler._headers = {}
    handler._write_buffer = []

    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.post("fig-vm")

    cam_path = tmp_path / "state" / "camera_fig-vm.json"
    assert cam_path.exists(), "camera JSON not written"
    data = json.loads(cam_path.read_text())
    assert data["position"] == [1.0, 2.0, 3.0]
    assert data["focal_point"] == [0.0, 0.0, 0.0]
    assert data["view_up"] == [0.0, 1.0, 0.0]
