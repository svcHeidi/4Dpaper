"""Tests for the color sync Tornado plugin."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def _make_handler(body_bytes: bytes) -> "ColorHandler":
    """Create a minimal ColorHandler with mocked request/response methods."""
    from dashboard.color_plugin import ColorHandler

    request = MagicMock()
    request.body = body_bytes
    handler = ColorHandler.__new__(ColorHandler)
    handler.request = request
    handler.write = MagicMock()
    handler.set_status = MagicMock()
    handler.finish = MagicMock()
    return handler


def test_color_plugin_imports():
    from dashboard.color_plugin import ColorHandler, ROUTES

    assert ColorHandler is not None
    assert len(ROUTES) == 1
    assert "/color/" in ROUTES[0][0]


def test_color_handler_post_writes_validated_json(tmp_path):
    body = json.dumps({"Vm": "viridis", "at": "not-a-map"}).encode()
    handler = _make_handler(body)
    with patch("dashboard.color_plugin._PROJECT_ROOT", tmp_path):
        handler.post("fig-vm")

    color_path = tmp_path / "state" / "color_fig-vm.json"
    assert color_path.exists()
    data = json.loads(color_path.read_text())
    assert data == {"Vm": "viridis"}
    handler.write.assert_called_once_with({"status": "ok"})


def test_color_handler_post_invalid_fig_id(tmp_path):
    body = json.dumps({"Vm": "viridis"}).encode()
    handler = _make_handler(body)
    with patch("dashboard.color_plugin._PROJECT_ROOT", tmp_path):
        handler.post("../bad")

    handler.set_status.assert_called_once_with(400)
    assert not (tmp_path / "state").exists()
