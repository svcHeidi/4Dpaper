"""Smoke tests for dashboard pages — verify they build without crashing."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


FAKE_CONFIG = {
    "cardiacfoam_root": "/fake/cf",
    "quarto_paper_path": "/fake/paper.qmd",
}


def test_paper_page_builds():
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        from dashboard.pages.paper_page import build_paper_page
        layout, _page = build_paper_page(config=FAKE_CONFIG)
    assert layout is not None


def test_paper_page_has_paper_view_tab():
    """Paper View tab must exist in the page layout."""
    from importlib import reload
    import dashboard.pages.paper_page as pp_mod
    reload(pp_mod)
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        layout, page = pp_mod.build_paper_page(config=FAKE_CONFIG)

    import panel as pn

    def _find_tabs(obj):
        if isinstance(obj, pn.Tabs):
            return obj
        children = getattr(obj, "objects", None) or []
        for child in children:
            result = _find_tabs(child)
            if result is not None:
                return result
        return None

    tabs = _find_tabs(layout)
    assert tabs is not None, "Expected a pn.Tabs widget in the paper page layout"
    tab_names = getattr(tabs, "_names", [])
    assert any("Paper" in str(n) for n in tab_names), (
        f"Expected a 'Paper View' tab, got: {tab_names}"
    )


def test_paper_page_enable_paper_view():
    """_enable_paper_view must set _paper_view_enabled=True."""
    from importlib import reload
    import dashboard.pages.paper_page as pp_mod
    reload(pp_mod)
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        _, page = pp_mod.build_paper_page(config=FAKE_CONFIG)

    assert not page._paper_view_enabled
    # Patch the periodic callback so it doesn't actually start
    with patch("panel.state.add_periodic_callback", return_value=None):
        with patch.object(page, "_tick_paper_view"):
            page._enable_paper_view()
    assert page._paper_view_enabled
