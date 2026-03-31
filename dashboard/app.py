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
import param

from dashboard.theme import THEME
from dashboard.utils import load_config
from dashboard.pages.paper_page import build_paper_page
from dashboard.file_tree import (
    EXPLORER_BUTTON_STYLESHEETS,
    EXPLORER_INNER_WIDTH,
    EXPLORER_LIST_BTN_STYLES,
    build_file_tree_sidebar,
    get_language,
)

_RAW_CSS = """
#header{display:none!important;height:0!important}
html,body{overflow-x:hidden!important;margin:0!important;padding:0!important;height:100%!important}
.container-fluid{padding:0!important;max-width:100%!important;height:100%!important;min-height:0!important;display:flex!important;flex-direction:column!important}
#main{padding:0!important;flex:1 1 auto!important;min-height:0!important;display:flex!important;flex-direction:column!important}
div.ace_editor{overflow:hidden!important}
div.ace_editor div.ace_scroller{overflow-x:hidden!important}
div.ace_editor div.ace_scrollbar-h{display:none!important;height:0!important}
div.ace_editor div.ace_content{overflow-x:hidden!important}
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
.activity-bar {
  background: #1e1e1e !important;
  border-right: 1px solid #333 !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  padding-top: 10px !important;
  z-index: 10 !important;
}
/* Crucial Shadow-DOM piercing for transparent icons */
.activity-bar .bk-btn {
  background: transparent !important;
  border: none !important;
  color: #858585 !important;
  font-size: 24px !important;
  padding: 0 !important;
  cursor: pointer !important;
  transition: color 0.1s, border-left 0.1s !important;
  border-left: 2px solid transparent !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}
.activity-bar .bk-btn:hover { color: #fff !important; }
.activity-bar .bk-btn.active {
  color: #fff !important;
  border-left: 2px solid #007acc !important;
}
.activity-btn { margin-bottom: 4px !important; }
"""

pn.extension(
    "codeeditor",
    sizing_mode="stretch_width",
    template="bootstrap",
    raw_css=[_RAW_CSS],
    css_files=[
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
        "/assets/theme.css?v=101",
    ],
    js_files={
        "insert_figure": "/assets/insert_figure_overlay.js?v=101",
        "split_loader": "/assets/split_loader.js?v=101",
    },
)

def _split_gutter(between: str) -> pn.Column:
    """Fixed-width handle between panes (Column target for split_pane.js). """
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
            "min-width": "8px", "max-width": "8px", "width": "8px",
            "min-height": "0", "padding": "0",
            "background": "rgba(55,65,80,0.55)",
            "border-left": "1px solid rgba(255,255,255,0.2)",
            "border-right": "1px solid rgba(0,0,0,0.35)",
        },
    )


class IDEPanel(pn.viewable.Viewer):
    """A panel that can switch between Explorer, Editor, and Preview."""
    mode = param.Selector(default="Editor", objects=["Explorer", "Editor", "Preview"], allow_None=True)

    def __init__(self, contents, **params):
        super().__init__(**params)
        self.contents = contents  # dict: mode -> viewable
        self._main_area = pn.Column(sizing_mode="stretch_both", styles={"min-height": "0", "flex": "1 1 auto"})
        
        # Activity Bar (Icons on the left)
        # Use individual buttons for better control over icons and CSS
        self._btns = {
            "Explorer": self._create_icon_btn("folder", "Explorer"),
            "Editor": self._create_icon_btn("pencil", "Editor"),
            "Preview": self._create_icon_btn("eye", "Preview"),
        }
        
        self._switcher = pn.Column(
            *self._btns.values(),
            width=48,
            sizing_mode="stretch_height",
            css_classes=["activity-bar"],
            styles={"background": "#1e1e1e", "border-right": "1px solid #333", "align-items": "center", "padding-top": "12px"}
        )
        
        self.param.watch(self._update_content, "mode")
        self._update_content()

    def _create_icon_btn(self, icon: str, m: str):
        btn = pn.widgets.Button(
            name="", 
            button_type="default",
            icon=icon,
            width=40, height=40,
            margin=(4, 0),
            css_classes=["activity-btn"],
            stylesheets=[EXPLORER_BUTTON_STYLESHEETS],
        )
        # Use a default argument in the lambda to capture the current mode string correctly
        btn.on_click(lambda e, m=m: setattr(self, "mode", m))
        return btn

    def _update_content(self, *events):
        # 1. Update buttons visual state by toggling CSS class
        for mode_key, btn in self._btns.items():
            classes = ["activity-btn"]
            if self.mode == mode_key:
                classes.append("active")
            btn.css_classes = classes
        
        # 2. Update main area
        view = self.contents.get(self.mode or "Editor")
        if view:
            self._main_area.objects = [view]

    def __panel__(self):
        return pn.Row(
            self._switcher,
            self._main_area,
            sizing_mode="stretch_both",
            styles={"min-height": "0", "flex": "1 1 auto", "overflow": "hidden"}
        )


def create_app():
    config = load_config()
    qmd_path = Path(config["quarto_paper_path"])

    qmd_content = qmd_path.read_text() if qmd_path.exists() else "# File not found"
    
    # We create distinct instances for each mode-component to avoid migration issues between panels.
    # We will synchronize the editors later if needed.
    def _create_editor():
        return pn.widgets.CodeEditor(
            value=qmd_content, language="markdown",
            sizing_mode="stretch_both", min_height=600, theme="tomorrow_night",
        )

    # Create SHARED instances for components that need global synchronization
    editor = _create_editor()
    shared_paper_content, shared_paper_page = build_paper_page(config)
    current_file = {"path": str(qmd_path)}

    def _on_file_click(file_path: str, language: str):
        if current_file["path"]:
            try:
                Path(current_file["path"]).write_text(editor.value, encoding="utf-8")
            except Exception:
                pass
        current_file["path"] = file_path
        txt = Path(file_path).read_text(encoding="utf-8")
        editor.value = txt
        editor.language = language

    # Factory for panel contents (returns a fresh dict, but themes views can be shared or fresh)
    def _get_contents():
        insert_figure_btn = pn.widgets.Button(
            name="Insert figure", icon="photo", icon_size="11px", button_type="default", button_style="outline",
            width=EXPLORER_INNER_WIDTH, sizing_mode="fixed", margin=(0, 0, 2, 0),
            css_classes=["dash-explorer-item", "dash-explorer-refresh"],
            styles={**EXPLORER_LIST_BTN_STYLES, "color": "#9fd4f5", "font-size": "13px"},
            stylesheets=[EXPLORER_BUTTON_STYLESHEETS],
        )
        insert_figure_btn.js_on_click(code="if (window.showInsertFigureModal) window.showInsertFigureModal();")

        explorer_view = build_file_tree_sidebar(
            project_root=qmd_path.parent, on_file_click=_on_file_click, insert_figure_button=insert_figure_btn,
        )
        explorer_view.sizing_mode = "stretch_both"
        explorer_view.styles = {**getattr(explorer_view, "styles", {}), "min-height": "0"}

        return {
            "Explorer": explorer_view,
            "Editor": pn.Column(editor, sizing_mode="stretch_both", css_classes=["editor-pane"], styles={"min-height": "0", "flex": "1 1 auto"}),
            "Preview": pn.Column(shared_paper_content, sizing_mode="stretch_both", css_classes=["preview-pane"], styles={"min-height": "0", "flex": "1 1 auto"}),
        }

    title_pane = pn.pane.HTML('<span class="dash-toolbar-title">4Dpaper</span>', sizing_mode="fixed", width=80, margin=(0, 8, 0, 4))
    
    build_cluster = pn.Row(
        shared_paper_page.rebuild_btn, shared_paper_page.export_btn, shared_paper_page.pdf_link,
        sizing_mode="fixed", margin=0, styles={"align-items": "center"},
    )

    toolbar = pn.Row(
        title_pane, pn.layout.HSpacer(), build_cluster,
        pn.pane.HTML('<span style="color:#555;font-size:14px">│</span>', margin=(2, 4)),
        sizing_mode="stretch_width", height=32, margin=0, css_classes=["dash-toolbar"],
        styles={"padding": "4px 10px", "align-items": "center"},
    )

    left_ide = IDEPanel(contents=_get_contents(), name="IDE_Left")
    left_container = pn.Column(
        left_ide,
        sizing_mode="stretch_both",
        css_classes=["pane-left"],
        styles={"min-height": "0", "flex": "1 1 auto"}
    )
    
    right_ide = IDEPanel(contents=_get_contents(), name="IDE_Right")
    # Set default mode for right container to Preview
    right_ide.mode = "Preview"
    
    right_container = pn.Column(
        right_ide,
        sizing_mode="stretch_both",
        css_classes=["pane-center"],
        styles={"min-height": "0", "flex": "1 1 auto"}
    )

    body = pn.Row(
        left_container,
        _split_gutter("left-center"),
        right_container,
        sizing_mode="stretch_both",
        styles={"min-height": "0", "flex": "1 1 auto"},
        css_classes=["body-row"],
    )

    # Mediator for camera synchronization between panels
    mediator = pn.pane.HTML("""
    <script>
    (function(){
      window.addEventListener("message", function(e) {
        if (e.data && e.data.type === "4dpaper-camera") {
          var iframes = document.querySelectorAll("iframe");
          for (var i = 0; i < iframes.length; i++) {
            if (iframes[i].contentWindow && iframes[i].contentWindow !== e.source) {
              iframes[i].contentWindow.postMessage({
                type: "4dpaper-camera-apply",
                camera: e.data.camera
              }, "*");
            }
          }
        }
      });
    })();
    </script>
    """, width=0, height=0, margin=0, sizing_mode="fixed")

    app_shell = pn.Column(
        toolbar,
        body,
        sizing_mode="stretch_both",
        css_classes=["app-shell"],
        styles={
            "border": f"2px solid {THEME['border_subtle']}",
            "background": THEME["bg_app"],
            "overflow": "hidden",
            "min-height": "0",
            "flex": "1 1 auto",
        },
    )
    
    return pn.Column(app_shell, mediator, sizing_mode="stretch_both")


app = create_app()
app.servable()
