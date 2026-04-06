"""Paper preview: segmented pill toggle (Interactive / Paper) + Ctrl+Wheel zoom."""
from __future__ import annotations

import html as html_mod
import threading
import time
from pathlib import Path
from typing import Any

import panel as pn
import param

from dashboard.theme import THEME
from dashboard.utils import run_quarto_render

# ── Pill toggle stylesheet (shadow-DOM) ───────────────────────────────────────
_PILL_SS = """
:host .bk-btn-group {
  display: flex;
  background: rgba(255,255,255,0.05);
  border-radius: 5px;
  padding: 2px;
  gap: 1px;
  border: 1px solid rgba(255,255,255,0.1);
  align-items: center !important;
  justify-content: center !important;
  height: 26px !important;
}
:host .bk-btn {
  height: 22px !important;
  line-height: 22px !important;
  padding: 0 10px !important;
  font-size: 11px !important;
  font-family: system-ui, -apple-system, sans-serif !important;
  border: none !important;
  border-radius: 4px !important;
  background: transparent !important;
  color: #8ab4cc !important;
  font-weight: 500 !important;
  letter-spacing: 0.01em !important;
  transition: background 0.12s, color 0.12s !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  vertical-align: middle !important;
  margin: 0 !important;
}
:host .bk-btn:hover:not(.bk-active) {
  background: rgba(255,255,255,0.08) !important;
  color: #fff !important;
}
:host .bk-btn.bk-active {
  background: rgba(19,138,124,0.35) !important;
  color: #fff !important;
  box-shadow: inset 0 0 0 1px rgba(19,138,124,0.55) !important;
}
:host .bk-btn span {
  display: flex !important;
  align-items: center !important;
  height: 100% !important;
}
"""

# Ctrl+Wheel zoom injected once into the page
_ZOOM_JS = """
<script>
(function(){
  var _zoom=1.0, _badge=null, _ft=null;
  function _showBadge(z){
    if(!_badge){
      _badge=document.createElement('div');
      _badge.style.cssText='position:fixed;bottom:72px;right:20px;'
        +'background:rgba(14,14,14,0.88);color:#fff;padding:4px 10px;'
        +'border-radius:4px;font-family:monospace;font-size:12px;'
        +'z-index:9999;pointer-events:none;opacity:0;'
        +'transition:opacity 0.15s;';
      document.body.appendChild(_badge);
    }
    _badge.textContent=Math.round(z*100)+'%';
    _badge.style.opacity='1';
    clearTimeout(_ft);
    _ft=setTimeout(function(){_badge.style.opacity='0';},1100);
  }
  function _apply(z){
    _zoom=Math.max(0.2,Math.min(2.5,z));
    document.querySelectorAll('.pzoom-frame').forEach(function(fr){
      fr.style.zoom=_zoom;
      fr.style.width=(100/_zoom)+'%';
      fr.style.height=(100/_zoom)+'%';
    });
    _showBadge(_zoom);
  }
  document.addEventListener('wheel',function(e){
    if(!e.ctrlKey&&!e.metaKey) return;
    var t=e.target, inP=false;
    while(t){if(t.classList&&t.classList.contains('pane-right')){inP=true;break;}t=t.parentElement;}
    if(!inP) return;
    e.preventDefault();
    _apply(_zoom+(e.deltaY<0?0.1:-0.1));
  },{passive:false});
})();
</script>
"""


class PaperPage(param.Parameterized):
    is_building = param.Boolean(default=False)

    def __init__(self, config: dict[str, Any], **params):
        super().__init__(**params)
        self._config = config
        self._qmd_path = Path(config["quarto_paper_path"])
        self._log_lines: list[str] = []
        self._log_cb = None
        self._hide_timer: threading.Timer | None = None
        self._status_text = ""
        self._status_type = "info"
        self._build_start: float | None = None

        # Paper-view state
        self._paper_view_enabled = False
        self._paper_view_building = False
        self._paper_view_cb = None
        self._paper_view_hide_timer: threading.Timer | None = None

        self._rebuild_html_btn = pn.widgets.Button(
            name="Compile",
            icon="reload",
            icon_size="1em",
            button_type="primary",
            height=26,
            margin=0,
            styles={
                "font-size": "11px",
                "letter-spacing": "0.01em",
                "font-family": "system-ui, -apple-system, sans-serif",
                "font-weight": "500",
            },
            css_classes=["btn-primary"],
        )
        self._export_pdf_btn = pn.widgets.Button(
            name="Export",
            icon="download",
            icon_size="1em",
            button_type="default",
            height=26,
            margin=0,
            styles={
                "font-size": "11px",
                "letter-spacing": "0.01em",
                "font-family": "system-ui, -apple-system, sans-serif",
                "font-weight": "500",
            },
            css_classes=["btn-secondary"],
        )

        # Segmented pill toggle — lives in the toolbar (returned via .view_toggle)
        self._view_toggle = pn.widgets.RadioButtonGroup(
            name='View Mode',
            options=['Interactive', 'Paper'],
            value='Interactive',
            button_type='default',
            margin=(0, 4, 0, 0)
        )

        self._header_status_indicator = pn.pane.HTML(
            '<span style="font-size:11px;color:#c8dff0;opacity:0.8;">(Status: Up to date)</span>',
            margin=(0, 10, 0, 0),
            align='center'
        )

        self._overlay = pn.pane.HTML(
            "",
            sizing_mode="stretch_width",
            visible=False,
            styles={
                "position": "absolute",
                "top": "8px",
                "left": "8px",
                "right": "8px",
                "z-index": "100",
            },
        )

        self._iframe = pn.pane.HTML(
            f'<div style="border:1px dashed {THEME["border_subtle"]};padding:2.5rem 1.5rem;'
            f'text-align:center;color:{THEME["text_muted"]};border-radius:6px;'
            f'background:{THEME["bg_panel"]};font-size:13px;line-height:1.5;">'
            f'<strong style="color:{THEME["text_primary"]};">HTML preview</strong><br><br>'
            f'Click <strong>Build HTML</strong> to render the paper here.</div>',
            sizing_mode="stretch_both",
        )

        self._paper_view_iframe = pn.pane.HTML(
            f'<div style="border:1px dashed {THEME["border_subtle"]};padding:2.5rem 1.5rem;'
            f'text-align:center;color:{THEME["text_muted"]};border-radius:6px;'
            f'background:{THEME["bg_panel"]};font-size:13px;line-height:1.5;">'
            f'<strong style="color:{THEME["text_primary"]};">Paper View</strong><br><br>'
            f'Switch to <strong>Paper</strong> to start auto-rebuilding every 30 s.</div>',
            sizing_mode="stretch_both",
        )

        self._paper_view_status = pn.pane.HTML(
            "",
            sizing_mode="stretch_width",
            visible=False,
            styles={
                "position": "absolute",
                "top": "8px",
                "left": "8px",
                "right": "8px",
                "z-index": "100",
            },
        )
        self._paper_view_start: float | None = None
        self._paper_view_log_cb = None

        self._download_trigger = pn.pane.HTML("", width=0, height=0, margin=0, styles={"display": "none"})

        self._rebuild_html_btn.on_click(self._on_rebuild_html)
        self._export_pdf_btn.on_click(self._on_export_pdf)

    # ── iframe helper ─────────────────────────────────────────────────────────

    @staticmethod
    def _make_iframe_html(src: str, bg: str) -> str:
        return (
            f'<div class="pzoom-outer" '
            f'style="width:100%;height:100%;overflow:auto;">'
            f'<iframe class="pzoom-frame" src="{src}" '
            f'frameborder="0" '
            f'style="border:none;display:block;width:100%;height:100%;background:{bg};">'
            f'</iframe></div>'
        )

    # ── Paper-view auto-rebuild ───────────────────────────────────────────────

    def _enable_paper_view(self) -> None:
        """Called once when the user first switches to the Paper slot."""
        if self._paper_view_enabled:
            return
        self._paper_view_enabled = True
        self._paper_view_cb = pn.state.add_periodic_callback(
            self._tick_paper_view,
            period=30_000,
        )
        self._tick_paper_view()

    def _tick_paper_view(self) -> None:
        if self._paper_view_building or self.is_building:
            return
        self._paper_view_building = True
        self._paper_view_start = time.time()
        self._set_status_label("Building...")
        self._update_paper_view_status("Building paper view…", "warning")
        if self._paper_view_log_cb is not None:
            self._paper_view_log_cb.stop()
        self._paper_view_log_cb = pn.state.add_periodic_callback(
            self._refresh_paper_view_status,
            period=500,
            count=600,
        )
        doc = pn.state.curdoc
        threading.Thread(target=self._run_paper_view_build, args=(doc,), daemon=True).start()

    def _update_paper_view_status(self, text: str, status_type: str = "info") -> None:
        colors = {
            "info": THEME["info"],
            "warning": THEME["warning"],
            "success": THEME["success"],
            "danger": THEME["danger"],
        }
        color = colors.get(status_type, THEME["info"])
        elapsed_html = ""
        if self._paper_view_start is not None and self._paper_view_building:
            elapsed = int(time.time() - self._paper_view_start)
            elapsed_html = (
                f'<div style="color:{THEME["text_muted"]};font-size:11px;margin-top:4px;">'
                f"{elapsed}s elapsed</div>"
            )
        self._paper_view_status.object = (
            f'<div style="background:rgba(24,22,20,0.94);color:{THEME["text_primary"]};'
            f'padding:10px 14px;border-radius:6px;font-family:monospace;'
            f'font-size:12px;box-shadow:0 4px 12px rgba(0,0,0,0.45);">'
            f'<div style="color:{color};font-weight:bold;">'
            f'{html_mod.escape(text)}</div>{elapsed_html}</div>'
        )
        self._paper_view_status.visible = True

    def _refresh_paper_view_status(self) -> None:
        if self._paper_view_building:
            self._update_paper_view_status("Building paper view…", "warning")

    def _run_paper_view_build(self, doc) -> None:
        log: list[str] = []
        try:
            exit_code = run_quarto_render(self._qmd_path, log, output_format="paperview")
        except Exception as exc:
            exit_code = 1
            log.append(f"[ERROR] {exc}")
        finally:
            self._paper_view_building = False
            if self._paper_view_log_cb is not None:
                self._paper_view_log_cb.stop()
                self._paper_view_log_cb = None

        if exit_code == 0:
            ts = int(time.time())
            elapsed = int(time.time() - self._paper_view_start) if self._paper_view_start else 0
            self._paper_view_start = None
            if doc is not None:
                doc.add_next_tick_callback(lambda: self._finish_paper_view(ts, elapsed))
        else:
            self._paper_view_start = None
            if doc is not None:
                doc.add_next_tick_callback(
                    lambda: self._update_paper_view_status("Build failed. Check logs.", "danger")
                )
                self._set_status_label("Build failed")

    def _finish_paper_view(self, ts: int, elapsed: int) -> None:
        self._update_paper_view_status(f"Built successfully ({elapsed}s)", "success")
        self._set_status_label("Up to date")
        if self._paper_view_hide_timer is not None:
            self._paper_view_hide_timer.cancel()

        doc = pn.state.curdoc

        def _hide():
            try:
                doc.add_next_tick_callback(
                    lambda: setattr(self._paper_view_status, "visible", False)
                )
            except Exception:
                pass
            self._paper_view_hide_timer = None

        self._paper_view_hide_timer = threading.Timer(3.0, _hide)
        self._paper_view_hide_timer.daemon = True
        self._paper_view_hide_timer.start()
        self._paper_view_iframe.object = self._make_iframe_html(
            f"/output/analysis_report-paperview.html?t={ts}", THEME["bg_app"]
        )

    # ── HTML / PDF build logic ────────────────────────────────────────────────

    def _update_overlay(
        self,
        status_text: str,
        status_type: str = "info",
        show_log: bool = True,
    ) -> None:
        self._status_text = status_text
        self._status_type = status_type
        colors = {
            "info": THEME["info"],
            "warning": THEME["warning"],
            "success": THEME["success"],
            "danger": THEME["danger"],
        }
        color = colors.get(status_type, THEME["info"])
        elapsed_html = ""
        if self._build_start is not None and self.is_building:
            elapsed = int(time.time() - self._build_start)
            elapsed_html = (
                f'<div style="color:{THEME["text_muted"]};font-size:11px;margin-bottom:4px;">'
                f"{elapsed}s elapsed</div>"
            )
        log_html = ""
        if show_log and self._log_lines:
            escaped = "<br>".join(
                html_mod.escape(line) for line in self._log_lines[-30:]
            )
            log_html = (
                f'<div style="margin-top:8px;font-size:11px;opacity:0.85;'
                f'max-height:180px;overflow-y:auto;">{escaped}</div>'
            )
        self._overlay.object = (
            f'<div style="background:rgba(24,22,20,0.94);color:{THEME["text_primary"]};'
            f'padding:12px 16px;border-radius:6px;font-family:monospace;'
            f'font-size:12px;box-shadow:0 4px 12px rgba(0,0,0,0.45);">'
            f'<div style="color:{color};font-weight:bold;margin-bottom:4px;">'
            f'{html_mod.escape(status_text)}</div>{elapsed_html}{log_html}</div>'
        )
        self._overlay.visible = True

    def _hide_overlay(self) -> None:
        self._overlay.visible = False
        self._hide_timer = None

    def _schedule_hide_overlay(self, doc, delay_s: float = 4.0) -> None:
        if self._hide_timer is not None:
            self._hide_timer.cancel()

        def _trigger():
            try:
                doc.add_next_tick_callback(self._hide_overlay)
            except Exception:
                pass

        self._hide_timer = threading.Timer(delay_s, _trigger)
        self._hide_timer.daemon = True
        self._hide_timer.start()

    def _on_rebuild_html(self, event) -> None:
        if self.is_building:
            return
        self.is_building = True
        self._rebuild_html_btn.disabled = True
        self._export_pdf_btn.disabled = True
        self._log_lines.clear()
        self._build_start = time.time()
        self._set_status_label("Building HTML...")
        self._update_overlay("Building HTML paper...", "warning")

        doc = pn.state.curdoc

        def _run() -> None:
            try:
                self._log_lines.append("[INFO] Running quarto render --to html...")
                code = run_quarto_render(self._qmd_path, self._log_lines)
                doc.add_next_tick_callback(lambda: self._finish_html(code, doc))
            except Exception as exc:
                self._log_lines.append(f"[ERROR] {exc}")
                doc.add_next_tick_callback(lambda: self._finish_html(1, doc))

        threading.Thread(target=_run, daemon=True).start()
        if self._log_cb is not None:
            self._log_cb.stop()
            self._log_cb = None
        self._log_cb = pn.state.add_periodic_callback(
            self._refresh_log,
            period=500,
            count=600,
        )

    def _finish_html(self, exit_code: int, doc) -> None:
        if self._log_cb is not None:
            self._log_cb.stop()
            self._log_cb = None
        self.is_building = False
        self._rebuild_html_btn.disabled = False
        self._export_pdf_btn.disabled = False

        if exit_code == 0:
            elapsed = (
                f" ({int(time.time() - self._build_start)}s)"
                if self._build_start
                else ""
            )
            self._build_start = None
            self._update_overlay(
                f"HTML paper built successfully!{elapsed}",
                "success",
                show_log=False,
            )
            self._set_status_label("Up to date")
            self._schedule_hide_overlay(doc, delay_s=4.0)
            ts = int(time.time())
            self._iframe.object = self._make_iframe_html(
                f"/output/analysis_report.html?t={ts}", THEME["bg_app"]
            )
        else:
            self._build_start = None
            self._set_status_label("Build failed")
            self._update_overlay(
                f"Build failed (exit code {exit_code}). See log.",
                "danger",
            )

    def _on_export_pdf(self, event) -> None:
        if self.is_building:
            return
        self.is_building = True
        self._rebuild_html_btn.disabled = True
        self._export_pdf_btn.disabled = True
        self._log_lines.clear()
        self._build_start = time.time()
        self._set_status_label("Exporting PDF...")
        self._update_overlay("Exporting PDF...", "warning")

        doc = pn.state.curdoc

        def _run() -> None:
            try:
                self._log_lines.append(
                    "[INFO] Running quarto render --to pdf...\n"
                    "[INFO] Using camera positions from current HTML preview. "
                    "Rotate figures in the HTML view to update the viewpoint before exporting."
                )
                exit_code = run_quarto_render(
                    self._qmd_path,
                    self._log_lines,
                    output_format="pdf",
                )
                pdf_path = self._qmd_path.parent / "_output" / "analysis_report.pdf"
                doc.add_next_tick_callback(
                    lambda: self._finish_pdf(exit_code, pdf_path, doc)
                )
            except Exception as exc:
                self._log_lines.append(f"[ERROR] {exc}")
                doc.add_next_tick_callback(lambda: self._finish_pdf(1, None, doc))

        threading.Thread(target=_run, daemon=True).start()
        if self._log_cb is not None:
            self._log_cb.stop()
            self._log_cb = None
        self._log_cb = pn.state.add_periodic_callback(
            self._refresh_log,
            period=500,
            count=600,
        )

    def _finish_pdf(self, exit_code: int, pdf_path, doc) -> None:
        if self._log_cb is not None:
            self._log_cb.stop()
            self._log_cb = None
        self.is_building = False
        self._rebuild_html_btn.disabled = False
        self._export_pdf_btn.disabled = False

        if exit_code == 0 and pdf_path and Path(pdf_path).exists():
            elapsed = (
                f" ({int(time.time() - self._build_start)}s)"
                if self._build_start
                else ""
            )
            self._build_start = None
            self._update_overlay(
                f"PDF exported successfully!{elapsed}",
                "success",
                show_log=False,
            )
            self._set_status_label("Up to date")
            self._schedule_hide_overlay(doc, delay_s=4.0)
            
            ts = int(time.time())
            self._download_trigger.object = f"""
            <img src onerror="
                var a = document.createElement('a');
                a.href = '/output/analysis_report.pdf?t={ts}';
                a.download = 'analysis_report.pdf';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            " style="display:none;">
            """
        else:
            self._build_start = None
            self._set_status_label("Export failed")
            self._update_overlay(
                f"PDF export failed (exit code {exit_code}). See log.",
                "danger",
            )

    def _refresh_log(self) -> None:
        if self.is_building:
            self._update_overlay(self._status_text, self._status_type)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def rebuild_btn(self) -> pn.widgets.Button:
        return self._rebuild_html_btn

    @property
    def export_btn(self) -> pn.widgets.Button:
        return self._export_pdf_btn

    @property
    def header_status_indicator(self) -> pn.pane.HTML:
        return self._header_status_indicator

    @property
    def view_toggle(self) -> pn.widgets.RadioButtonGroup:
        return self._view_toggle

    def _set_status_label(self, text: str) -> None:
        self._header_status_indicator.object = f'<span style="font-size:11px;color:#c8dff0;opacity:0.8;">(Status: {text})</span>'

    def layout(self) -> pn.Column:
        html_slot = pn.Column(
            self._overlay,
            self._iframe,
            sizing_mode="stretch_both",
            min_height=0,
            styles={"position": "relative", "flex": "1 1 auto"},
        )
        paper_slot = pn.Column(
            self._paper_view_status,
            self._paper_view_iframe,
            sizing_mode="stretch_both",
            min_height=0,
            visible=False,
            styles={"position": "relative", "flex": "1 1 auto"},
        )

        def _on_toggle(event):
            is_paper = event.new == "Paper"
            html_slot.visible = not is_paper
            paper_slot.visible = is_paper
            if is_paper:
                self._enable_paper_view()

        self._view_toggle.param.watch(_on_toggle, "value")

        zoom_js = pn.pane.HTML(
            _ZOOM_JS,
            width=0, height=0, margin=0,
            styles={"display": "none"},
        )

        return pn.Column(
            html_slot,
            paper_slot,
            zoom_js,
            self._download_trigger,
            sizing_mode="stretch_both",
            min_height=0,
        )


def build_paper_page(config: dict[str, Any]) -> tuple[pn.Column, PaperPage]:
    page = PaperPage(config=config)
    return page.layout(), page
