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
