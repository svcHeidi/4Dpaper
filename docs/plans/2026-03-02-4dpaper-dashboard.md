# 4Dpaper Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Panel web dashboard inside the 4Dpapers repo that lets you select, edit, and run cardiacFoamEP post-processing scripts, view outputs, and rebuild the Quarto paper — all from a browser.

**Architecture:** Dashboard lives in `4Dpapers/dashboard/`. It calls `run_postprocessing()` from cardiacFoamEP scripts directly (no foamctl subprocess complexity) and reads the `plots.json` artifact manifest they produce. The `analysis_report.qmd` is updated to read those artifacts at render time so the paper always reflects the latest run.

**Tech Stack:** Panel ≥1.0 (already in requirements.txt), PyYAML (add to requirements), Python asyncio for non-blocking subprocess, pathlib for all paths.

---

## Project Layout After This Plan

```
4Dpapers/
├── dashboard/
│   ├── __init__.py
│   ├── app.py                   ← panel serve entry point
│   ├── config.yaml              ← paths + tutorial metadata
│   ├── utils.py                 ← config loading, script runner, manifest reader
│   └── pages/
│       ├── __init__.py
│       ├── run_page.py          ← Run tab (selector, params, code editor, log)
│       ├── outputs_page.py      ← Outputs tab (artifact grid)
│       └── paper_page.py        ← Paper tab (rebuild + preview link)
├── docs/
│   └── plans/
│       └── 2026-03-02-4dpaper-dashboard.md   ← this file
├── tests/
│   ├── test_utils.py
│   └── test_pages.py
├── analysis_report.qmd          ← add reports_dir param + manifest section
└── requirements.txt             ← add pyyaml>=6.0
```

---

## Key References (read-only, do not modify)

| Path | What it is |
|------|-----------|
| `/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/setupNiedererEtAl2012/postProcessing/line_postProcessing.py:292` | `run_postprocessing(output_dir, setup_root=None, excel_path=None, show=False)` |
| `/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/setupNiedererEtAl2012/postProcessing/points_postProcessing.py` | same contract |
| `/Users/simaocastro/cardiacFoamEP/tutorials/openfoam_driver/postprocessing/driver.py:110` | `_write_plots_manifest` — defines `plots.json` schema |
| `/Users/simaocastro/4Dpapers/analysis_report.qmd` | Quarto paper to modify |
| `/Users/simaocastro/4Dpapers/_quarto.yml` | Quarto config (do not modify) |

**plots.json schema:**
```json
{
  "schema_version": "1.0",
  "tutorial": "niederer2012",
  "output_dir": "/abs/path",
  "generated_at_utc": "...",
  "artifact_count": 2,
  "artifacts": [
    {"path": "relative/to/output_dir.html", "kind": "plot", "format": "html", "label": "..."},
    {"path": "other.png", "kind": "plot", "format": "png", "label": "..."}
  ]
}
```

---

## Task 1: Add pyyaml to requirements and create directory skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `dashboard/__init__.py`
- Create: `dashboard/pages/__init__.py`
- Create: `tests/__init__.py`

**Step 1: Add pyyaml to requirements.txt**

Open `requirements.txt` and add at the end:
```
pyyaml>=6.0
```

**Step 2: Create empty `__init__.py` files**

```bash
touch /Users/simaocastro/4Dpapers/dashboard/__init__.py
touch /Users/simaocastro/4Dpapers/dashboard/pages/__init__.py
mkdir -p /Users/simaocastro/4Dpapers/tests
touch /Users/simaocastro/4Dpapers/tests/__init__.py
```

**Step 3: Install pyyaml in the venv**

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/pip install pyyaml
```

Expected: `Successfully installed pyyaml-6.x`

**Step 4: Commit**

```bash
cd /Users/simaocastro/4Dpapers
git add requirements.txt dashboard/ tests/
git commit -m "chore: add dashboard skeleton and pyyaml dependency"
```

---

## Task 2: Write `dashboard/config.yaml`

**Files:**
- Create: `dashboard/config.yaml`

**Step 1: Create the file**

```yaml
# Paths to the two repos. Adjust if your layout differs.
cardiacfoam_root: "/Users/simaocastro/cardiacFoamEP"
quarto_paper_path: "/Users/simaocastro/4Dpapers/analysis_report.qmd"

tutorials:
  NiedererEtAl2012:
    display_name: "Niederer Et Al. 2012"
    scripts:
      - name: "Line Post-Processing"
        # Path relative to cardiacfoam_root
        module_relpath: "tutorials/NiedererEtAl2012/setupNiedererEtAl2012/postProcessing/line_postProcessing.py"
        function: "run_postprocessing"
        params:
          output_dir: "tutorials/NiedererEtAl2012/postProcessing"
          setup_root: "tutorials/NiedererEtAl2012/setupNiedererEtAl2012"
          excel_path: "tutorials/NiedererEtAl2012/setupNiedererEtAl2012/postProcessing/Niederer_graphs_webplotdigitilizer_points_slab/WebPlotDigitilizerdata.xlsx"
          show: false
      - name: "Points Post-Processing"
        module_relpath: "tutorials/NiedererEtAl2012/setupNiedererEtAl2012/postProcessing/points_postProcessing.py"
        function: "run_postprocessing"
        params:
          output_dir: "tutorials/NiedererEtAl2012/postProcessing"
          setup_root: "tutorials/NiedererEtAl2012/setupNiedererEtAl2012"
          show: false
    # plots.json written by run_postprocessing, relative to cardiacfoam_root
    plots_manifest: "tutorials/NiedererEtAl2012/postProcessing/plots.json"
```

**Step 2: Commit**

```bash
git add dashboard/config.yaml
git commit -m "feat: add dashboard config.yaml"
```

---

## Task 3: Write `dashboard/utils.py` (with TDD)

**Files:**
- Create: `dashboard/utils.py`
- Create: `tests/test_utils.py`

**Step 1: Write failing tests**

Create `tests/test_utils.py`:

```python
"""Tests for dashboard/utils.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Make dashboard importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.utils import load_config, load_manifest, resolve_param_paths


class TestLoadConfig:
    def test_returns_dict_with_tutorials_key(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "cardiacfoam_root: /foo\nquarto_paper_path: /bar.qmd\ntutorials: {}\n"
        )
        with patch("dashboard.utils.CONFIG_PATH", cfg_file):
            cfg = load_config()
        assert "tutorials" in cfg
        assert cfg["cardiacfoam_root"] == "/foo"

    def test_raises_on_missing_file(self, tmp_path):
        missing = tmp_path / "no_such.yaml"
        with patch("dashboard.utils.CONFIG_PATH", missing):
            with pytest.raises(FileNotFoundError):
                load_config()


class TestLoadManifest:
    def test_returns_artifacts_list(self, tmp_path):
        manifest = {
            "schema_version": "1.0",
            "tutorial": "test",
            "output_dir": str(tmp_path),
            "generated_at_utc": "2026-01-01T00:00:00+00:00",
            "artifact_count": 1,
            "artifacts": [{"path": "foo.html", "kind": "plot", "format": "html", "label": "Foo"}],
        }
        manifest_path = tmp_path / "plots.json"
        manifest_path.write_text(json.dumps(manifest))
        result = load_manifest(manifest_path)
        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["format"] == "html"

    def test_returns_none_when_missing(self, tmp_path):
        result = load_manifest(tmp_path / "plots.json")
        assert result is None


class TestResolveParamPaths:
    def test_resolves_relative_paths_to_absolute(self, tmp_path):
        root = tmp_path
        params = {
            "output_dir": "some/relative",
            "show": False,
        }
        resolved = resolve_param_paths(params, root=root)
        assert resolved["output_dir"] == str(root / "some/relative")
        assert resolved["show"] is False

    def test_leaves_absolute_paths_unchanged(self, tmp_path):
        params = {"output_dir": "/abs/path"}
        resolved = resolve_param_paths(params, root=tmp_path)
        assert resolved["output_dir"] == "/abs/path"
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/python -m pytest tests/test_utils.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'dashboard.utils'` or similar.

**Step 3: Write minimal implementation**

Create `dashboard/utils.py`:

```python
"""Utility helpers for the 4Dpapers dashboard."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import yaml

# Resolved at module load; tests can patch this.
CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict[str, Any]:
    """Load and return the dashboard config.yaml."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_PATH}")
    with CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


def load_manifest(manifest_path: Path) -> dict[str, Any] | None:
    """Read plots.json; return parsed dict or None if not found."""
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text())


def resolve_param_paths(params: dict[str, Any], *, root: Path) -> dict[str, Any]:
    """Resolve relative string param values to absolute paths under *root*."""
    resolved: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str) and not Path(value).is_absolute():
            resolved[key] = str(root / value)
        else:
            resolved[key] = value
    return resolved


def load_script_module(module_path: Path, module_name: str = "postproc_script"):
    """Dynamically import a Python file and return the module object."""
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_postprocessing_script(
    *,
    module_path: Path,
    function_name: str,
    params: dict[str, Any],
    log_lines: list[str],
) -> Any:
    """
    Import *module_path*, call *function_name*(**params).
    Stdout/stderr are captured into *log_lines* in real-time via a subprocess
    so that the Panel log pane can update incrementally.

    Returns the function's return value (artifact list / dict / None).
    """
    import subprocess
    import threading

    cmd = [
        sys.executable, "-c",
        f"import importlib.util, sys, json\n"
        f"spec = importlib.util.spec_from_file_location('m', {str(module_path)!r})\n"
        f"mod = importlib.util.module_from_spec(spec)\n"
        f"spec.loader.exec_module(mod)\n"
        f"result = mod.{function_name}(**{params!r})\n"
        f"print('__RESULT__:' + json.dumps(result, default=str))\n",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    result_payload = None

    def _read():
        nonlocal result_payload
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("__RESULT__:"):
                result_payload = json.loads(line[len("__RESULT__:"):])
            else:
                log_lines.append(line)

    thread = threading.Thread(target=_read, daemon=True)
    thread.start()
    proc.wait()
    thread.join()

    if proc.returncode != 0:
        log_lines.append(f"[ERROR] Script exited with code {proc.returncode}")

    return result_payload


def run_quarto_render(qmd_path: Path, log_lines: list[str]) -> int:
    """
    Run `quarto render <qmd_path>`.  Streams output to *log_lines*.
    Returns the process exit code.
    """
    import subprocess
    import threading

    proc = subprocess.Popen(
        ["quarto", "render", str(qmd_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(qmd_path.parent),
    )

    def _read():
        for line in proc.stdout:
            log_lines.append(line.rstrip("\n"))

    thread = threading.Thread(target=_read, daemon=True)
    thread.start()
    proc.wait()
    thread.join()
    return proc.returncode
```

**Step 4: Run tests to verify they pass**

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/python -m pytest tests/test_utils.py -v
```

Expected: All 5 tests PASS.

**Step 5: Commit**

```bash
git add dashboard/utils.py tests/test_utils.py
git commit -m "feat: add dashboard utils (config loader, manifest reader, script runner)"
```

---

## Task 4: Write `dashboard/pages/run_page.py`

**Files:**
- Create: `dashboard/pages/run_page.py`
- Create: `tests/test_pages.py` (smoke tests only — Panel widgets are hard to unit test)

**Step 1: Write a minimal smoke test**

Create `tests/test_pages.py`:

```python
"""Smoke tests for dashboard pages — verify they build without crashing."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


FAKE_CONFIG = {
    "cardiacfoam_root": "/fake/cf",
    "quarto_paper_path": "/fake/paper.qmd",
    "tutorials": {
        "NiedererEtAl2012": {
            "display_name": "Niederer Et Al. 2012",
            "scripts": [
                {
                    "name": "Line Post-Processing",
                    "module_relpath": "some/script.py",
                    "function": "run_postprocessing",
                    "params": {"output_dir": "out", "show": False},
                }
            ],
            "plots_manifest": "out/plots.json",
        }
    },
}


def test_run_page_builds():
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        from dashboard.pages.run_page import build_run_page
        page = build_run_page(tutorial_key="NiedererEtAl2012", config=FAKE_CONFIG)
    assert page is not None


def test_outputs_page_builds():
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        from dashboard.pages.outputs_page import build_outputs_page
        page = build_outputs_page(manifest=None)
    assert page is not None


def test_paper_page_builds():
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        from dashboard.pages.paper_page import build_paper_page
        page = build_paper_page(config=FAKE_CONFIG)
    assert page is not None
```

**Step 2: Run to verify fails**

```bash
.venv/bin/python -m pytest tests/test_pages.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'dashboard.pages.run_page'`

**Step 3: Create `dashboard/pages/run_page.py`**

```python
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
```

**Step 4: Run smoke test**

```bash
.venv/bin/python -m pytest tests/test_pages.py::test_run_page_builds -v
```

Expected: PASS

---

## Task 5: Write `dashboard/pages/outputs_page.py`

**Files:**
- Create: `dashboard/pages/outputs_page.py`

**Step 1: Create the file**

```python
"""Outputs tab: grid of artifacts from plots.json."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import panel as pn


def build_outputs_page(
    manifest: dict[str, Any] | None,
    *,
    output_dir: Path | None = None,
) -> pn.Column:
    if manifest is None:
        return pn.Column(
            pn.pane.Alert(
                "No outputs yet. Run post-processing from the **Run** tab first.",
                alert_type="info",
            )
        )

    artifacts = manifest.get("artifacts", [])
    generated_at = manifest.get("generated_at_utc", "unknown")
    base_dir = Path(manifest.get("output_dir", "."))

    cards = []
    for artifact in artifacts:
        label = artifact.get("label", artifact.get("path", "output"))
        fmt = artifact.get("format", "").lower()
        rel_path = artifact.get("path", "")
        abs_path = base_dir / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)

        if fmt == "html" and abs_path.exists():
            pane = pn.pane.HTML(
                f'<iframe src="file://{abs_path}" width="100%" height="450px" '
                f'style="border:none;border-radius:4px;"></iframe>',
                sizing_mode="stretch_width",
            )
        elif fmt in ("png", "jpg", "jpeg", "svg") and abs_path.exists():
            pane = pn.pane.Image(str(abs_path), sizing_mode="stretch_width")
        elif fmt == "csv" and abs_path.exists():
            import pandas as pd
            df = pd.read_csv(abs_path)
            pane = pn.widgets.Tabulator(df, pagination="local", page_size=10,
                                        sizing_mode="stretch_width")
        else:
            pane = pn.pane.Alert(
                f"File not found or unsupported format: `{abs_path}`",
                alert_type="warning",
            )

        cards.append(
            pn.Card(
                pane,
                title=label,
                collapsible=True,
                sizing_mode="stretch_width",
            )
        )

    return pn.Column(
        pn.pane.Markdown(f"**Generated:** {generated_at}  |  **{len(artifacts)} artifact(s)**"),
        pn.layout.Divider(),
        *cards,
        sizing_mode="stretch_width",
    )
```

**Step 2: Run smoke test**

```bash
.venv/bin/python -m pytest tests/test_pages.py::test_outputs_page_builds -v
```

Expected: PASS

---

## Task 6: Write `dashboard/pages/paper_page.py`

**Files:**
- Create: `dashboard/pages/paper_page.py`

**Step 1: Create the file**

```python
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
```

**Step 2: Run smoke tests**

```bash
.venv/bin/python -m pytest tests/test_pages.py -v
```

Expected: All 3 tests PASS.

**Step 3: Commit**

```bash
git add dashboard/pages/ tests/test_pages.py
git commit -m "feat: add run/outputs/paper dashboard pages"
```

---

## Task 7: Write `dashboard/app.py` (main entry point)

**Files:**
- Create: `dashboard/app.py`

**Step 1: Create the file**

```python
"""
4Dpaper Dashboard — main Panel app.

Launch with:
    panel serve dashboard/app.py --show --port 5006
from the 4Dpapers repository root.
"""
from __future__ import annotations

from pathlib import Path

import panel as pn

from dashboard.utils import load_config, load_manifest, resolve_param_paths
from dashboard.pages.run_page import build_run_page
from dashboard.pages.outputs_page import build_outputs_page
from dashboard.pages.paper_page import build_paper_page

pn.extension("codeeditor", sizing_mode="stretch_width", template="bootstrap")


def create_app():
    config = load_config()
    tutorials = config.get("tutorials", {})
    tutorial_keys = list(tutorials.keys())

    # ── Sidebar ──────────────────────────────────────────────────────────────
    tutorial_selector = pn.widgets.Select(
        name="Tutorial",
        options={v["display_name"]: k for k, v in tutorials.items()},
        sizing_mode="stretch_width",
    )
    last_run_status = pn.pane.Markdown("*No run yet.*")

    sidebar = pn.Column(
        pn.pane.Markdown("## 4Dpaper\n---"),
        pn.pane.Markdown("**Tutorial**"),
        tutorial_selector,
        pn.layout.Divider(),
        pn.pane.Markdown("**Last run**"),
        last_run_status,
        width=260,
    )

    # ── Pages (built lazily when tutorial changes) ────────────────────────────
    current_tutorial_key = tutorial_keys[0] if tutorial_keys else None

    run_col = pn.Column(sizing_mode="stretch_width")
    outputs_col = pn.Column(sizing_mode="stretch_width")
    paper_col = pn.Column(sizing_mode="stretch_width")

    def _load_tutorial(key: str):
        run_col.clear()
        run_col.append(build_run_page(key, config))

        tut_cfg = config["tutorials"][key]
        manifest_rel = tut_cfg.get("plots_manifest", "")
        cf_root = Path(config["cardiacfoam_root"])
        manifest_path = cf_root / manifest_rel
        manifest = load_manifest(manifest_path)

        outputs_col.clear()
        outputs_col.append(build_outputs_page(manifest))

        paper_col.clear()
        paper_col.append(build_paper_page(config))

    if current_tutorial_key:
        _load_tutorial(current_tutorial_key)

    def _on_tutorial_change(event):
        _load_tutorial(event.new)

    tutorial_selector.param.watch(_on_tutorial_change, "value")

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tabs = pn.Tabs(
        ("▶ Run", run_col),
        ("📊 Outputs", outputs_col),
        ("📄 Paper", paper_col),
        dynamic=True,
        sizing_mode="stretch_width",
    )

    # ── Root layout ───────────────────────────────────────────────────────────
    app = pn.Row(
        sidebar,
        pn.layout.VSpacer(width=16),
        tabs,
        sizing_mode="stretch_width",
    )
    return app


app = create_app()
app.servable()
```

**Step 2: Verify the app starts without errors (quick sanity)**

```bash
cd /Users/simaocastro/4Dpapers
timeout 5 .venv/bin/python -c "from dashboard.app import create_app; print('OK')" 2>&1
```

Expected: `OK` (or minor import warnings, but no exceptions).

**Step 3: Commit**

```bash
git add dashboard/app.py
git commit -m "feat: add Panel app entry point (dashboard/app.py)"
```

---

## Task 8: Update `analysis_report.qmd` to embed manifest artifacts

**Files:**
- Modify: `analysis_report.qmd` (add `reports_dir` param + new section)

**Step 1: Read the current params block (top of file, lines ~1-30)**

Check the current `params:` block in `analysis_report.qmd`. It should look like:
```yaml
params:
  case_path: "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/case.foam"
```

**Step 2: Add `reports_dir` to the params block**

In the YAML front matter, add:
```yaml
params:
  case_path: "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/case.foam"
  reports_dir: "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/postProcessing"
```

**Step 3: Add a new section at the end of the document (before Appendix A)**

Insert this new Quarto section before the `## Appendix A` heading:

````markdown
## Generated Post-Processing Results {#sec-postprocessing}

```{python}
#| label: load-postproc-results
#| output: asis
import json
from pathlib import Path
from IPython.display import display, Markdown, Image

reports_dir = Path(params.get("reports_dir", ""))
manifest_path = reports_dir / "plots.json"

if not manifest_path.exists():
    display(Markdown(
        "> **No post-processing outputs found.**  \n"
        "> Run the dashboard (`panel serve dashboard/app.py`) and click **Run Post-Processing**."
    ))
else:
    manifest = json.loads(manifest_path.read_text())
    artifacts = manifest.get("artifacts", [])
    generated_at = manifest.get("generated_at_utc", "unknown")
    display(Markdown(f"*{len(artifacts)} artifact(s) generated at {generated_at}*"))

    for artifact in artifacts:
        label = artifact.get("label", artifact.get("path", "Output"))
        fmt = artifact.get("format", "").lower()
        rel_path = artifact.get("path", "")
        abs_path = reports_dir / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)

        display(Markdown(f"### {label}"))

        if fmt == "html" and abs_path.exists():
            html_content = abs_path.read_text()
            display(Markdown(
                f'<details><summary>Show interactive plot</summary>\n\n'
                f'<iframe srcdoc="{html_content[:500]}..." '  # embed via file reference
                f'width="100%" height="500px" style="border:none;"></iframe>\n\n</details>'
            ))
            # For Quarto, embed by reference:
            display(Markdown(f"[Open {label}]({abs_path})"))
        elif fmt in ("png", "jpg", "jpeg") and abs_path.exists():
            display(Image(str(abs_path)))
        else:
            display(Markdown(f"*File: `{abs_path}`*"))
```
````

> **Note on HTML embeds:** Plotly HTML files can be very large. For the paper, the recommended approach is to embed a PNG screenshot or reference the HTML via a relative link. Adjust based on the actual artifact sizes.

**Step 4: Test render (dry run)**

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/quarto render analysis_report.qmd --no-execute 2>&1 | tail -10
```

Expected: `Output created: _output/analysis_report.html` (execution skipped with `--no-execute`).

**Step 5: Commit**

```bash
git add analysis_report.qmd
git commit -m "feat: add reports_dir param and post-processing results section to paper"
```

---

## Task 9: End-to-end verification

**Step 1: Start the dashboard**

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/panel serve dashboard/app.py --show --port 5006
```

Browser opens at `http://localhost:5006`.

**Step 2: Run post-processing**

1. Tutorial selector should show "Niederer Et Al. 2012"
2. Click **▶ Run Post-Processing** for "Line Post-Processing"
3. Watch log — should see `[INFO]` lines from the script
4. On success: check that `plots.json` exists:
   ```bash
   ls /Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/postProcessing/plots.json
   ```

**Step 3: View outputs**

Switch to the **📊 Outputs** tab — reload it by clicking back to Run and back (or add a refresh button in a later iteration). Verify artifact cards appear.

**Step 4: Rebuild the paper**

Switch to **📄 Paper** tab → click **⚙ Rebuild Paper** → wait for log to show `Output created: _output/analysis_report.html` → click the link → verify the "Generated Post-Processing Results" section shows the artifacts.

**Step 5: Code editor round-trip**

Back in **▶ Run** tab → click **▸ Advanced: Show code editor** → modify a comment in the script → click **▶ Run Post-Processing** → verify the modified file was saved and used (check timestamp on the output file).

---

## Summary of Commits

After all tasks, `git log --oneline` should show:

```
chore: add dashboard skeleton and pyyaml dependency
feat: add dashboard config.yaml
feat: add dashboard utils (config loader, manifest reader, script runner)
feat: add run/outputs/paper dashboard pages
feat: add Panel app entry point (dashboard/app.py)
feat: add reports_dir param and post-processing results section to paper
```
