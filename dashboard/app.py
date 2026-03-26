"""
4Dpaper Dashboard — main Panel app.

Launch with:
    panel serve dashboard/app.py --plugins dashboard.plugins \
        --static-dirs output=_output assets=dashboard/static state=state --show --port 5006
from the 4Dpapers repository root.
"""
from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import panel as pn

from dashboard.utils import load_config
from dashboard.pages.paper_page import build_paper_page
from dashboard.file_tree import build_file_tree_sidebar, get_language

_RAW_CSS = """
#header{display:none!important;height:0!important}
html,body{overflow-x:hidden!important;margin:0!important;padding:0!important;background:#000!important;height:100%!important}
.container-fluid{padding:0!important;max-width:100%!important;height:100%!important;min-height:0!important;display:flex!important;flex-direction:column!important}
#main{padding:0!important;flex:1 1 auto!important;min-height:0!important;display:flex!important;flex-direction:column!important}
div.ace_editor{overflow:hidden!important}
div.ace_editor div.ace_scroller{overflow-x:hidden!important}
div.ace_editor div.ace_scrollbar-h{display:none!important;height:0!important}
div.ace_editor div.ace_content{overflow-x:hidden!important}
/* Ensure Ace cursor is visible on dark backgrounds */
.ace_editor .ace_cursor{border-left:2px solid #e6e6e6!important}
.ace_editor.ace_focus .ace_cursor{border-left:2px solid #ffffff!important}
.ace_editor .ace_cursor{opacity:1!important}
.ace_editor .ace_hidden-cursors .ace_cursor{opacity:1!important}
#split-status{color:#8ab4ff;font-size:10px;font-family:monospace;opacity:0.9;margin-left:8px;}
/* VS Code–like shell: toolbar + body row fill viewport; panes stretch vertically */
.app-shell{height:100vh!important;min-height:0!important;display:flex!important;flex-direction:column!important;box-sizing:border-box!important}
.app-shell .body-row{flex:1 1 auto!important;min-height:0!important;width:100%!important;display:flex!important;flex-direction:row!important;align-items:stretch!important;position:relative!important;overflow:visible!important}
/* Panes may shrink; gutters keep fixed width (do not apply min-width:0 to gutters) */
.app-shell .body-row > *:not(.split-gutter){min-height:0!important;min-width:0!important}
.split-gutter{
  flex:0 0 8px!important;min-width:8px!important;max-width:8px!important;width:8px!important;
  min-height:0!important;padding:0!important;margin:0!important;box-sizing:border-box!important;
  cursor:ew-resize!important;user-select:none!important;-webkit-user-select:none!important;
  background:rgba(55,65,80,0.55)!important;
  border-left:1px solid rgba(255,255,255,0.2)!important;border-right:1px solid rgba(0,0,0,0.35)!important;
}
.split-gutter:hover,.split-gutter.__split-dragging{background:rgba(13,110,253,0.45)!important}
.split-gutter .__split_handle{
  min-height:100%!important;height:100%!important;width:100%!important;
  pointer-events:auto!important;cursor:ew-resize!important;
}
"""

pn.extension(
    "codeeditor",
    sizing_mode="stretch_width",
    template="bootstrap",
    raw_css=[_RAW_CSS],
    js_files={
        "insert_figure": "/assets/insert_figure_overlay.js?v=1",
        # Defer split_pane until .app-shell exists (see split_loader.js).
        "split_loader": "/assets/split_loader.js?v=5",
    },
)


def _split_gutter(between: str) -> pn.Column:
    """Fixed-width flex sibling between panes (hit target for resize; no iframe). *between*: left-center | center-right."""
    handle = pn.pane.HTML(
        '<div class="__split_handle" role="separator" aria-orientation="vertical" title="Drag to resize panes"></div>',
        sizing_mode="stretch_both",
        margin=0,
    )
    return pn.Column(
        handle,
        sizing_mode="stretch_both",
        width=8,
        margin=0,
        css_classes=["split-gutter", f"split-gutter--between-{between}"],
        styles={
            "flex": "0 0 8px",
            "min-width": "8px",
            "max-width": "8px",
            "width": "8px",
            "min-height": "0",
            "padding": "0",
        },
    )


def create_app():
    config = load_config()
    qmd_path = Path(config["quarto_paper_path"])

    qmd_content = qmd_path.read_text() if qmd_path.exists() else "# File not found"
    editor = pn.widgets.CodeEditor(
        value=qmd_content, language="markdown",
        sizing_mode="stretch_both", min_height=600, theme="tomorrow_night",
    )

    current_file = {"path": str(qmd_path)}

    def _on_file_click(file_path: str, language: str):
        if current_file["path"]:
            Path(current_file["path"]).write_text(editor.value, encoding="utf-8")
        current_file["path"] = file_path
        editor.value = Path(file_path).read_text(encoding="utf-8")
        editor.language = language

    paper_content, paper_page = build_paper_page(config)

    toolbar = pn.Row(
        pn.layout.HSpacer(),
        paper_page.rebuild_btn, paper_page.export_btn,
        paper_page.pdf_link,
        pn.pane.HTML('<span style="color:#555;font-size:14px">│</span>', margin=(2, 4)),
        pn.pane.HTML(
            '<span id="split-status" class="split-status-target" data-split-status="1">split: …</span>',
        ),
        sizing_mode="stretch_width", height=28,
        styles={"padding": "1px 6px", "background": "#111", "border-bottom": "1px solid #333"},
    )

    sidebar_files = build_file_tree_sidebar(
        project_root=qmd_path.parent, on_file_click=_on_file_click,
    )
    sidebar_files.sizing_mode = "stretch_both"
    sidebar_files.styles = {**getattr(sidebar_files, "styles", {}), "min-height": "0"}

    editor_panel = pn.Column(
        editor,
        sizing_mode="stretch_both",
        min_width=360,
        styles={"min-height": "0", "flex": "1 1 auto"},
        css_classes=["editor-pane"],
    )
    center_tabs = pn.Tabs(
        ("Editor", editor_panel),
        dynamic=False,
        sizing_mode="stretch_both",
        styles={"min-height": "0", "flex": "1 1 auto"},
    )

    paper_panel = pn.Column(
        paper_content,
        sizing_mode="stretch_both",
        min_width=360,
        styles={"min-height": "0", "flex": "1 1 auto"},
        css_classes=["preview-pane"],
    )
    right_tabs = pn.Tabs(
        ("Preview", paper_panel),
        dynamic=False,
        sizing_mode="stretch_both",
        styles={"min-height": "0", "flex": "1 1 auto"},
    )

    insert_btn = pn.widgets.Button(
        name="Insert Figure",
        button_type="default",
        width=150,
        height=26,
        margin=(0, 0, 8, 0),
        styles={"font-size": "11px"},
    )
    insert_btn.js_on_click(
        code="if (window.showInsertFigureModal) window.showInsertFigureModal();",
    )

    left_header = pn.Row(
        pn.pane.Markdown("**Explorer**", styles={"color": "#ddd"}),
        pn.layout.HSpacer(),
        insert_btn,
        sizing_mode="stretch_width",
        styles={"padding-bottom": "2px"},
    )

    left_container = pn.Column(
        left_header,
        sidebar_files,
        sizing_mode="stretch_both",
        min_width=240,
        styles={"min-height": "0", "overflow": "hidden", "flex": "1 1 auto"},
        css_classes=["pane-left", "sidebar-pane"],
    )
    center_container = pn.Column(
        center_tabs,
        sizing_mode="stretch_both",
        min_width=360,
        styles={"min-height": "0", "flex": "1 1 auto"},
        css_classes=["pane-center"],
    )
    right_container = pn.Column(
        right_tabs,
        sizing_mode="stretch_both",
        min_width=360,
        styles={"min-height": "0", "flex": "1 1 auto"},
        css_classes=["pane-right"],
    )

    body = pn.Row(
        left_container,
        _split_gutter("left-center"),
        center_container,
        _split_gutter("center-right"),
        right_container,
        sizing_mode="stretch_both",
        styles={"min-height": "0", "flex": "1 1 auto"},
        css_classes=["body-row"],
    )

    return pn.Column(
        toolbar,
        body,
        sizing_mode="stretch_both",
        css_classes=["app-shell"],
        styles={
            "border": "2px solid #000",
            "background": "#000",
            "overflow": "hidden",
            "min-height": "0",
            "flex": "1 1 auto",
        },
    )


app = create_app()
app.servable()
