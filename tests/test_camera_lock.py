"""Tests for the CameraLockHandler Tornado endpoint."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_lock_handler(body_bytes: bytes = b"") -> "CameraLockHandler":
    from dashboard.camera_plugin import CameraLockHandler
    request = MagicMock()
    request.body = body_bytes
    handler = CameraLockHandler.__new__(CameraLockHandler)
    handler.request = request
    handler.write = MagicMock()
    handler.set_status = MagicMock()
    handler.finish = MagicMock()
    return handler


def test_camera_lock_handler_in_routes():
    from dashboard.camera_plugin import CameraLockHandler, ROUTES
    assert CameraLockHandler is not None
    patterns = [r for r, _ in ROUTES]
    assert any("camera-lock" in p for p in patterns)


def test_lock_get_returns_false_when_absent(tmp_path):
    (tmp_path / "state").mkdir()
    handler = _make_lock_handler()
    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.get("fig-vm")
    handler.write.assert_called_once_with({"locked": False})


def test_lock_get_returns_saved_state(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "camera_fig-vm_lock.json").write_text('{"locked": true}')
    handler = _make_lock_handler()
    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.get("fig-vm")
    handler.write.assert_called_once_with({"locked": True})


def test_lock_post_writes_file(tmp_path):
    (tmp_path / "state").mkdir()
    body = json.dumps({"locked": True}).encode()
    handler = _make_lock_handler(body)
    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.post("fig-vm")
    lock_path = tmp_path / "state" / "camera_fig-vm_lock.json"
    assert lock_path.exists()
    data = json.loads(lock_path.read_text())
    assert data == {"locked": True}
    handler.write.assert_called_once_with({"status": "ok"})


def test_lock_post_invalid_fig_id_returns_400():
    handler = _make_lock_handler(b'{"locked": true}')
    handler.post("../evil; rm -rf")
    handler.set_status.assert_called_once_with(400)


def test_lock_get_invalid_fig_id_returns_400():
    handler = _make_lock_handler()
    handler.get("../evil")
    handler.set_status.assert_called_once_with(400)
