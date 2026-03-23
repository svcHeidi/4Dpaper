"""Tests for panel camera sync mode."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSnippetForSync:
    def test_wildcard_ack_accepted(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        # The ack filter must accept wildcard "*" from sync panels
        assert 'fig_id!=="*"' in snippet or "fig_id !== \"*\"" in snippet

    def test_camera_apply_listener_present(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        assert "4dpaper-camera-apply" in snippet

    def test_camera_apply_sets_camera_position(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        assert "setPosition" in snippet
        assert "setFocalPoint" in snippet
        assert "setViewUp" in snippet
