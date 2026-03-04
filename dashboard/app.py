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
from pathlib import Path

# Ensure the repo root is on sys.path so `dashboard.*` imports work when
# panel serve runs this file directly.
_repo_root = Path(__file__).parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import panel as pn

from dashboard.utils import load_config
from dashboard.pages.paper_page import build_paper_page
from dashboard.figure_browser import build_figure_browser

pn.extension(
    "codeeditor",
    sizing_mode="stretch_width",
    template="bootstrap",
    raw_css=[
        """
        /* ── Full-width layout ──────────────────────────────────────────── */
        html, body { overflow-x: hidden !important; max-width: 100vw; }
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

    def _on_save(_event):
        try:
            qmd_path.write_text(editor.value, encoding="utf-8")
            save_status.object = "✓ Saved — click Rebuild HTML to preview changes."
            save_status.alert_type = "success"
        except Exception as exc:
            save_status.object = f"✗ Save failed: {exc}"
            save_status.alert_type = "danger"
        save_status.visible = True

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
            document.querySelectorAll('.ace_editor').forEach(function(el){
                try{
                    var ed=ace.edit(el);
                    ed.session.setUseWrapMode(true);
                    // also hide the h-scrollbar via the editor API
                    if(ed.renderer && ed.renderer.$scrollbarV)
                        ed.renderer.$scrollbarV.element.style.overflowX='hidden';
                }catch(e){}
            });
        })();
        """,
    )

    # Fire the callback as soon as the session WebSocket is ready.
    pn.state.onload(lambda: setattr(_wrap_trigger, "clicks", 1))

    editor_panel = pn.Column(
        pn.pane.Markdown(f"### `{qmd_path.name}`"),
        pn.Row(save_btn, save_status),
        editor,
        _wrap_trigger,          # invisible; must be in the layout to be served
        sizing_mode="stretch_both",
        min_width=380,
    )

    # ── Figure browser sidebar ─────────────────────────────────────────────────
    sidebar = build_figure_browser(editor, qmd_path, config)

    # ── Paper preview ──────────────────────────────────────────────────────────
    paper_panel = pn.Column(
        build_paper_page(config),
        sizing_mode="stretch_both",
        min_width=480,
    )

    # ── Panel toggle toolbar ───────────────────────────────────────────────────
    sidebar_toggle = pn.widgets.Toggle(
        name="⊣  Figures",
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
            "background": "#212529",
            "border-bottom": "1px solid #343a40",
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
