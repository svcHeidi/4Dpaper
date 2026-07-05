"""Regression checks for frontend deployment auth wiring."""
from __future__ import annotations

from pathlib import Path


def test_auth_script_is_loaded_before_dashboard_clients():
    path = Path(__file__).parent.parent / "dashboard" / "static" / "index.html"
    text = path.read_text(encoding="utf-8")

    auth_idx = text.index('dashboard/static/js/auth.js')
    chat_idx = text.index('dashboard/static/js/chat.js')
    figure_idx = text.index('dashboard/static/js/insert-figure-overlay.js')

    assert auth_idx < chat_idx
    assert auth_idx < figure_idx


def test_auth_script_covers_header_and_cookie_paths():
    path = Path(__file__).parent.parent / "dashboard" / "static" / "js" / "auth.js"
    text = path.read_text(encoding="utf-8")

    assert "X-API-Key" in text
    assert "document.cookie" in text
    assert "window.fetch = authorizedFetch" in text
    assert "fourd_api_key" in text


def test_settings_panel_exposes_deployment_api_key_controls():
    path = Path(__file__).parent.parent / "dashboard" / "static" / "index.html"
    text = path.read_text(encoding="utf-8")

    assert 'id="deploymentApiKey"' in text
    assert 'id="deploymentApiKeySave"' in text
    assert 'id="deploymentApiKeyClear"' in text
    assert "same-origin cookie" in text
