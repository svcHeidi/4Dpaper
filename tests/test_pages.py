"""Smoke tests for dashboard pages — verify they build without crashing."""
from __future__ import annotations

import sys
import unittest.mock
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


def test_paper_page_enable_paper_view_idempotent():
    """Calling _enable_paper_view twice must not register two callbacks."""
    from importlib import reload
    import dashboard.pages.paper_page as pp_mod
    reload(pp_mod)
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        _, page = pp_mod.build_paper_page(config=FAKE_CONFIG)

    cb_mock = None

    def fake_add_periodic(fn, period):
        nonlocal cb_mock
        cb_mock = fn
        return object()

    with patch("panel.state.add_periodic_callback", side_effect=fake_add_periodic):
        with patch.object(page, "_tick_paper_view"):
            page._enable_paper_view()
            page._enable_paper_view()  # second call must be a no-op

    # add_periodic_callback should only have been called once
    assert cb_mock is not None


def test_paper_page_tick_blocked_while_building():
    """_tick_paper_view must not launch a build if one is already in progress."""
    from importlib import reload
    import dashboard.pages.paper_page as pp_mod
    reload(pp_mod)
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        _, page = pp_mod.build_paper_page(config=FAKE_CONFIG)

    page._paper_view_building = True
    launched = []

    with patch("threading.Thread") as mock_thread:
        mock_thread.return_value.start = lambda: launched.append(1)
        with patch("panel.state.add_periodic_callback", return_value=None):
            with patch.object(pp_mod.pn.state.__class__, "curdoc", new_callable=lambda: property(lambda self: None), create=True):
                page._tick_paper_view()

    assert len(launched) == 0, "_tick_paper_view must not start a thread when already building"


def test_paper_page_building_flag_reset_on_error():
    """_run_paper_view_build must reset _paper_view_building even when quarto raises."""
    from importlib import reload
    import dashboard.pages.paper_page as pp_mod
    reload(pp_mod)
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        _, page = pp_mod.build_paper_page(config=FAKE_CONFIG)

    page._paper_view_building = True
    page._paper_view_start = __import__("time").time()

    with patch("dashboard.utils.run_quarto_render", side_effect=RuntimeError("boom")):
        page._run_paper_view_build(doc=None)

    assert not page._paper_view_building, "_paper_view_building must be False after exception"


def test_paper_page_building_flag_reset_on_failure():
    """_run_paper_view_build must reset _paper_view_building when exit code != 0."""
    from importlib import reload
    import dashboard.pages.paper_page as pp_mod
    reload(pp_mod)
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        _, page = pp_mod.build_paper_page(config=FAKE_CONFIG)

    page._paper_view_building = True
    page._paper_view_start = __import__("time").time()

    with patch("dashboard.utils.run_quarto_render", return_value=1):
        page._run_paper_view_build(doc=None)

    assert not page._paper_view_building


def test_paper_page_finish_paper_view_updates_iframe():
    """_finish_paper_view must update the iframe object with a cache-busted URL."""
    from importlib import reload
    import dashboard.pages.paper_page as pp_mod
    reload(pp_mod)
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        _, page = pp_mod.build_paper_page(config=FAKE_CONFIG)

    with patch("threading.Timer") as mock_timer_cls:
        mock_timer_cls.return_value.start = lambda: None
        page._finish_paper_view(ts=12345, elapsed=10)

    assert "12345" in page._paper_view_iframe.object
    assert "analysis_report-paperview.html" in page._paper_view_iframe.object


def test_paper_page_finish_paper_view_cancels_previous_timer():
    """_finish_paper_view must cancel any previous hide timer before setting a new one."""
    from importlib import reload
    import dashboard.pages.paper_page as pp_mod
    reload(pp_mod)
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        _, page = pp_mod.build_paper_page(config=FAKE_CONFIG)

    # Plant a mock timer as if a previous build already set one
    old_timer = unittest.mock.MagicMock()
    page._paper_view_hide_timer = old_timer

    with patch("threading.Timer") as mock_timer_cls:
        mock_timer_cls.return_value.start = lambda: None
        page._finish_paper_view(ts=99999, elapsed=5)

    old_timer.cancel.assert_called_once()


def test_paper_page_status_visible_during_build():
    """_update_paper_view_status must make the status pane visible."""
    from importlib import reload
    import dashboard.pages.paper_page as pp_mod
    reload(pp_mod)
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        _, page = pp_mod.build_paper_page(config=FAKE_CONFIG)

    assert not page._paper_view_status.visible
    page._paper_view_building = True
    page._paper_view_start = __import__("time").time()
    page._update_paper_view_status("Building…", "warning")
    assert page._paper_view_status.visible
