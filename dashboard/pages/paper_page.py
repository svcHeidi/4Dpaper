"""Paper tab: iframe preview + Rebuild HTML + Export PDF + Paper View auto-rebuild."""
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

        self._rebuild_html_btn = pn.widgets.Button(
            name="HTML",
            icon="file-type-html",
            icon_size="1em",
            button_type="primary",
            width=88,
            height=26,
            margin=(0, 2),
            styles={"font-size": "11px"},
            css_classes=["dash-btn-build-primary"],
        )
        self._export_pdf_btn = pn.widgets.Button(
            name="PDF",
            icon="file-type-pdf",
            icon_size="1em",
            button_type="default",
            width=84,
            height=26,
            margin=(0, 2),
            styles={"font-size": "11px"},
            css_classes=["dash-btn-build-secondary"],
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
            f'Run <strong>HTML</strong> to render the paper here.</div>',
            sizing_mode="stretch_both",
        )

        self._paper_view_iframe = pn.pane.HTML(
            f'<div style="border:1px dashed {THEME["border_subtle"]};padding:2.5rem 1.5rem;'
            f'text-align:center;color:{THEME["text_muted"]};border-radius:6px;'
            f'background:{THEME["bg_panel"]};font-size:13px;line-height:1.5;">'
            f'<strong style="color:{THEME["text_primary"]};">Paper View</strong><br><br>'
            f'Open this tab to start auto-rebuilding every 30 s.</div>',
            sizing_mode="stretch_both",
        )

        self._pdf_link = pn.pane.HTML("", sizing_mode="stretch_width", margin=(2, 4))
        self._set_pdf_link_if_exists()

        self._rebuild_html_btn.on_click(self._on_rebuild_html)
        self._export_pdf_btn.on_click(self._on_export_pdf)

    # ── Paper-view auto-rebuild ───────────────────────────────────────────────

    def _enable_paper_view(self) -> None:
        """Called once when the user first opens the Paper View tab."""
        if self._paper_view_enabled:
            return
        self._paper_view_enabled = True
        self._paper_view_cb = pn.state.add_periodic_callback(
            self._tick_paper_view,
            period=30_000,
        )
        # Trigger an immediate first build
        self._tick_paper_view()

    def _tick_paper_view(self) -> None:
        if self._paper_view_building or self.is_building:
            return
        self._paper_view_building = True
        threading.Thread(target=self._run_paper_view_build, daemon=True).start()

    def _run_paper_view_build(self) -> None:
        log: list[str] = []
        try:
            exit_code = run_quarto_render(self._qmd_path, log, output_format="paperview")
        except Exception as exc:
            exit_code = 1
            log.append(f"[ERROR] {exc}")
        finally:
            self._paper_view_building = False

        if exit_code == 0:
            ts = int(time.time())
            doc = pn.state.curdoc
            if doc is not None:
                doc.add_next_tick_callback(lambda: self._refresh_paper_view(ts))

    def _refresh_paper_view(self, ts: int) -> None:
        self._paper_view_iframe.object = (
            f'<iframe src="/output/analysis_report-paperview.html?t={ts}" '
            f'width="100%" frameborder="0" '
            f'style="border:none;border-radius:4px;width:100%;height:100%;'
            f'display:block;background:{THEME["bg_app"]};"></iframe>'
        )

    # ── Existing HTML / PDF build logic ──────────────────────────────────────

    def _set_pdf_link_if_exists(self) -> None:
        pdf_path = self._qmd_path.parent / "_output" / "analysis_report.pdf"
        if pdf_path.exists():
            ts = int(time.time())
            self._pdf_link.object = (
                f'<a href="/output/analysis_report.pdf?t={ts}" target="_blank" '
                f'style="background:{THEME["accent"]};color:#fff;padding:5px 10px;'
                f'border-radius:4px;text-decoration:none;font-size:11px;'
                f'font-weight:600;font-family:system-ui,sans-serif;display:inline-flex;'
                f'align-items:center;gap:5px;margin:0 4px;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.25);">PDF</a>'
            )

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
        self._pdf_link.object = ""
        self._build_start = time.time()
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
            self._schedule_hide_overlay(doc, delay_s=4.0)
            ts = int(time.time())
            self._iframe.object = (
                f'<iframe src="/output/analysis_report.html?t={ts}" '
                f'width="100%" frameborder="0" '
                f'style="border:none;border-radius:4px;width:100%;height:100%;'
                f'display:block;background:{THEME["bg_app"]};"></iframe>'
            )
        else:
            self._build_start = None
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
        self._pdf_link.object = ""
        self._build_start = time.time()
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
            self._schedule_hide_overlay(doc, delay_s=4.0)
            cache_bust = int(time.time())
            self._pdf_link.object = (
                f'<a href="/output/analysis_report.pdf?t={cache_bust}" target="_blank" '
                f'style="background:{THEME["accent"]};color:#fff;padding:5px 10px;'
                f'border-radius:4px;text-decoration:none;font-size:11px;'
                f'font-weight:600;font-family:system-ui,sans-serif;display:inline-flex;'
                f'align-items:center;gap:5px;margin:0 4px;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.25);">PDF</a>'
            )
        else:
            self._build_start = None
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
    def pdf_link(self) -> pn.pane.HTML:
        return self._pdf_link

    def layout(self) -> pn.Column:
        # Interactive HTML tab
        html_tab = pn.Column(
            pn.Column(
                self._overlay,
                self._iframe,
                sizing_mode="stretch_both",
                min_height=0,
                styles={"position": "relative", "flex": "1 1 auto"},
            ),
            sizing_mode="stretch_both",
            min_height=0,
        )

        # Paper View tab
        paper_tab = pn.Column(
            self._paper_view_iframe,
            sizing_mode="stretch_both",
            min_height=0,
        )

        tabs = pn.Tabs(
            ("Interactive HTML", html_tab),
            ("Paper View", paper_tab),
            sizing_mode="stretch_both",
            min_height=0,
        )

        # Trigger paper-view rebuild when user switches to that tab (index 1)
        def _on_tab_change(event):
            if event.new == 1:
                self._enable_paper_view()

        tabs.param.watch(_on_tab_change, "active")

        return pn.Column(tabs, sizing_mode="stretch_both", min_height=0)


def build_paper_page(config: dict[str, Any]) -> tuple[pn.Column, PaperPage]:
    page = PaperPage(config=config)
    return page.layout(), page
