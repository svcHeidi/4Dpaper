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


import panel as pn  # noqa: E402

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
