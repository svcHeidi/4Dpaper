"""
4Dpaper Dashboard — main Panel app.

Launch with:
    panel serve dashboard/app.py --plugins dashboard.camera_plugin --static-dirs output=_output --show --port 5006
from the 4Dpapers repository root.

The --static-dirs flag makes _output/ available at /output/ so the
paper iframe can embed the rendered HTML at /output/analysis_report.html.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

# Ensure the repo root is on sys.path so `dashboard.*` imports work when
# panel serve runs this file directly.
_repo_root = Path(__file__).parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import panel as pn

from dashboard.theme import THEME, chrome_css
from dashboard.utils import load_config
from dashboard.pages.paper_page import build_paper_page
from dashboard.file_tree import build_file_tree_sidebar, get_language
from dashboard.figure_browser import build_figure_insert_form

pn.extension(
    "codeeditor",
    sizing_mode="stretch_width",
    template="bootstrap",
    raw_css=[
        chrome_css()
        + """
        /* ── Hide the "Panel Application" header bar ─────────────────────── */
        #header { display: none !important; height: 0 !important; }

        /* ── Full-width layout ──────────────────────────────────────────── */
        html, body {
            overflow-x: hidden !important;
            max-width: 100vw;
            margin: 0 !important;
            padding: 0 !important;
        }
        .container-fluid {
            padding-left:  0 !important;
            padding-right: 0 !important;
            max-width: 100% !important;
        }
        #main { padding: 0 !important; }

        /* ── Ace editor: no horizontal scroll / movement ─────────────────
           Use highly specific selectors to win against Ace's own rules.  */
        div.ace_editor                         { overflow: hidden !important; }
        div.ace_editor div.ace_scroller        { overflow-x: hidden !important; }
        div.ace_editor div.ace_scrollbar-h     { display: none   !important;
                                                 height: 0       !important; }
        div.ace_editor div.ace_content         { overflow-x: hidden !important; }
        """
    ],
)


def create_app():
    config = load_config()
    qmd_path = Path(config["quarto_paper_path"])

    # ── QMD editor ────────────────────────────────────────────────────────────
    qmd_content = qmd_path.read_text() if qmd_path.exists() else (
        f"# File not found\n\n`{qmd_path}` does not exist.\n\n"
        "Update `quarto_paper_path` in `dashboard/config.yaml`."
    )

    editor = pn.widgets.CodeEditor(
        value=qmd_content,
        language="markdown",
        sizing_mode="stretch_width",
        height=800,
        theme="tomorrow_night",
    )

    # ── Multi-file state ──────────────────────────────────────────────────────
    current_file = {"path": str(qmd_path)}

    editor_title = pn.pane.Markdown(f"### `{qmd_path.name}`")

    def _on_file_click(file_path: str, language: str):
        # Auto-save current file before switching
        if current_file["path"]:
            Path(current_file["path"]).write_text(editor.value, encoding="utf-8")
        # Load new file
        current_file["path"] = file_path
        editor.value = Path(file_path).read_text(encoding="utf-8")
        editor.language = language
        editor_title.object = f"### `{Path(file_path).name}`"

    # ── Save button ───────────────────────────────────────────────────────────
    save_btn = pn.widgets.Button(
        name="💾  Save",
        button_type="default",
        width=110,
    )
    save_status = pn.pane.Alert(
        "",
        alert_type="success",
        sizing_mode="stretch_width",
        visible=False,
    )

    _save_timer: list[threading.Timer] = []  # holds at most one timer

    def _on_save(_event):
        try:
            Path(current_file["path"]).write_text(editor.value, encoding="utf-8")
            save_status.object = f"✓ Saved {Path(current_file['path']).name}"
            save_status.alert_type = "success"
        except Exception as exc:
            save_status.object = f"✗ Save failed: {exc}"
            save_status.alert_type = "danger"
        save_status.visible = True
        # Auto-hide after 3 s
        for t in _save_timer:
            t.cancel()
        _save_timer.clear()
        doc = pn.state.curdoc
        def _hide():
            doc.add_next_tick_callback(lambda: setattr(save_status, "visible", False))
        t = threading.Timer(3.0, _hide)
        t.daemon = True
        t.start()
        _save_timer.append(t)

    save_btn.on_click(_on_save)

    # ── Ace word-wrap via Bokeh jscallback (reliable client-side JS) ──────────
    # pn.pane.HTML script tags are stripped by Bokeh's innerHTML injection.
    # jscallback creates a real Bokeh CustomJS that is sent to the browser over
    # the WebSocket and executed there — no sanitisation happens.
    _wrap_trigger = pn.widgets.Button(
        name="", width=1, height=1, margin=0, visible=False,
    )
    _wrap_trigger.jscallback(
        clicks="""
        (function init(){
            if(typeof ace==='undefined'){setTimeout(init,200);return;}
            // ── Enable word-wrap on every Ace editor instance ────────────
            document.querySelectorAll('.ace_editor').forEach(function(el){
                try{
                    var ed=ace.edit(el);
                    ed.session.setUseWrapMode(true);
                    if(ed.renderer && ed.renderer.$scrollbarV)
                        ed.renderer.$scrollbarV.element.style.overflowX='hidden';
                }catch(e){}
            });
            // ── Force equal widths on editor + preview panels ────────────
            // Bokeh uses shadow DOM; we traverse shadow roots to find the
            // body Row (3 visible children: sidebar, editor, preview) and
            // force the last two to share space equally via inline flex.
            // Delay to ensure Bokeh's layout is fully rendered first.
            setTimeout(function(){
                var found=false;
                function fix(root,depth){
                    if(found||depth>12)return;
                    var kids=root.children||[];
                    for(var i=0;i<kids.length;i++){
                        if(found)return;
                        var sr=kids[i].shadowRoot;
                        if(sr){
                            var vis=[];
                            for(var j=0;j<sr.children.length;j++){
                                if(sr.children[j].offsetWidth>10)vis.push(sr.children[j]);
                            }
                            if(vis.length===3&&vis[0].offsetWidth<350&&vis[1].offsetWidth>350){
                                vis[1].style.setProperty('flex','1 1 0%','important');
                                vis[1].style.setProperty('width','auto','important');
                                vis[2].style.setProperty('flex','1 1 0%','important');
                                vis[2].style.setProperty('width','auto','important');
                                found=true;
                                // Trigger Ace editor resize after layout change
                                document.querySelectorAll('.ace_editor').forEach(function(el){
                                    try{ace.edit(el).resize();}catch(e){}
                                });
                                return;
                            }
                            fix(sr,depth+1);
                        }
                        fix(kids[i],depth+1);
                    }
                }
                fix(document.body,0);
            },1000);
        })();
        """,
    )

    # Fire the callback as soon as the session WebSocket is ready.
    pn.state.onload(lambda: setattr(_wrap_trigger, "clicks", 1))

    editor_panel = pn.Column(
        editor_title,
        pn.Row(save_btn, save_status),
        editor,
        _wrap_trigger,          # invisible; must be in the layout to be served
        sizing_mode="stretch_both",
        min_width=400,
    )

    # ── File tree sidebar (+ Insert Figure at the bottom) ─────────────────────
    sidebar = build_file_tree_sidebar(
        project_root=qmd_path.parent,
        on_file_click=_on_file_click,
    )

    # ── Insert Figure toggle + form (lives in sidebar) ────────────────────────
    insert_fig_btn = pn.widgets.Toggle(
        name="📐 Insert Figure",
        value=False,
        button_type="default",
        width=260,
    )
    figure_form = build_figure_insert_form(editor, qmd_path, config)
    figure_form.visible = False
    insert_fig_btn.param.watch(
        lambda e: setattr(figure_form, "visible", e.new), "value"
    )
    sidebar.append(pn.layout.Divider(margin=(8, 0, 4, 0)))
    sidebar.append(insert_fig_btn)
    sidebar.append(figure_form)

    # ── Paper preview ──────────────────────────────────────────────────────────
    paper_panel = pn.Column(
        build_paper_page(config),
        sizing_mode="stretch_both",
        min_width=400,
    )

    # ── Panel toggle toolbar ───────────────────────────────────────────────────
    sidebar_toggle = pn.widgets.Toggle(
        name="⊣  Files",
        value=True,
        button_type="primary",
        width=110,
    )
    preview_toggle = pn.widgets.Toggle(
        name="Preview  ⊢",
        value=True,
        button_type="primary",
        width=110,
    )

    sidebar_toggle.param.watch(lambda e: setattr(sidebar, "visible", e.new), "value")
    preview_toggle.param.watch(lambda e: setattr(paper_panel, "visible", e.new), "value")

    toolbar = pn.Row(
        sidebar_toggle,
        pn.layout.HSpacer(),
        preview_toggle,
        sizing_mode="stretch_width",
        height=42,
        styles={
            "padding": "4px 8px",
            "background": THEME["toolbar_bg"],
            "border-bottom": f"1px solid {THEME['border_subtle']}",
        },
    )

    body = pn.Row(
        sidebar,
        editor_panel,
        paper_panel,
        sizing_mode="stretch_both",
    )

    return pn.Column(toolbar, body, sizing_mode="stretch_both")


app = create_app()
app.servable()
