# Multi-Tab Editor — Design Spec
**Date:** 2026-03-31
**Status:** Approved

## Goal

Replace the single-file editor (which overwrites content on every file click) with a tab-based editor. Files open in tabs, stay open until explicitly closed, and the ACE editor content switches when the active tab changes.

## Architecture

**Single editor, dynamic tab bar.** One `pn.widgets.CodeEditor` instance is reused for all files. A `pn.Row` tab bar sits above the editor and is rebuilt whenever tab state changes.

### State (in `create_app()` scope)

```python
tab_order: list[str] = []      # resolved absolute paths, open order
active_path: str | None = None  # currently visible file
file_cache: dict[str, str] = {} # path → last-saved content (avoids disk reads on switch)
```

### Tab bar

`tab_bar = pn.Row(sizing_mode="stretch_width", height=30, margin=0)`

`_rebuild_tab_bar()` rebuilds `tab_bar.objects` from `tab_order` + `active_path`. Each open file becomes:
- A `pn.widgets.Button` (filename label) → calls `_on_tab_activate(path)`
- A small `pn.widgets.Button` ("×") → calls `_on_tab_close(path)`

Active tab button gets `button_type="primary"` to indicate selection; others use `"default"`.

### `editor_view` layout

```
pn.Column(
  tab_bar,
  editor,          ← ACE CodeEditor, hidden when tab_order is empty
  editor_placeholder,  ← shown when tab_order is empty
  ...
)
```

### State transitions

**File clicked in explorer** → `open_in_tabs(tab_order, path)` → save current content to cache → write cache to disk → load new content → update `active_path` → `_rebuild_tab_bar()`

**Tab label clicked** → save current → load target → update `active_path` → `_rebuild_tab_bar()`

**× clicked** → save current if it's the active tab → `after_close_tab(tab_order, active_path, closing)` → if result is None (last tab): `tab_order=[], active_path=None`; else unpack → load new active or show placeholder → `_rebuild_tab_bar()`

### Changes to `editor_tabs.py`

`after_close_tab` currently returns `None` to prevent closing the last tab. Change to return `([], "")` — callers check for empty `new_order` to show placeholder.

## Files Changed

| File | Change |
|------|--------|
| `dashboard/editor_tabs.py` | `after_close_tab` returns `([], "")` instead of `None` for last tab |
| `dashboard/app.py` | Replace single editor state with `tab_order`/`active_path`/`file_cache`; add `tab_bar`; rewrite `_on_file_click`; add `_on_tab_activate`, `_on_tab_close`, `_rebuild_tab_bar` |
| `dashboard/static/theme.css` | Tab bar button styles (active/inactive, × button) |

## Out of Scope

- Drag-reorder of tabs
- Unsaved-changes indicator (dot on tab)
- Keyboard shortcuts for tab navigation
