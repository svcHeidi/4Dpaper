"""
4Dpaper Dashboard - main Panel app.

Launch with:
    panel serve dashboard/app.py --plugins dashboard.plugins \
        --static-dirs output=_output assets=dashboard/static state=state --show --port 5006
from the 4Dpapers repository root.
"""
from __future__ import annotations

import json
import threading
import sys
from pathlib import Path

_repo_root = Path(__file__).parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import panel as pn

from dashboard.editor_tabs import after_close_tab, open_in_tabs
from dashboard.file_tree import (
    EXPLORER_BUTTON_STYLESHEETS,
    EXPLORER_INNER_WIDTH,
    EXPLORER_LIST_BTN_STYLES,
    build_file_tree_sidebar,
)
from dashboard.pages.paper_page import build_paper_page
from dashboard.pages.settings_page import build_settings_page
from dashboard.theme import THEME
from dashboard.utils import load_config

_RAW_CSS = """
#header{display:none!important;height:0!important}
html,body{overflow-x:hidden!important;margin:0!important;padding:0!important;background:#000!important;height:100%!important}
.container-fluid{padding:0!important;max-width:100%!important;height:100%!important;min-height:0!important;display:flex!important;flex-direction:column!important}
#main{padding:0!important;flex:1 1 auto!important;min-height:0!important;display:flex!important;flex-direction:column!important}
div.ace_editor{overflow:hidden!important}
div.ace_editor div.ace_scroller{overflow-x:hidden!important}
div.ace_editor div.ace_scrollbar-h{display:none!important;height:0!important}
div.ace_editor div.ace_content{overflow-x:hidden!important}
.ace_editor .ace_cursor{border-left:2px solid #e6e6e6!important}
.ace_editor.ace_focus .ace_cursor{border-left:2px solid #ffffff!important}
.ace_editor .ace_hidden-cursors .ace_cursor{opacity:1!important}
#split-status{color:#8ab4ff;font-size:10px;font-family:monospace;opacity:0.9;margin-left:8px;}
.app-shell{height:100vh!important;min-height:0!important;display:flex!important;flex-direction:column!important;box-sizing:border-box!important}
.app-shell .body-row{flex:1 1 auto!important;min-height:0!important;width:100%!important;display:flex!important;flex-direction:row!important;align-items:stretch!important;position:relative!important;overflow:visible!important}
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
    css_files=["/assets/theme.css?v=106"],
    js_files={
        "insert_figure": "/assets/insert_figure_overlay.js?v=106",
        "split_loader": "/assets/split_loader.js?v=106",
    },
)


def _split_gutter(between: str) -> pn.Column:
    handle = pn.pane.HTML(
        '<div class="__split_handle" role="separator" aria-orientation="vertical" '
        'title="Drag to resize panes"></div>',
        sizing_mode="stretch_both",
        margin=0,
    )
    return pn.Column(
        handle,
        sizing_mode="stretch_height",
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
            "background": "rgba(55,65,80,0.55)",
            "border-left": "1px solid rgba(255,255,255,0.2)",
            "border-right": "1px solid rgba(0,0,0,0.35)",
        },
    )


def _build_split_config_script(panels: list[dict], default_panel: str) -> str:
    """Return an inline <script> that sets window.SPLIT_CONFIG from PANELS."""
    panel_entries = [
        {
            "id": p["id"],
            "icon": p["icon"],
            "label": p["label"],
            "selector": f".panel-slot--{p['id']}",
            **({"bottom": True} if p.get("bottom") else {}),
        }
        for p in panels
    ]
    config = {
        "panels": panel_entries,
        "defaultPanel": default_panel,
        "mainPanelSelector": ".main-panel",
        "previewPanelSelector": ".pane-right",
        "gutterSelector": "[class*='split-gutter--between-main-preview']",
    }
    return (
        f"<script>window.SPLIT_CONFIG = {json.dumps(config)};"
        "localStorage.removeItem('4dpapers.pane.mainWidth');"
        "</script>"
    )


def _build_activity_bar_html(panels: list[dict]) -> str:
    """Return HTML string for the activity bar (injected via pn.pane.HTML)."""
    def btn(p: dict) -> str:
        return (
            f'<button class="activity-bar-btn" data-panel-id="{p["id"]}" '
            f'title="{p["label"]}" '
            f'onclick="if(window.__activityBarSwitch)window.__activityBarSwitch(\'{p["id"]}\');">'
            f'{p["icon"]}'
            f"</button>"
        )

    top_items = [p for p in panels if not p.get("bottom")]
    bottom_items = [p for p in panels if p.get("bottom")]
    top_html = "".join(btn(p) for p in top_items)
    bottom_html = "".join(btn(p) for p in bottom_items)

    return (
        '<div class="activity-bar" id="activity-bar">'
        f'<div class="activity-bar-top">{top_html}</div>'
        f'<div class="activity-bar-bottom">{bottom_html}</div>'
        "</div>"
    )


def create_app():
    config = load_config()
    qmd_path = Path(config["quarto_paper_path"])

    qmd_content = qmd_path.read_text(encoding="utf-8") if qmd_path.exists() else (
        f"# File not found\n\n`{qmd_path}` does not exist.\n\n"
        "Update `quarto_paper_path` in `dashboard/config.yaml`."
    )
    editor = pn.widgets.CodeEditor(
        value=qmd_content,
        language="markdown",
        sizing_mode="stretch_both",
        min_height=400,
        theme="tomorrow_night",
    )

    # ── Tab state ────────────────────────────────────────────────────────
    _qmd_resolved = str(qmd_path.resolve())
    tab_order: list[str] = [_qmd_resolved]
    active_path: list[str | None] = [_qmd_resolved]   # list wraps scalar for closure mutation
    file_cache: dict[str, str] = {_qmd_resolved: qmd_content}

    save_status = pn.pane.HTML(
        "",
        width=220,
        visible=False,
        styles={
            "font-size": "11px",
            "color": THEME["text_muted"],
            "white-space": "nowrap",
            "overflow": "hidden",
            "text-overflow": "ellipsis",
        },
    )
    _save_timer: list[threading.Timer] = []

    def _set_save_status(text: str) -> None:
        save_status.object = text
        save_status.visible = True
        for timer in _save_timer:
            timer.cancel()
        _save_timer.clear()
        doc = pn.state.curdoc

        def _hide():
            if doc is None:
                return
            try:
                doc.add_next_tick_callback(lambda: setattr(save_status, "visible", False))
            except Exception:
                pass

        timer = threading.Timer(3.0, _hide)
        timer.daemon = True
        timer.start()
        _save_timer.append(timer)

    def _detect_language(path: str) -> str:
        return {
            ".qmd": "markdown", ".md": "markdown",
            ".py": "python", ".yaml": "yaml", ".yml": "yaml",
            ".bib": "text", ".lua": "lua", ".json": "json",
            ".toml": "toml", ".css": "css",
            ".js": "javascript", ".html": "html",
        }.get(Path(path).suffix.lower(), "text")

    def _save_active() -> None:
        ap = active_path[0]
        if not ap:
            return
        content = editor.value
        file_cache[ap] = content
        Path(ap).write_text(content, encoding="utf-8")

    def _load_path(path: str, language: str | None = None) -> None:
        content = file_cache.get(path)
        if content is None:
            content = Path(path).read_text(encoding="utf-8")
            file_cache[path] = content
        editor.value = content
        editor.language = language or _detect_language(path)

    def _rebuild_tab_bar() -> None:
        ap = active_path[0]
        if not tab_order:
            tab_bar.objects = []
            editor.visible = False
            editor_placeholder.visible = True
            return
        editor.visible = True
        editor_placeholder.visible = False
        objects: list = []
        for path in tab_order:
            is_active = path == ap
            name = Path(path).name
            tab_btn = pn.widgets.Button(
                name=name,
                button_type="primary" if is_active else "default",
                height=22,
                margin=0,
                css_classes=["editor-tab", "editor-tab-active" if is_active else "editor-tab-inactive"],
                stylesheets=[_TAB_ACTIVE_SS if is_active else _TAB_INACTIVE_SS],
            )
            tab_btn.on_click(lambda _e, p=path: _on_tab_activate(p))
            close_btn = pn.widgets.Button(
                name="×",
                button_type="light",
                width=18,
                height=22,
                margin=0,
                css_classes=["editor-tab-close"],
                stylesheets=[_CLOSE_ACTIVE_SS if is_active else _CLOSE_INACTIVE_SS],
            )
            close_btn.on_click(lambda _e, p=path: _on_tab_close(p))
            objects.extend([tab_btn, close_btn])
        tab_bar.objects = objects

    def _on_tab_activate(path: str) -> None:
        if active_path[0] and active_path[0] != path:
            file_cache[active_path[0]] = editor.value
        active_path[0] = path
        _load_path(path)
        _rebuild_tab_bar()

    def _on_tab_close(path: str) -> None:
        if active_path[0]:
            file_cache[active_path[0]] = editor.value
        new_order, new_active = after_close_tab(tab_order, active_path[0] or "", path)
        tab_order.clear()
        tab_order.extend(new_order)
        active_path[0] = new_active if new_active else None
        if active_path[0]:
            _load_path(active_path[0])
        _rebuild_tab_bar()

    def _on_file_click(file_path: str, language: str) -> None:
        if active_path[0]:
            file_cache[active_path[0]] = editor.value
        new_order, new_active = open_in_tabs(tab_order, file_path)
        tab_order.clear()
        tab_order.extend(new_order)
        active_path[0] = new_active
        _load_path(new_active, language)
        _rebuild_tab_bar()

    save_btn = pn.widgets.Button(
        name="Save",
        button_type="default",
        width=88,
        height=26,
        margin=(0, 2),
        styles={"font-size": "11px"},
    )

    def _on_save(_event):
        if not active_path[0]:
            return
        try:
            _save_active()
            _set_save_status(f"Saved {Path(active_path[0]).name}")
        except Exception as exc:
            _set_save_status(f"Save failed: {exc}")

    save_btn.on_click(_on_save)

    # Shadow-DOM stylesheets for tab buttons — :host pierces Panel's shadow root
    _BG_ACTIVE = THEME["bg_panel"]       # #121212
    _BG_INACTIVE = "#1a1a1a"
    _BORDER = THEME["border_subtle"]     # #3d3834
    _ACCENT = THEME["accent"]            # #138a7c
    _MUTED = THEME["text_muted"]         # #b8def5

    _TAB_ACTIVE_SS = (
        f":host{{background:{_BG_ACTIVE}!important;margin:0!important;padding:0!important;flex-shrink:0!important}}"
        f":host .bk-btn{{background:{_BG_ACTIVE}!important;color:#fff!important;"
        f"border:none!important;border-bottom:2px solid {_ACCENT}!important;"
        f"border-radius:0!important;height:22px!important;font-size:11px!important;"
        f"padding:0 4px 0 6px!important;white-space:nowrap!important;"
        f"overflow:hidden!important;text-overflow:ellipsis!important}}"
    )
    _TAB_INACTIVE_SS = (
        f":host{{background:{_BG_INACTIVE}!important;margin:0!important;padding:0!important;flex-shrink:0!important}}"
        f":host .bk-btn{{background:{_BG_INACTIVE}!important;color:{_MUTED}!important;"
        f"border:none!important;border-radius:0!important;height:22px!important;"
        f"font-size:11px!important;padding:0 4px 0 6px!important;"
        f"white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}}"
        f":host .bk-btn:hover{{background:rgba(255,255,255,0.08)!important;color:#fff!important}}"
    )
    _CLOSE_ACTIVE_SS = (
        f":host{{background:{_BG_ACTIVE}!important;margin:0!important;padding:0!important;"
        f"width:18px!important;flex-shrink:0!important}}"
        f":host .bk-btn{{background:{_BG_ACTIVE}!important;color:{_MUTED}!important;"
        f"border:none!important;border-right:1px solid {_BORDER}!important;"
        f"border-bottom:2px solid {_ACCENT}!important;border-radius:0!important;"
        f"height:22px!important;width:18px!important;font-size:12px!important;padding:0!important}}"
        f":host .bk-btn:hover{{color:#fff!important;background:rgba(255,255,255,0.1)!important}}"
    )
    _CLOSE_INACTIVE_SS = (
        f":host{{background:{_BG_INACTIVE}!important;margin:0!important;padding:0!important;"
        f"width:18px!important;flex-shrink:0!important}}"
        f":host .bk-btn{{background:{_BG_INACTIVE}!important;color:{_MUTED}!important;"
        f"border:none!important;border-right:1px solid {_BORDER}!important;"
        f"border-radius:0!important;height:22px!important;width:18px!important;"
        f"font-size:12px!important;padding:0!important}}"
        f":host .bk-btn:hover{{color:#fff!important;background:rgba(255,255,255,0.1)!important}}"
    )

    tab_bar = pn.Row(
        sizing_mode="stretch_width",
        height=22,
        margin=0,
        css_classes=["editor-tab-bar"],
        styles={"min-height": "0", "flex": "0 0 22px", "gap": "0"},
    )
    editor_placeholder = pn.pane.HTML(
        f'<div style="display:flex;align-items:center;justify-content:center;'
        f'height:100%;color:{THEME["text_muted"]};font-size:13px;">'
        f"Click a file in the explorer to open it.</div>",
        sizing_mode="stretch_both",
        visible=False,
        styles={"min-height": "0"},
    )

    _ace_wrap = pn.widgets.Button(name="", width=1, height=1, margin=0, visible=False)
    _ace_wrap.jscallback(
        clicks="""
        (function(){
            function wrap(){
                document.querySelectorAll('.ace_editor').forEach(function(el){
                    try{
                        var ed=ace.edit(el);
                        ed.session.setUseWrapMode(true);
                        if(ed.renderer && ed.renderer.$scrollbarV)
                            ed.renderer.$scrollbarV.element.style.overflowX='hidden';
                        ed.resize();
                    }catch(e){}
                });
            }
            if(typeof ace==='undefined'){setTimeout(function(){wrap();},300);return;}
            wrap();
            setTimeout(wrap,600);
            setTimeout(wrap,1500);
        })();
        """,
    )
    pn.state.onload(lambda: setattr(_ace_wrap, "clicks", 1))

    # ── Build panel contents ───────────────────────────────────────────────
    insert_figure_btn = pn.widgets.Button(
        name="Insert figure",
        icon="photo",
        icon_size="11px",
        button_type="default",
        button_style="outline",
        width=EXPLORER_INNER_WIDTH,
        sizing_mode="fixed",
        margin=(0, 0, 2, 0),
        css_classes=["dash-explorer-item", "dash-explorer-refresh"],
        styles={**EXPLORER_LIST_BTN_STYLES, "color": "#9fd4f5", "font-size": "13px"},
        stylesheets=[EXPLORER_BUTTON_STYLESHEETS],
    )
    insert_figure_btn.js_on_click(
        code="if (window.showInsertFigureModal) window.showInsertFigureModal();",
    )

    explorer_view = build_file_tree_sidebar(
        project_root=qmd_path.parent,
        on_file_click=_on_file_click,
        insert_figure_button=insert_figure_btn,
    )
    explorer_view.sizing_mode = "stretch_height"
    explorer_view.styles = {**getattr(explorer_view, "styles", {}), "min-height": "0"}

    # ── Explorer as permanent collapsible left sidebar ────────────────────
    explorer_view.css_classes = [*getattr(explorer_view, "css_classes", []), "explorer-sidebar-inner"]
    explorer_view.styles = {
        **getattr(explorer_view, "styles", {}),
        "flex": "1 1 auto",
        "min-width": "0",
        "overflow": "hidden",
    }

    _EXPLORER_COLLAPSE_BTN_HTML = (
        '<div id="explorer-collapse-btn"'
        ' style="width:24px;flex:0 0 24px;background:transparent;'
        'cursor:pointer;display:flex;align-items:center;justify-content:center;'
        'font-size:16px;color:#aaa;user-select:none;transition:color 0.15s ease;"'
        ' title="Toggle explorer"'
        ' onmouseover="this.style.color=\'#fff\';"'
        ' onmouseout="this.style.color=\'#aaa\';"'
        ' onclick="if(window.__explorerCollapseToggle)window.__explorerCollapseToggle();">'
        '\u2039</div>'
    )
    explorer_collapse_btn = pn.pane.HTML(
        _EXPLORER_COLLAPSE_BTN_HTML,
        sizing_mode="stretch_height",
        width=24,
        styles={"flex": "0 0 24px", "min-height": "0"},
    )
    explorer_sidebar = pn.Row(
        explorer_view,
        sizing_mode="stretch_height",
        width=248,
        styles={"flex": "0 0 248px", "min-width": "20px", "min-height": "0", "overflow": "hidden"},
        css_classes=["explorer-sidebar-wrap"],
    )

    editor_view = pn.Column(
        tab_bar,
        editor,
        editor_placeholder,
        _ace_wrap,
        sizing_mode="stretch_both",
        styles={"min-height": "0", "background": THEME["bg_panel"]},
    )

    settings_view = build_settings_page()

    _rebuild_tab_bar()

    paper_content, paper_page = build_paper_page(config)

    main_panel = pn.Column(
        editor_view,
        sizing_mode="stretch_both",
        min_width=200,
        styles={"min-height": "0", "flex": "1 1 auto"},
        css_classes=["main-panel"],
    )

    preview_toolbar = pn.Row(
        paper_page.rebuild_btn,
        paper_page.export_btn,
        paper_page.pdf_link,
        sizing_mode="stretch_width",
        height=32,
        margin=0,
        styles={
            "padding": "2px 6px",
            "background": THEME["toolbar_bg"],
            "border-bottom": f"1px solid {THEME['border_subtle']}",
            "align-items": "center",
            "flex": "0 0 32px",
        },
    )
    preview_container = pn.Column(
        preview_toolbar,
        paper_content,
        sizing_mode="stretch_both",
        min_width=320,
        styles={"min-height": "0", "flex": "1 1 auto"},
        css_classes=["pane-right", "preview-pane"],
    )

    # ── Emit SPLIT_CONFIG (selectors only, no panel switching) ───────────
    split_config_pane = pn.pane.HTML(
        "<script>window.SPLIT_CONFIG={"
        '"mainPanelSelector":".main-panel",'
        '"previewPanelSelector":".pane-right",'
        '"gutterSelector":"[class*=\'split-gutter--between-main-preview\']",'
        '"panels":[],"defaultPanel":"editor"};</script>',
        width=0, height=0, margin=0,
        styles={"display": "none"},
    )

    # ── Toolbar ───────────────────────────────────────────────────────────
    toolbar = pn.Row(
        explorer_collapse_btn,
        pn.pane.HTML(
            '<span class="dash-toolbar-title" '
            'style="font-size:12px;font-weight:600;color:#fff;">4Dpaper</span>',
            width=72,
            margin=(0, 6, 0, 2),
        ),
        sizing_mode="stretch_width",
        height=32,
        margin=0,
        styles={
            "padding": "2px 8px",
            "background": THEME["toolbar_bg"],
            "border-bottom": f"1px solid {THEME['border_subtle']}",
            "align-items": "center",
        },
    )

    body = pn.Row(
        split_config_pane,
        explorer_sidebar,
        _split_gutter("explorer-editor"),
        main_panel,
        _split_gutter("main-preview"),
        preview_container,
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
            "border": f"1px solid {THEME['border_subtle']}",
            "background": THEME["bg_app"],
            "overflow": "hidden",
            "min-height": "0",
            "flex": "1 1 auto",
        },
    )


app = create_app()
app.servable()
