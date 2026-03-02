"""Paper tab: rebuild Quarto paper and open preview."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import panel as pn
import param

from dashboard.utils import run_quarto_render


class PaperPage(param.Parameterized):
    log_text = param.String(default="")
    is_building = param.Boolean(default=False)
    last_exit_code = param.Integer(default=-1)

    def __init__(self, config: dict[str, Any], **params):
        super().__init__(**params)
        self._qmd_path = Path(config["quarto_paper_path"])
        self._log_lines: list[str] = []

        self._rebuild_btn = pn.widgets.Button(
            name="⚙  Rebuild Paper",
            button_type="primary",
            sizing_mode="stretch_width",
        )
        self._status_badge = pn.pane.Alert(
            "No build yet. Click 'Rebuild Paper' to render the Quarto document.",
            alert_type="info",
        )
        self._log_pane = pn.pane.Str(
            "",
            styles={
                "font-family": "monospace", "font-size": "12px",
                "overflow-y": "auto", "max-height": "300px",
                "background": "#1e1e1e", "color": "#d4d4d4",
                "padding": "8px", "border-radius": "4px",
            },
            sizing_mode="stretch_width",
        )
        self._open_link = pn.pane.HTML("", sizing_mode="stretch_width")

        self._rebuild_btn.on_click(self._on_rebuild_click)

    def _on_rebuild_click(self, event) -> None:
        if self.is_building:
            return
        self.is_building = True
        self._rebuild_btn.disabled = True
        self._log_lines.clear()
        self._status_badge.object = "Building…"
        self._status_badge.alert_type = "warning"
        self._open_link.object = ""

        def _run():
            code = run_quarto_render(self._qmd_path, self._log_lines)
            pn.state.execute(lambda: self._finish(code))

        threading.Thread(target=_run, daemon=True).start()
        pn.state.add_periodic_callback(self._refresh_log, period=500, count=120)

    def _refresh_log(self) -> None:
        self._log_pane.object = "\n".join(self._log_lines)

    def _finish(self, exit_code: int) -> None:
        self.last_exit_code = exit_code
        self.is_building = False
        self._rebuild_btn.disabled = False
        self._log_pane.object = "\n".join(self._log_lines)

        if exit_code == 0:
            output_html = self._qmd_path.parent / "_output" / "analysis_report.html"
            self._status_badge.object = "✓ Paper built successfully!"
            self._status_badge.alert_type = "success"
            self._open_link.object = (
                f'<a href="file://{output_html}" target="_blank" '
                f'style="font-size:1rem;">📄 Open analysis_report.html</a>'
            )
        else:
            self._status_badge.object = f"✗ Build failed (exit code {exit_code}). See log."
            self._status_badge.alert_type = "danger"

    def layout(self) -> pn.Column:
        return pn.Column(
            pn.pane.Markdown("### Rebuild the 4Dpaper"),
            pn.pane.Markdown(
                "Clicking 'Rebuild Paper' runs `quarto render analysis_report.qmd`. "
                "The paper will embed whatever post-processing outputs exist in `plots.json`."
            ),
            self._rebuild_btn,
            self._status_badge,
            self._open_link,
            pn.layout.Divider(),
            pn.pane.Markdown("**Build log:**"),
            self._log_pane,
            sizing_mode="stretch_width",
        )


def build_paper_page(config: dict[str, Any]) -> pn.Column:
    page = PaperPage(config=config)
    return page.layout()
