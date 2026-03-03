"""Paper tab: iframe preview + Rebuild HTML + Export PDF."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import panel as pn
import param

from dashboard.utils import run_pvpython_render, run_quarto_render


class PaperPage(param.Parameterized):
    is_building = param.Boolean(default=False)

    def __init__(self, config: dict[str, Any], **params):
        super().__init__(**params)
        self._config = config
        self._qmd_path = Path(config["quarto_paper_path"])
        self._log_lines: list[str] = []

        # ── Buttons ──────────────────────────────────────────────────────────
        self._rebuild_html_btn = pn.widgets.Button(
            name="⚙  Rebuild HTML",
            button_type="primary",
            width=180,
        )
        self._export_pdf_btn = pn.widgets.Button(
            name="📥  Export PDF",
            button_type="default",
            width=180,
        )

        # ── Status + log ─────────────────────────────────────────────────────
        self._status_badge = pn.pane.Alert(
            "No build yet. Click 'Rebuild HTML' to render the paper.",
            alert_type="info",
            sizing_mode="stretch_width",
        )
        self._log_pane = pn.pane.Str(
            "",
            styles={
                "font-family": "monospace", "font-size": "11px",
                "overflow-y": "auto", "max-height": "200px",
                "background": "#1e1e1e", "color": "#d4d4d4",
                "padding": "8px", "border-radius": "4px",
            },
            sizing_mode="stretch_width",
        )

        # ── Iframe ───────────────────────────────────────────────────────────
        self._iframe = pn.pane.HTML(
            '<div style="border:1px dashed #ccc;padding:2rem;text-align:center;color:#888">'
            'Paper preview will appear here after first build.</div>',
            min_height=750,
            sizing_mode="stretch_width",
        )

        # ── PDF download link ─────────────────────────────────────────────────
        self._pdf_link = pn.pane.HTML("", sizing_mode="stretch_width")

        self._rebuild_html_btn.on_click(self._on_rebuild_html)
        self._export_pdf_btn.on_click(self._on_export_pdf)

    # ── HTML rebuild ──────────────────────────────────────────────────────────

    def _on_rebuild_html(self, event) -> None:
        if self.is_building:
            return
        self.is_building = True
        self._rebuild_html_btn.disabled = True
        self._export_pdf_btn.disabled = True
        self._log_lines.clear()
        self._status_badge.object = "Building HTML paper…"
        self._status_badge.alert_type = "warning"
        self._pdf_link.object = ""

        def _run() -> None:
            self._log_lines.append("[INFO] Running quarto render --to html…")
            pn.state.execute(self._refresh_log)
            code = run_quarto_render(self._qmd_path, self._log_lines)
            pn.state.execute(lambda: self._finish_html(code))

        threading.Thread(target=_run, daemon=True).start()
        pn.state.add_periodic_callback(self._refresh_log, period=500, count=120)

    def _finish_html(self, exit_code: int) -> None:
        self.is_building = False
        self._rebuild_html_btn.disabled = False
        self._export_pdf_btn.disabled = False
        self._log_pane.object = "\n".join(self._log_lines)

        if exit_code == 0:
            self._status_badge.object = "✓ HTML paper built successfully!"
            self._status_badge.alert_type = "success"
            # Refresh iframe with cache-busting timestamp
            ts = int(time.time())
            self._iframe.object = (
                f'<iframe src="/output/analysis_report.html?t={ts}" '
                f'width="100%" height="750px" frameborder="0" '
                f'style="border:none;border-radius:4px;"></iframe>'
            )
        else:
            self._status_badge.object = f"✗ Build failed (exit code {exit_code}). See log."
            self._status_badge.alert_type = "danger"

    # ── PDF export ────────────────────────────────────────────────────────────

    def _on_export_pdf(self, event) -> None:
        if self.is_building:
            return
        self.is_building = True
        self._rebuild_html_btn.disabled = True
        self._export_pdf_btn.disabled = True
        self._log_lines.clear()
        self._status_badge.object = "Checking for camera state…"
        self._status_badge.alert_type = "warning"
        self._pdf_link.object = ""

        cfg = self._config
        camera_path = Path(cfg.get("camera_state", ""))
        pv_cfg = cfg.get("paraview", {})

        def _run() -> None:
            # Step 1: pvpython figure render (requires camera state)
            if camera_path and camera_path.exists() and pv_cfg:
                self._log_lines.append("[INFO] Camera state found — rendering PDF figures…")
                pn.state.execute(self._refresh_log)

                from pathlib import Path as _Path
                figures_dir = _Path(__file__).parent.parent.parent / "state" / "figures"
                figures_dir.mkdir(parents=True, exist_ok=True)

                # Re-use camera render for the main figure (fig-vm → render_output.png)
                render_output = _Path(cfg.get("render_output", str(figures_dir / "fig-vm.png")))
                exit_code = run_pvpython_render(
                    pvpython_path=pv_cfg.get("pvpython_path", "pvpython"),
                    pvsm_path=pv_cfg.get("pvsm_path", ""),
                    foam_path=pv_cfg.get("foam_path", ""),
                    camera_state_path=camera_path,
                    output_path=render_output,
                    resolution=pv_cfg.get("render_resolution", [1920, 1080]),
                    log_lines=self._log_lines,
                )
                # Copy render output to state/figures/fig-vm.png for shortcode lookup
                if exit_code == 0 and render_output != figures_dir / "fig-vm.png":
                    import shutil
                    shutil.copy2(render_output, figures_dir / "fig-vm.png")

                if exit_code != 0:
                    pn.state.execute(lambda: self._finish_pdf(exit_code, None))
                    return
                self._log_lines.append("[INFO] PDF figures rendered.")
            else:
                self._log_lines.append(
                    "[WARN] No camera state — PDF figures will show placeholder text."
                )

            # Step 2: quarto render --to pdf
            self._log_lines.append("[INFO] Running quarto render --to pdf…")
            pn.state.execute(self._refresh_log)
            exit_code = run_quarto_render(
                self._qmd_path, self._log_lines, output_format="pdf"
            )
            pdf_path = self._qmd_path.parent / "_output" / "analysis_report.pdf"
            pn.state.execute(lambda: self._finish_pdf(exit_code, pdf_path))

        threading.Thread(target=_run, daemon=True).start()
        pn.state.add_periodic_callback(self._refresh_log, period=500, count=120)

    def _finish_pdf(self, exit_code: int, pdf_path) -> None:
        self.is_building = False
        self._rebuild_html_btn.disabled = False
        self._export_pdf_btn.disabled = False
        self._log_pane.object = "\n".join(self._log_lines)

        if exit_code == 0 and pdf_path and Path(pdf_path).exists():
            self._status_badge.object = "✓ PDF exported successfully!"
            self._status_badge.alert_type = "success"
            self._pdf_link.object = (
                f'<a href="file://{pdf_path}" target="_blank" style="font-size:1rem;">'
                f'📄 Open analysis_report.pdf</a>'
            )
        else:
            self._status_badge.object = f"✗ PDF export failed (exit code {exit_code}). See log."
            self._status_badge.alert_type = "danger"

    # ── Shared ────────────────────────────────────────────────────────────────

    def _refresh_log(self) -> None:
        self._log_pane.object = "\n".join(self._log_lines)

    def layout(self) -> pn.Column:
        return pn.Column(
            pn.pane.Markdown("### 4D Paper"),
            pn.Row(self._rebuild_html_btn, self._export_pdf_btn),
            self._status_badge,
            self._iframe,
            self._pdf_link,
            pn.layout.Divider(),
            self._log_pane,
            sizing_mode="stretch_width",
        )


def build_paper_page(config: dict[str, Any]) -> pn.Column:
    page = PaperPage(config=config)
    return page.layout()
