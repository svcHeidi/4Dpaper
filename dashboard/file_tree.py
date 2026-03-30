"""
Paper / authoring file explorer for the 4Dpapers dashboard.

VS Code–style compact tree showing only LaTeX- and Quarto-related sources
and main project configs—not the full repository.
"""
from __future__ import annotations

import html as html_mod
from pathlib import Path
from typing import Any

from bokeh.models import InlineStyleSheet

from dashboard.theme import THEME

# Panel 1.8+ ships shadow-DOM css (dist/css/button.css). :host(.solid) uses
# --surface-color (light fill). Global theme.css cannot pierce :host — use
# outline + this sheet appended after Panel's button.css.
EXPLORER_BUTTON_STYLESHEETS: tuple[InlineStyleSheet, ...] = (
    InlineStyleSheet(css="""
:host {
  background: transparent !important;
  display: block !important;
  width: 100% !important;
  box-sizing: border-box !important;
}
:host(.outline) .bk-btn,
:host(.outline) .bk-btn.bk-btn-default {
  border: none !important;
  background: transparent !important;
  background-color: transparent !important;
  box-shadow: none !important;
  padding: 0 4px 0 2px !important;
  margin: 0 !important;
  min-height: 22px !important;
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
  line-height: 20px !important;
  font-size: 11px !important;
  font-weight: 400 !important;
  text-align: left !important;
  justify-content: flex-start !important;
  align-items: center !important;
  overflow: visible !important;
  opacity: 1 !important;
  -webkit-font-smoothing: antialiased;
}
:host(.outline) .bk-btn:hover:not(:disabled) {
  background-color: rgba(255, 255, 255, 0.12) !important;
}
/* Label color must live here: global theme.css does not pierce this shadow root. */
:host(.dash-explorer-item) .bk-btn,
:host(.dash-explorer-item) .bk-btn * {
  color: #ffffff !important;
}
:host(.dash-explorer-folder) .bk-btn,
:host(.dash-explorer-folder) .bk-btn * {
  color: #fff9c4 !important;
  font-weight: 600 !important;
  font-size: 12px !important;
}
/* If host only gets `outline`, classes may mirror onto .bk-btn in some builds */
:host(.outline) .bk-btn.dash-explorer-folder,
:host(.outline) .bk-btn.dash-explorer-folder * {
  color: #fff9c4 !important;
  font-weight: 600 !important;
  font-size: 12px !important;
}
:host(.dash-explorer-file) .bk-btn,
:host(.dash-explorer-file) .bk-btn * {
  color: #b8ecff !important;
  font-size: 12px !important;
}
:host(.dash-explorer-config) .bk-btn,
:host(.dash-explorer-config) .bk-btn * {
  color: #7ec8ff !important;
  font-size: 12px !important;
}
:host(.dash-explorer-refresh) .bk-btn,
:host(.dash-explorer-refresh) .bk-btn * {
  color: #9fd4f5 !important;
}
:host(.dash-explorer-inline-action) .bk-btn,
:host(.dash-explorer-inline-action) .bk-btn * {
  color: #d4eefc !important;
}
:host(.dash-explorer-inline-active) .bk-btn,
:host(.dash-explorer-inline-active) .bk-btn * {
  color: #7efff0 !important;
}
"""),
)

HIDDEN_DIRS = {
    ".git", ".venv", "__pycache__", "_freeze", ".quarto",
    "node_modules", ".claude", ".pytest_cache", ".ipynb_checkpoints",
}

# Shown in the explorer and openable in the editor.
AUTHORING_SUFFIXES: frozenset[str] = frozenset({
    ".qmd", ".tex", ".bib", ".md", ".sty", ".cls",
})

# Quarto / LaTeX project configs (name match, case-insensitive).
AUTHORING_FILE_NAMES: frozenset[str] = frozenset({
    "_quarto.yml", "_quarto.yaml",
    "metadata.yml", "metadata.yaml",
    "custom.yml", "custom.yaml",
})

EDITABLE_EXTENSIONS = {
    ".qmd", ".bib", ".yaml", ".yml", ".css", ".tex", ".md", ".txt",
    ".sty", ".cls",
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
    ".sty": "text",
    ".cls": "text",
}


def is_editable(filename: str) -> bool:
    """Return True if the file extension is in the editable set."""
    return Path(filename).suffix.lower() in EDITABLE_EXTENSIONS


def is_authoring_file(path: Path) -> bool:
    """True for paper sources and known Quarto/LaTeX config filenames."""
    if not path.is_file():
        return False
    suf = path.suffix.lower()
    if suf in AUTHORING_SUFFIXES:
        return True
    return path.name.lower() in AUTHORING_FILE_NAMES


def subtree_contains_authoring(dir_path: Path) -> bool:
    """True if *dir_path* contains an authoring file or such a subtree."""
    if not dir_path.is_dir():
        return False
    try:
        for item in dir_path.iterdir():
            if item.is_dir():
                if item.name in HIDDEN_DIRS:
                    continue
                if subtree_contains_authoring(item):
                    return True
            elif is_authoring_file(item):
                return True
    except OSError:
        return False
    return False


def list_project_files(directory: Path) -> list[dict[str, Any]]:
    """
    List all files and directories in *directory* (legacy / tests).

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


def list_authoring_entries(directory: Path) -> list[dict[str, Any]]:
    """
    List directories and files under *directory* for the paper explorer only.

    Directories appear only if ``subtree_contains_authoring`` is true.
    Files appear only if ``is_authoring_file``.
    """
    if not directory.is_dir():
        return []

    dirs: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    try:
        items = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []

    for item in items:
        if item.is_dir():
            if item.name in HIDDEN_DIRS:
                continue
            if subtree_contains_authoring(item):
                dirs.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": True,
                    "editable": False,
                })
        elif is_authoring_file(item):
            files.append({
                "name": item.name,
                "path": str(item),
                "is_dir": False,
                "editable": True,
            })

    return dirs + files


def get_language(filename: str) -> str:
    """Return the CodeEditor language mode for a filename."""
    suffix = Path(filename).suffix.lower()
    return LANGUAGE_MAP.get(suffix, "text")


def _tabler_file_icon(path: str) -> str:
    """Tabler icon name for Panel ``Button(icon=...)`` (file rows)."""
    p = Path(path)
    name = p.name.lower()
    suf = p.suffix.lower()
    if name in AUTHORING_FILE_NAMES or suf in {".yml", ".yaml"}:
        return "settings"
    if suf in {".md", ".qmd"}:
        return "markdown"
    if suf == ".tex":
        return "file-text"
    if suf == ".bib":
        return "book"
    if suf in {".sty", ".cls"}:
        return "file-code"
    return "file-text"


import panel as pn  # noqa: E402

EXPLORER_WIDTH = 228
_EXPLORER_PAD_X = 6
_IW = EXPLORER_WIDTH - 2 * _EXPLORER_PAD_X
EXPLORER_INNER_WIDTH = _IW
_INDENT_PX = 10
_EXPLORER_ICON_SIZE = "11px"

# Inline styles beat Bootstrap .btn-light (white blocks). Color comes from CSS classes.
EXPLORER_LIST_BTN_STYLES: dict[str, str] = {
    "background": "transparent",
    "background-color": "transparent",
    "border": "none",
    "border-width": "0",
    "box-shadow": "none",
    "padding": "0 2px 0 1px",
    "margin": "0",
    "min-height": "22px",
    "height": "22px",
    "line-height": "22px",
    "text-align": "left",
    "font-weight": "400",
}

_SIDEBAR_STYLES = {
    "background": THEME["bg_sidebar"],
    "border-right": f"1px solid {THEME['border_subtle']}",
    "padding": f"4px {_EXPLORER_PAD_X}px 6px",
    "overflow-x": "hidden",
    "overflow-y": "auto",
    "box-sizing": "border-box",
}


def _row_margin(depth: int) -> tuple[int, int, int, int]:
    return (0, 0, 1, depth * _INDENT_PX)


def build_file_tree_sidebar(
    project_root: Path,
    on_file_click: callable,
    insert_figure_button: pn.widgets.Button | None = None,
) -> pn.Column:
    """
    Build a compact VS Code–style explorer for paper-related files only.

    *on_file_click* is called with (file_path: str, language: str) when
    the user clicks a file.

    If *insert_figure_button* is given, it is placed directly under **Refresh**
    (same row styling as Refresh: outline + explorer shadow stylesheet).
    """
    root_label = project_root.resolve().name.upper()
    tree_container = pn.Column(sizing_mode="stretch_width")

    def _render_tree(directory: Path, depth: int = 0):
        widgets = []
        for item in list_authoring_entries(directory):
            if item["is_dir"]:
                dir_path = Path(item["path"])
                children_col = pn.Column(visible=False, margin=(0, 0, 0, 0))
                nm = item["name"]

                toggle = pn.widgets.Button(
                    name=nm,
                    icon="chevron-right",
                    icon_size=_EXPLORER_ICON_SIZE,
                    button_type="default",
                    button_style="outline",
                    width=_IW,
                    align="start",
                    sizing_mode="fixed",
                    margin=_row_margin(depth),
                    css_classes=["dash-explorer-item", "dash-explorer-folder"],
                    styles={
                        **EXPLORER_LIST_BTN_STYLES,
                        "color": "#fff9c4",
                        "font-weight": "600",
                        "font-size": "13px",
                    },
                    stylesheets=list(EXPLORER_BUTTON_STYLESHEETS),
                )

                def _toggle_dir(
                    event,
                    col=children_col,
                    d=dir_path,
                    dep=depth,
                    btn=toggle,
                ):
                    if not col.visible:
                        if len(col) == 0:
                            col.extend(_render_tree(d, dep + 1))
                        col.visible = True
                        btn.param.update(icon="chevron-down")
                    else:
                        col.visible = False
                        btn.param.update(icon="chevron-right")

                toggle.on_click(_toggle_dir)
                widgets.append(toggle)
                widgets.append(children_col)
            else:
                fn = item["name"]
                file_classes = ["dash-explorer-item", "dash-explorer-file"]
                suf = Path(fn).suffix.lower()
                is_cfg = suf in {".yml", ".yaml"} or fn.lower() in AUTHORING_FILE_NAMES
                if is_cfg:
                    file_classes.append("dash-explorer-config")
                file_styles = {
                    **EXPLORER_LIST_BTN_STYLES,
                    "font-size": "13px",
                    "color": "#7ec8ff" if is_cfg else "#b8ecff",
                }
                btn = pn.widgets.Button(
                    name=fn,
                    icon=_tabler_file_icon(item["path"]),
                    icon_size=_EXPLORER_ICON_SIZE,
                    button_type="default",
                    button_style="outline",
                    width=_IW,
                    align="start",
                    sizing_mode="fixed",
                    margin=_row_margin(depth),
                    css_classes=file_classes,
                    styles=file_styles,
                    stylesheets=list(EXPLORER_BUTTON_STYLESHEETS),
                )

                def _open_file(event, path=item["path"], name=item["name"]):
                    on_file_click(path, get_language(name))

                btn.on_click(_open_file)
                widgets.append(btn)

        return widgets

    refresh_btn = pn.widgets.Button(
        name="Refresh",
        icon="refresh",
        icon_size=_EXPLORER_ICON_SIZE,
        button_type="default",
        button_style="outline",
        width=_IW,
        sizing_mode="fixed",
        margin=(0, 0, 4, 0),
        css_classes=["dash-explorer-item", "dash-explorer-refresh"],
        styles={**EXPLORER_LIST_BTN_STYLES, "color": "#9fd4f5", "font-size": "13px"},
        stylesheets=list(EXPLORER_BUTTON_STYLESHEETS),
    )

    def _on_refresh(event):
        tree_container.clear()
        tree_container.extend(_render_tree(project_root))

    refresh_btn.on_click(_on_refresh)
    tree_container.extend(_render_tree(project_root))

    title_esc = html_mod.escape(root_label)
    explorer_top: list[Any] = [
        pn.pane.HTML(
            f'<div class="dash-explorer-section-title">'
            f'<i class="bi bi-chevron-down dash-explorer-title-chevron"></i>'
            f"<span>{title_esc}</span></div>",
            sizing_mode="stretch_width",
        ),
        refresh_btn,
    ]
    if insert_figure_button is not None:
        explorer_top.append(insert_figure_button)
    explorer_top.extend([
        pn.layout.Divider(margin=(2, 0, 4, 0)),
        tree_container,
    ])
    return pn.Column(
        *explorer_top,
        width=EXPLORER_WIDTH,
        sizing_mode="stretch_height",
        styles=_SIDEBAR_STYLES,
    )
