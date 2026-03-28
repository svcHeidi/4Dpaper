# Overleaf-Style UI — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the specialized figure-browser sidebar with a full project file tree, making the dashboard feel like Overleaf/VS Code — file browser on left, multi-file editor in center, paper preview on right.

**Architecture:** New `dashboard/file_tree.py` module builds a Panel sidebar showing the project directory tree. Clicking an editable file opens it in the existing CodeEditor. The figure-insertion form from `figure_browser.py` moves into a modal triggered by a toolbar button. `app.py` wires everything together.

**Tech Stack:** Panel (Python), Bokeh widgets, existing CodeEditor

---

### Task 1: Create the file tree widget

Build a new module that recursively lists the project directory as a clickable tree.

**Files:**
- Create: `dashboard/file_tree.py`
- Test: `tests/test_file_tree.py`

**Step 1: Write the failing tests**

Create `tests/test_file_tree.py`:

```python
"""Tests for dashboard/file_tree.py"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.file_tree import list_project_files, is_editable, HIDDEN_DIRS


class TestListProjectFiles:
    def test_lists_files_in_directory(self, tmp_path):
        (tmp_path / "report.qmd").write_text("# Hello")
        (tmp_path / "refs.bib").write_text("@article{}")
        result = list_project_files(tmp_path)
        names = [r["name"] for r in result]
        assert "report.qmd" in names
        assert "refs.bib" in names

    def test_lists_subdirectories(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "case.foam").write_text("")
        result = list_project_files(tmp_path)
        dir_names = [r["name"] for r in result if r["is_dir"]]
        assert "data" in dir_names

    def test_hides_filtered_directories(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".venv").mkdir()
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "src").mkdir()
        result = list_project_files(tmp_path)
        dir_names = [r["name"] for r in result if r["is_dir"]]
        assert ".git" not in dir_names
        assert ".venv" not in dir_names
        assert "__pycache__" not in dir_names
        assert "src" in dir_names

    def test_sorts_dirs_first_then_files(self, tmp_path):
        (tmp_path / "zebra.qmd").write_text("")
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta.bib").write_text("")
        result = list_project_files(tmp_path)
        # Dirs come first, then files, both alphabetically
        assert result[0]["name"] == "alpha"
        assert result[0]["is_dir"] is True


class TestIsEditable:
    def test_qmd_is_editable(self):
        assert is_editable("report.qmd") is True

    def test_bib_is_editable(self):
        assert is_editable("refs.bib") is True

    def test_yaml_is_editable(self):
        assert is_editable("config.yaml") is True

    def test_css_is_editable(self):
        assert is_editable("style.css") is True

    def test_png_is_not_editable(self):
        assert is_editable("figure.png") is False

    def test_py_is_not_editable(self):
        assert is_editable("script.py") is False

    def test_html_is_not_editable(self):
        assert is_editable("output.html") is False
```

**Step 2: Run tests — verify they fail**

Run: `.venv/bin/python -m pytest tests/test_file_tree.py -v`
Expected: FAIL — `dashboard.file_tree` does not exist

**Step 3: Implement `dashboard/file_tree.py`**

```python
"""
Project file tree sidebar for the 4Dpapers dashboard.

Provides an Overleaf-style file browser showing the full project directory.
Clicking an editable file opens it in the code editor.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

HIDDEN_DIRS = {
    ".git", ".venv", "__pycache__", "_freeze", ".quarto",
    "node_modules", ".claude", ".pytest_cache", ".ipynb_checkpoints",
}

EDITABLE_EXTENSIONS = {
    ".qmd", ".bib", ".yaml", ".yml", ".css", ".tex", ".md", ".txt",
}

LANGUAGE_MAP = {
    ".qmd": "markdown",
    ".md": "markdown",
    ".txt": "text",
    ".bib": "latex",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".css": "css",
    ".tex": "latex",
}


def is_editable(filename: str) -> bool:
    """Return True if the file extension is in the editable set."""
    return Path(filename).suffix.lower() in EDITABLE_EXTENSIONS


def list_project_files(directory: Path) -> list[dict[str, Any]]:
    """
    List files and directories in *directory*, excluding hidden/build dirs.

    Returns a list of dicts with keys: name, path, is_dir, editable.
    Sorted: directories first (alphabetically), then files (alphabetically).
    """
    if not directory.is_dir():
        return []

    dirs = []
    files = []
    for item in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if item.name.startswith(".") and item.name in HIDDEN_DIRS:
            continue
        if item.is_dir():
            if item.name in HIDDEN_DIRS:
                continue
            dirs.append({
                "name": item.name,
                "path": str(item),
                "is_dir": True,
                "editable": False,
            })
        else:
            files.append({
                "name": item.name,
                "path": str(item),
                "is_dir": False,
                "editable": is_editable(item.name),
            })

    return dirs + files


def get_language(filename: str) -> str:
    """Return the CodeEditor language mode for a filename."""
    suffix = Path(filename).suffix.lower()
    return LANGUAGE_MAP.get(suffix, "text")
```

**Step 4: Run tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/test_file_tree.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add dashboard/file_tree.py tests/test_file_tree.py
git commit -m "feat: add file tree module with project listing and editability checks"
```

---

### Task 2: Build the Panel file tree sidebar widget

Add a `build_file_tree_sidebar()` function that creates the interactive Panel widget.

**Files:**
- Modify: `dashboard/file_tree.py` (add `build_file_tree_sidebar`)

**Step 1: Add the Panel sidebar builder**

Append to `dashboard/file_tree.py`:

```python
import panel as pn


_W = 280  # sidebar width in pixels
_IW = _W - 20  # inner widget width

_SIDEBAR_STYLES = {
    "background": "#1a1a1a",
    "border-right": "1px solid #333",
    "padding": "10px",
    "overflow-x": "hidden",
    "overflow-y": "auto",
    "box-sizing": "border-box",
}


def build_file_tree_sidebar(
    project_root: Path,
    on_file_click: callable,
) -> pn.Column:
    """
    Build a file tree sidebar rooted at *project_root*.

    *on_file_click* is called with (file_path: str, language: str) when
    the user clicks an editable file.
    """
    tree_container = pn.Column(sizing_mode="stretch_width")

    def _render_tree(directory: Path, depth: int = 0):
        """Render one level of the tree into buttons."""
        items = list_project_files(directory)
        widgets = []
        indent = "  " * depth

        for item in items:
            if item["is_dir"]:
                # Directory: collapsible toggle
                dir_path = Path(item["path"])
                children_col = pn.Column(visible=False, margin=(0, 0, 0, 16))

                toggle = pn.widgets.Button(
                    name=f"{indent}📁 {item['name']}",
                    button_type="light",
                    width=_IW,
                    align="start",
                    styles={"text-align": "left", "font-size": "12px"},
                )

                def _toggle_dir(event, col=children_col, d=dir_path, dep=depth):
                    if not col.visible:
                        if len(col) == 0:
                            col.extend(_render_tree(d, dep + 1))
                        col.visible = True
                    else:
                        col.visible = False

                toggle.on_click(_toggle_dir)
                widgets.append(toggle)
                widgets.append(children_col)
            elif item["editable"]:
                btn = pn.widgets.Button(
                    name=f"{indent}📄 {item['name']}",
                    button_type="light",
                    width=_IW,
                    align="start",
                    styles={"text-align": "left", "font-size": "12px"},
                )

                def _open_file(event, path=item["path"], name=item["name"]):
                    on_file_click(path, get_language(name))

                btn.on_click(_open_file)
                widgets.append(btn)
            else:
                # Non-editable file: greyed out label
                widgets.append(pn.pane.Markdown(
                    f"{indent}<span style='color:#666;font-size:12px;'>"
                    f"  {item['name']}</span>",
                    width=_IW,
                ))
        return widgets

    refresh_btn = pn.widgets.Button(
        name="🔄 Refresh",
        button_type="light",
        width=_IW,
    )

    def _on_refresh(event):
        tree_container.clear()
        tree_container.extend(_render_tree(project_root))

    refresh_btn.on_click(_on_refresh)
    tree_container.extend(_render_tree(project_root))

    return pn.Column(
        pn.pane.Markdown("### Project Files", styles={"color": "#ddd"}),
        refresh_btn,
        pn.layout.Divider(margin=(6, 0)),
        tree_container,
        width=_W,
        sizing_mode="stretch_height",
        styles=_SIDEBAR_STYLES,
    )
```

**Step 2: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add dashboard/file_tree.py
git commit -m "feat: add Panel file tree sidebar widget"
```

---

### Task 3: Refactor figure insertion into a modal dialog

Extract the figure-insertion form from `figure_browser.py` into a toggleable panel that appears when the user clicks "Insert Figure".

**Files:**
- Modify: `dashboard/figure_browser.py` — extract form-building into `build_figure_insert_form(editor, qmd_path, config)` that returns a `pn.Column` (not the full sidebar)

**Step 1: Refactor `figure_browser.py`**

Keep all the existing functions (`find_foam_files`, `get_timesteps`, `copy_case_data`, `generate_shortcode`). Rename `build_figure_browser` to `build_figure_insert_form` and have it return just the form widgets (not the full sidebar column with its own width/styles).

The key change: remove `width=_W`, `sizing_mode="stretch_height"`, and `styles=_SIDEBAR_STYLES` from the returned Column. The caller (app.py) will decide how to present it (as a modal or toggle panel).

**Step 2: Run existing figure_browser tests**

Run: `.venv/bin/python -m pytest tests/test_figure_browser.py -v`
Expected: All tests PASS (they test helper functions, not the UI builder)

**Step 3: Commit**

```bash
git add dashboard/figure_browser.py
git commit -m "refactor: extract figure insertion form for use in modal"
```

---

### Task 4: Wire everything together in `app.py`

Replace the figure-browser sidebar with the file tree. Add multi-file editing support and an "Insert Figure" button that toggles the figure-insertion form.

**Files:**
- Modify: `dashboard/app.py`

**Step 1: Update `app.py` imports**

```python
# Replace:
from dashboard.figure_browser import build_figure_browser
# With:
from dashboard.file_tree import build_file_tree_sidebar, get_language
from dashboard.figure_browser import build_figure_insert_form
```

**Step 2: Add file-switching logic**

In `create_app()`, add:

```python
# Track the currently open file path
current_file = {"path": str(qmd_path)}

def _on_file_click(file_path: str, language: str):
    # Auto-save current file before switching
    if current_file["path"]:
        Path(current_file["path"]).write_text(editor.value, encoding="utf-8")
    # Load new file
    current_file["path"] = file_path
    editor.value = Path(file_path).read_text(encoding="utf-8")
    editor.language = language
    editor_title.object = f"### `{Path(file_path).name}`"
```

**Step 3: Replace sidebar**

```python
# Replace:
sidebar = build_figure_browser(editor, qmd_path, config)
# With:
sidebar = build_file_tree_sidebar(
    project_root=qmd_path.parent,
    on_file_click=_on_file_click,
)
```

**Step 4: Add "Insert Figure" toggle button + form panel**

```python
insert_fig_btn = pn.widgets.Toggle(
    name="📐 Insert Figure",
    value=False,
    button_type="default",
    width=140,
)

figure_form = build_figure_insert_form(editor, qmd_path, config)
figure_form.visible = False
insert_fig_btn.param.watch(
    lambda e: setattr(figure_form, "visible", e.new), "value"
)
```

Add `insert_fig_btn` to the toolbar row and `figure_form` below the editor.

**Step 5: Update Save button to save current file**

```python
def _on_save(_event):
    try:
        Path(current_file["path"]).write_text(editor.value, encoding="utf-8")
        save_status.object = f"✓ Saved {Path(current_file['path']).name}"
        save_status.alert_type = "success"
    except Exception as exc:
        save_status.object = f"✗ Save failed: {exc}"
        save_status.alert_type = "danger"
    save_status.visible = True
```

**Step 6: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

**Step 7: Manual smoke test**

```bash
panel serve dashboard/app.py --plugins dashboard.camera_plugin --static-dirs output=_output --show --port 5006
```

Verify:
- Left sidebar shows the project file tree
- Clicking `analysis_report.qmd` opens it in the editor
- Clicking `_quarto.yml` opens the YAML config
- Clicking "Insert Figure" toggle shows the figure-insertion form
- Save button saves to the currently open file
- Rebuild HTML / Export PDF still work

**Step 8: Commit**

```bash
git add dashboard/app.py
git commit -m "feat: Overleaf-style file tree sidebar with multi-file editing"
```
