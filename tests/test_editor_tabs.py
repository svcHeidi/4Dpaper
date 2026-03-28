"""Tests for dashboard/editor_tabs.py (multi-file tab order)."""
from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.editor_tabs import after_close_tab, open_in_tabs, resolve_path


@pytest.fixture
def paths(tmp_path: Path) -> tuple[str, str, str]:
    a = tmp_path / "one.qmd"
    b = tmp_path / "two.qmd"
    c = tmp_path / "three.bib"
    a.write_text("a", encoding="utf-8")
    b.write_text("b", encoding="utf-8")
    c.write_text("c", encoding="utf-8")
    return str(a), str(b), str(c)


def test_resolve_path(paths: tuple[str, str, str]) -> None:
    a, _, _ = paths
    assert resolve_path(a) == str(Path(a).resolve())


def test_open_in_tabs_appends(paths: tuple[str, str, str]) -> None:
    a, b, _ = paths
    ra, rb = resolve_path(a), resolve_path(b)
    order, target = open_in_tabs([a], b)
    assert target == rb
    assert order == [ra, rb]


def test_open_in_tabs_focuses_existing(paths: tuple[str, str, str]) -> None:
    a, b, _ = paths
    ra, rb = resolve_path(a), resolve_path(b)
    order0 = [ra, rb]
    order, target = open_in_tabs(order0, a)
    assert order == order0
    assert target == ra


def test_after_close_tab_last_only_returns_none(paths: tuple[str, str, str]) -> None:
    a, _, _ = paths
    ra = resolve_path(a)
    assert after_close_tab([ra], ra, ra) is None


def test_after_close_tab_inactive(paths: tuple[str, str, str]) -> None:
    a, b, _ = paths
    ra, rb = resolve_path(a), resolve_path(b)
    new_order, new_active = after_close_tab([ra, rb], ra, rb)
    assert new_order == [ra]
    assert new_active == ra


def test_after_close_tab_active_pick_left_neighbor(paths: tuple[str, str, str]) -> None:
    a, b, c = paths
    ra, rb, rc = resolve_path(a), resolve_path(b), resolve_path(c)
    new_order, new_active = after_close_tab([ra, rb, rc], rb, rb)
    assert new_order == [ra, rc]
    assert new_active == ra


def test_after_close_tab_active_first_picks_second(paths: tuple[str, str, str]) -> None:
    a, b, _ = paths
    ra, rb = resolve_path(a), resolve_path(b)
    new_order, new_active = after_close_tab([ra, rb], ra, ra)
    assert new_order == [rb]
    assert new_active == rb


def test_after_close_unknown_tab_unchanged(paths: tuple[str, str, str]) -> None:
    a, b, _ = paths
    ra, rb = resolve_path(a), resolve_path(b)
    ghost = str(Path(a).parent / "nope.qmd")
    new_order, new_active = after_close_tab([ra, rb], ra, ghost)
    assert new_order == [ra, rb]
    assert new_active == ra
