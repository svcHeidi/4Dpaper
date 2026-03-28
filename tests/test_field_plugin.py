"""Tests for the field sync Tornado plugin."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_handler(body_bytes: bytes) -> "FieldHandler":
    """Create a minimal FieldHandler with mocked request and response methods."""
    from dashboard.field_plugin import FieldHandler
    request = MagicMock()
    request.body = body_bytes
    handler = FieldHandler.__new__(FieldHandler)
    handler.request = request
    handler.write = MagicMock()
    handler.set_status = MagicMock()
    handler.finish = MagicMock()
    return handler


def test_field_plugin_imports():
    from dashboard.field_plugin import FieldHandler, ROUTES
    assert FieldHandler is not None
    assert len(ROUTES) == 1
    assert "/field/" in ROUTES[0][0]


def test_field_handler_post_writes_json(tmp_path):
    """Happy path: POST writes field state JSON to correct path."""
    body = json.dumps({
        "field": "Vm",
        "time": "5"
    }).encode()
    handler = _make_handler(body)
    with patch("dashboard.field_plugin._PROJECT_ROOT", tmp_path):
        handler.post("fig-vm")
    field_path = tmp_path / "state" / "field_fig-vm.json"
    assert field_path.exists(), "field JSON not written"
    data = json.loads(field_path.read_text())
    assert data["field"] == "Vm"
    assert data["time"] == "5"
    handler.write.assert_called_once_with({"status": "ok"})


def test_field_handler_post_partial_update(tmp_path):
    """Update only the time field should preserve the existing field field."""
    field_path = tmp_path / "state" / "field_fig-vm.json"
    field_path.parent.mkdir(parents=True, exist_ok=True)
    field_path.write_text(json.dumps({"field": "Vm", "time": "2"}))
    
    body = json.dumps({
        "time": "10"
    }).encode()
    handler = _make_handler(body)
    with patch("dashboard.field_plugin._PROJECT_ROOT", tmp_path):
        handler.post("fig-vm")
        
    data = json.loads(field_path.read_text())
    assert data["field"] == "Vm"
    assert data["time"] == "10"
    handler.write.assert_called_once_with({"status": "ok"})

def test_field_handler_post_invalid_json(tmp_path):
    """POST with non-JSON body returns 400."""
    handler = _make_handler(b"not json")
    with patch("dashboard.field_plugin._PROJECT_ROOT", tmp_path):
        handler.post("fig-vm")
    handler.set_status.assert_called_once_with(400)
    written = handler.write.call_args[0][0]
    assert written["status"] == "error"

def test_field_handler_post_invalid_fig_id(tmp_path):
    """POST with path-traversal fig_id returns 400."""
    body = json.dumps({
        "field": "Vm"
    }).encode()
    handler = _make_handler(body)
    with patch("dashboard.field_plugin._PROJECT_ROOT", tmp_path):
        handler.post("../../etc/passwd")
    handler.set_status.assert_called_once_with(400)
    # No file should be written
    assert not (tmp_path / "state").exists()
