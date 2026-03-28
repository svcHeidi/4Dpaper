"""Pure helpers for VS Code–style editor tab order (multi-file open in one window)."""
from __future__ import annotations

from pathlib import Path


def resolve_path(path: str) -> str:
    return str(Path(path).resolve())


def open_in_tabs(tab_order: list[str], file_path: str) -> tuple[list[str], str]:
    """
    Return ``(new_order, path_to_activate)``.
    If *file_path* is already open, order unchanged; otherwise append resolved path.
    """
    r = resolve_path(file_path)
    order = [resolve_path(p) for p in tab_order]
    if r in order:
        return order, r
    return order + [r], r


def after_close_tab(
    tab_order: list[str],
    active_path: str,
    closing: str,
) -> tuple[list[str], str] | None:
    """
    Remove *closing* from tabs. Returns ``(new_order, new_active)`` or ``None`` if
    the last tab cannot be closed.
    """
    order = [resolve_path(p) for p in tab_order]
    r_close = resolve_path(closing)
    if len(order) <= 1:
        return None
    if r_close not in order:
        return order, resolve_path(active_path)
    new_order = [p for p in order if p != r_close]
    ap = resolve_path(active_path)
    if ap != r_close:
        return new_order, ap
    idx = order.index(r_close)
    if idx > 0:
        new_active = order[idx - 1]
    else:
        new_active = order[1]
    return new_order, new_active
