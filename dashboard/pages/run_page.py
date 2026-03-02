"""Run tab: select a post-processing script, edit params/code, execute it."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import panel as pn
import param

from dashboard.utils import (
    load_config,
    resolve_param_paths,
    run_postprocessing_script,
)

pn.extension("codeeditor")


class RunPage(param.Parameterized):
    selected_script_index = param.Integer(default=0)
    log_text = param.String(default="")
    is_running = param.Boolean(default=False)

    def __init__(self, tutorial_key: str, config: dict[str, Any], **params):
        super().__init__(**params)
        self._config = config
        self._tutorial_key = tutorial_key
        self._tutorial = config["tutorials"][tutorial_key]
        self._scripts = self._tutorial["scripts"]
        self._cardiacfoam_root = Path(config["cardiacfoam_root"])
        self._log_lines: list[str] = []

        # Widgets
        self._script_selector = pn.widgets.Select(
            name="Post-Processing Script",
            options=[s["name"] for s in self._scripts],
        )
        self._param_widgets: dict[str, pn.widgets.Widget] = {}
        self._code_editor = pn.widgets.CodeEditor(
            language="python",
            theme="monokai",
            height=350,
            sizing_mode="stretch_width",
        )
        self._show_editor = pn.widgets.Toggle(
            name="▸ Advanced: Show code editor",
            value=False,
            button_type="light",
        )
        self._run_btn = pn.widgets.Button(
            name="▶  Run Post-Processing",
            button_type="success",
            sizing_mode="stretch_width",
        )
        self._log_pane = pn.pane.Str(
            "",
            styles={"font-family": "monospace", "font-size": "12px",
                    "overflow-y": "auto", "max-height": "200px",
                    "background": "#1e1e1e", "color": "#d4d4d4",
                    "padding": "8px", "border-radius": "4px"},
            sizing_mode="stretch_width",
        )

        # Wire callbacks
        self._script_selector.param.watch(self._on_script_change, "value")
        self._run_btn.on_click(self._on_run_click)
        self._show_editor.param.watch(self._on_toggle_editor, "value")

        # Initialise with first script
        self._load_script(0)

    def _load_script(self, index: int) -> None:
        script = self._scripts[index]
        module_path = self._cardiacfoam_root / script["module_relpath"]
        if module_path.exists():
            self._code_editor.value = module_path.read_text()
        else:
            self._code_editor.value = f"# File not found: {module_path}"

        # Rebuild param widgets from config params
        self._param_widgets = {}
        resolved = resolve_param_paths(script.get("params", {}), root=self._cardiacfoam_root)
        for key, value in resolved.items():
            if isinstance(value, bool):
                w = pn.widgets.Checkbox(name=key, value=value)
            else:
                w = pn.widgets.TextInput(name=key, value=str(value))
            self._param_widgets[key] = w

    def _on_script_change(self, event) -> None:
        idx = [s["name"] for s in self._scripts].index(event.new)
        self.selected_script_index = idx
        self._load_script(idx)

    def _on_toggle_editor(self, event) -> None:
        pass  # Panel's reactive layout handles visibility via .visible binding

    def _on_run_click(self, event) -> None:
        if self.is_running:
            return
        self.is_running = True
        self._log_lines.clear()
        self.log_text = "[INFO] Starting...\n"
        self._run_btn.disabled = True

        script = self._scripts[self.selected_script_index]
        module_path = self._cardiacfoam_root / script["module_relpath"]

        # Save any edits made in the code editor back to disk
        if module_path.exists():
            module_path.write_text(self._code_editor.value)

        # Collect params from widgets
        params: dict[str, Any] = {}
        for key, widget in self._param_widgets.items():
            params[key] = widget.value

        def _run():
            run_postprocessing_script(
                module_path=module_path,
                function_name=script["function"],
                params=params,
                log_lines=self._log_lines,
            )
            pn.state.execute(self._refresh_log)
            pn.state.execute(self._finish_run)

        threading.Thread(target=_run, daemon=True).start()
        pn.state.add_periodic_callback(self._refresh_log, period=500, count=60)

    def _refresh_log(self) -> None:
        self.log_text = "\n".join(self._log_lines)
        self._log_pane.object = self.log_text

    def _finish_run(self) -> None:
        self.is_running = False
        self._run_btn.disabled = False

    def layout(self) -> pn.Column:
        editor_col = pn.Column(
            self._code_editor,
            visible=self._show_editor,  # hide/show based on toggle
        )
        return pn.Column(
            pn.pane.Markdown("### Post-Processing Script"),
            self._script_selector,
            pn.pane.Markdown("#### Parameters"),
            *self._param_widgets.values(),
            self._show_editor,
            editor_col,
            pn.layout.Divider(),
            self._run_btn,
            pn.pane.Markdown("**Log output:**"),
            self._log_pane,
            sizing_mode="stretch_width",
        )


def build_run_page(tutorial_key: str, config: dict[str, Any]) -> pn.Column:
    page = RunPage(tutorial_key=tutorial_key, config=config)
    return page.layout()
