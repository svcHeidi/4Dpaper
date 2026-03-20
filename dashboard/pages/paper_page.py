"""Paper tab: iframe preview + Rebuild HTML + Export PDF."""
from __future__ import annotations

import html as html_mod
import threading
import time
from pathlib import Path
from typing import Any

import panel as pn
import param

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

        # ── Buttons ──────────────────────────────────────────────────────────
        self._rebuild_html_btn = pn.widgets.Button(
            name="⚙ HTML",
            button_type="primary",
            width=75,
            height=26,
            margin=(0, 2),
            styles={"font-size": "11px"},
        )
        self._export_pdf_btn = pn.widgets.Button(
            name="📥 PDF",
            button_type="default",
            width=70,
            height=26,
            margin=(0, 2),
            styles={"font-size": "11px"},
        )

        # ── Build overlay (appears over the preview, auto-hides) ─────────
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

        # ── Iframe ───────────────────────────────────────────────────────────
        self._iframe = pn.pane.HTML(
            '<div style="border:1px dashed #555;padding:2rem;text-align:center;'
            'color:#888;border-radius:4px;">Paper preview will appear here '
            'after first build.</div>',
            min_height=750,
            sizing_mode="stretch_width",
        )

        # ── PDF link (persistent if file exists) ──────────────────────────────
        self._pdf_link = pn.pane.HTML("", sizing_mode="stretch_width", margin=(10, 8))
        self._set_pdf_link_if_exists()

        self._rebuild_html_btn.on_click(self._on_rebuild_html)
        self._export_pdf_btn.on_click(self._on_export_pdf)

    def _set_pdf_link_if_exists(self) -> None:
        """Check if analysis_report.pdf exists and set the link if so."""
        pdf_path = self._qmd_path.parent / "_output" / "analysis_report.pdf"
        if pdf_path.exists():
            ts = int(time.time())
            self._pdf_link.object = (
                f'<a href="/output/analysis_report.pdf?t={ts}" target="_blank" '
                f'style="background:#007bff; color:white; padding:4px 8px; '
                f'border-radius:4px; text-decoration:none; font-size:11px; '
                f'font-weight:bold; font-family:sans-serif; display:inline-block;'
                f'margin: 0 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.3);">'
                f'📄 PDF</a>'
            )

    # ── Overlay helpers ────────────────────────────────────────────────────

    def _update_overlay(self, status_text: str, status_type: str = "info",
                        show_log: bool = True) -> None:
        self._status_text = status_text
        self._status_type = status_type
        colors = {
            "info": "#17a2b8", "warning": "#ffc107",
            "success": "#28a745", "danger": "#dc3545",
        }
        color = colors.get(status_type, "#17a2b8")
        elapsed_html = ""
        if self._build_start is not None and self.is_building:
            elapsed = int(time.time() - self._build_start)
            elapsed_html = (
                f'<div style="color:#aaa;font-size:11px;margin-bottom:4px;">'
                f'⏱ {elapsed}s elapsed</div>'
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
            f'<div style="background:rgba(30,30,30,0.92);color:#d4d4d4;'
            f'padding:12px 16px;border-radius:6px;font-family:monospace;'
            f'font-size:12px;box-shadow:0 4px 12px rgba(0,0,0,0.4);">'
            f'<div style="color:{color};font-weight:bold;margin-bottom:4px;">'
            f'{html_mod.escape(status_text)}</div>{elapsed_html}{log_html}</div>'
        )
        self._overlay.visible = True

    def _hide_overlay(self) -> None:
        self._overlay.visible = False
        self._hide_timer = None

    def _schedule_hide_overlay(self, doc, delay_s: float = 4.0) -> None:
        """Schedule _hide_overlay to run on the Bokeh doc after *delay_s* seconds.

        Uses a threading.Timer + doc.add_next_tick_callback so it works in
        background threads and doesn't require a running asyncio event loop.
        """
        if self._hide_timer is not None:
            self._hide_timer.cancel()

        def _trigger():
            try:
                doc.add_next_tick_callback(self._hide_overlay)
            except Exception:
                pass  # session may have closed

        self._hide_timer = threading.Timer(delay_s, _trigger)
        self._hide_timer.daemon = True
        self._hide_timer.start()

    # ── HTML rebuild ──────────────────────────────────────────────────────────

    def _on_rebuild_html(self, event) -> None:
        if self.is_building:
            return
        self.is_building = True
        self._rebuild_html_btn.disabled = True
        self._export_pdf_btn.disabled = True
        self._log_lines.clear()
        self._pdf_link.object = ""
        self._build_start = time.time()
        self._update_overlay("Building HTML paper\u2026", "warning")

        # Capture Bokeh document here (on the event loop) before spawning thread.
        doc = pn.state.curdoc

        def _run() -> None:
            try:
                self._log_lines.append("[INFO] Running quarto render --to html\u2026")
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
            self._refresh_log, period=500, count=600,
        )

    def _finish_html(self, exit_code: int, doc) -> None:
        if self._log_cb is not None:
            self._log_cb.stop()
            self._log_cb = None
        self.is_building = False
        self._rebuild_html_btn.disabled = False
        self._export_pdf_btn.disabled = False

        if exit_code == 0:
            elapsed = f" ({int(time.time() - self._build_start)}s)" if self._build_start else ""
            self._build_start = None
            self._update_overlay(
                f"\u2713 HTML paper built successfully!{elapsed}", "success", show_log=False,
            )
            self._schedule_hide_overlay(doc, delay_s=4.0)
            ts = int(time.time())
            self._iframe.object = (
                f'<iframe src="/output/analysis_report.html?t={ts}" '
                f'width="100%" height="750px" frameborder="0" '
                f'style="border:none;border-radius:4px;"></iframe>'
            )
        else:
            self._update_overlay(
                f"\u2717 Build failed (exit code {exit_code}). See log.",
                "danger",
            )

    # ── PDF export ────────────────────────────────────────────────────────────

    def _on_export_pdf(self, event) -> None:
        if self.is_building:
            return
        self.is_building = True
        self._rebuild_html_btn.disabled = True
        self._export_pdf_btn.disabled = True
        self._log_lines.clear()
        self._pdf_link.object = ""
        self._build_start = time.time()
        self._update_overlay("Exporting PDF\u2026", "warning")

        doc = pn.state.curdoc

        def _run() -> None:
            try:
                self._log_lines.append(
                    "[INFO] Running quarto render --to pdf\u2026\n"
                    "[INFO] Using camera positions from current HTML preview. "
                    "Rotate figures in the HTML view to update the viewpoint before exporting."
                )
                exit_code = run_quarto_render(
                    self._qmd_path, self._log_lines, output_format="pdf",
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
            self._refresh_log, period=500, count=600,
        )

    def _finish_pdf(self, exit_code: int, pdf_path, doc) -> None:
        if self._log_cb is not None:
            self._log_cb.stop()
            self._log_cb = None
        self.is_building = False
        self._rebuild_html_btn.disabled = False
        self._export_pdf_btn.disabled = False

        if exit_code == 0 and pdf_path and Path(pdf_path).exists():
            elapsed = f" ({int(time.time() - self._build_start)}s)" if self._build_start else ""
            self._build_start = None
            self._update_overlay(
                f"✓ PDF exported successfully!{elapsed}", "success", show_log=False,
            )
            self._schedule_hide_overlay(doc, delay_s=4.0)
            cache_bust = int(time.time())
            self._pdf_link.object = (
                f'<a href="/output/analysis_report.pdf?t={cache_bust}" target="_blank" '
                f'style="background:#007bff; color:white; padding:4px 8px; '
                f'border-radius:4px; text-decoration:none; font-size:11px; '
                f'font-weight:bold; font-family:sans-serif; display:inline-block;'
                f'margin: 0 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.3);">'
                f'📄 PDF</a>'
            )
        else:
            self._update_overlay(
                f"\u2717 PDF export failed (exit code {exit_code}). See log.",
                "danger",
            )

    # ── Shared ────────────────────────────────────────────────────────────────

    def _refresh_log(self) -> None:
        if self.is_building:
            self._update_overlay(self._status_text, self._status_type)

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
        preview_container = pn.Column(
            self._overlay,
            self._iframe,
            sizing_mode="stretch_width",
            styles={"position": "relative"},
        )
        return pn.Column(
            preview_container,
            sizing_mode="stretch_width",
        )


def build_paper_page(config: dict[str, Any]) -> tuple[pn.Column, PaperPage]:
    """Return (layout, page_instance) so callers can access buttons."""
    page = PaperPage(config=config)
    return page.layout(), page
