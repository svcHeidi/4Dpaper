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
from dashboard.figure_browser import build_figure_insert_form

_RAW_CSS = """
#header{display:none!important;height:0!important}
html,body{overflow-x:hidden!important;margin:0!important;padding:0!important;background:#000!important}
.container-fluid{padding:0!important;max-width:100%!important}
#main{padding:0!important}
div.ace_editor{overflow:hidden!important}
div.ace_editor div.ace_scroller{overflow-x:hidden!important}
div.ace_editor div.ace_scrollbar-h{display:none!important;height:0!important}
div.ace_editor div.ace_content{overflow-x:hidden!important}
"""

pn.extension(
    "codeeditor",
    sizing_mode="stretch_width",
    template="bootstrap",
    raw_css=[_RAW_CSS],
    js_files={"split_pane": "/assets/split_pane.js?v=7"},
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

    # Toggles
    stog = pn.widgets.Toggle(
        name="☰ Files", value=True, button_type="light",
        width=70, height=24, margin=(0, 2), styles={"font-size": "11px"},
    )
    ptog = pn.widgets.Toggle(
        name="Preview ⊢", value=True, button_type="light",
        width=80, height=24, margin=(0, 2), styles={"font-size": "11px"},
    )

    paper_content, paper_page = build_paper_page(config)

    toolbar = pn.Row(
        stog, pn.layout.HSpacer(),
        paper_page.rebuild_btn, paper_page.export_btn,
        paper_page.pdf_link,
        pn.pane.HTML('<span style="color:#555;font-size:14px">│</span>', margin=(2, 4)),
        ptog,
        sizing_mode="stretch_width", height=28,
        styles={"padding": "1px 6px", "background": "#111", "border-bottom": "1px solid #333"},
    )

    editor_panel = pn.Column(
        editor,
        pn.pane.HTML('<div class="split-marker" data-id="editor"></div>', height=0, width=0, margin=0),
        sizing_mode="stretch_both", min_width=250,
        css_classes=["editor-pane"],
    )

    sidebar = build_file_tree_sidebar(
        project_root=qmd_path.parent, on_file_click=_on_file_click,
    )
    sidebar.append(pn.pane.HTML('<div class="split-marker" data-id="sidebar"></div>', height=0, width=0, margin=0))
    sidebar.css_classes = ["sidebar-pane"]

    insert_fig_btn = pn.widgets.Toggle(
        name="📐 Insert Figure", value=False, button_type="default",
        width=240, height=26, styles={"font-size": "12px"},
    )
    figure_form = build_figure_insert_form(editor, qmd_path, config)
    figure_form.visible = False
    insert_fig_btn.param.watch(lambda e: setattr(figure_form, "visible", e.new), "value")
    sidebar.append(pn.layout.Divider(margin=(8, 0, 4, 0)))
    sidebar.append(insert_fig_btn)
    sidebar.append(figure_form)
    stog.param.watch(lambda e: setattr(sidebar, "visible", e.new), "value")

    paper_panel = pn.Column(
        paper_content,
        pn.pane.HTML('<div class="split-marker" data-id="preview"></div>', height=0, width=0, margin=0),
        sizing_mode="stretch_both", min_width=250,
        css_classes=["preview-pane"],
    )
    ptog.param.watch(lambda e: setattr(paper_panel, "visible", e.new), "value")

    body = pn.Row(
        sidebar, editor_panel, paper_panel,
        sizing_mode="stretch_both",
        css_classes=["body-row"],
    )

    return pn.Column(
        toolbar, body,
        sizing_mode="stretch_both",
        styles={"border": "2px solid #000", "background": "#000", "overflow": "hidden"},
    )


app = create_app()
app.servable()
