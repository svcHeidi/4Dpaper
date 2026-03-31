"""Smoke tests for activity-bar layout — settings page and app assembly."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import panel as pn


def test_settings_page_builds():
    from dashboard.pages.settings_page import build_settings_page
    widget = build_settings_page()
    assert widget is not None
    assert isinstance(widget, pn.viewable.Viewable)


def test_split_config_script_contains_panels():
    """_build_split_config_script embeds all panel IDs and sets SPLIT_CONFIG."""
    from dashboard.app import _build_split_config_script
    panels = [
        {"id": "explorer", "icon": "📁", "label": "Files"},
        {"id": "editor",   "icon": "📝", "label": "Editor"},
    ]
    script = _build_split_config_script(panels, default_panel="explorer")
    assert "explorer" in script
    assert "editor" in script
    assert "SPLIT_CONFIG" in script
    assert "<script>" in script


def test_build_activity_bar_html_has_buttons():
    """_build_activity_bar_html returns one button per panel; bottom items in activity-bar-bottom."""
    from dashboard.app import _build_activity_bar_html
    panels = [
        {"id": "explorer", "icon": "📁", "label": "Files"},
        {"id": "settings", "icon": "⚙️", "label": "Settings", "bottom": True},
    ]
    html = _build_activity_bar_html(panels)
    assert 'data-panel-id="explorer"' in html
    assert 'data-panel-id="settings"' in html
    assert "activity-bar-bottom" in html
