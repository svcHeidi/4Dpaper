# Phase 2 — Camera Sync + ParaView Headless Render

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the loop between the interactive PyVista/Trame viewer in the Quarto paper and high-resolution static images for PDF export. The user sets the 3D view in the browser, saves camera state with one click, then the dashboard's "Rebuild Paper" button calls pvpython headlessly to generate a 4K PNG using the existing ParaView state file — which Quarto then embeds in the paper.

**Architecture:** Five additions to the already-working dashboard:
1. `state/` directory for camera JSON + render PNG (gitignored, machine-local)
2. `dashboard/paraview_render.py` — pvpython-only injector script
3. `dashboard/utils.py` extensions — camera helpers + pvpython runner
4. `dashboard/pages/paper_page.py` update — auto-runs pvpython before quarto
5. `analysis_report.qmd` update — "Save Camera" button + PNG-first display logic

**Tech Stack:** ParaView pvpython (`paraview.simple`), Panel widgets, PyVista camera API, Python subprocess + threading, JSON, pathlib.

---

## Project State at Start of This Plan

Phase 1 (the dashboard) is **already complete**. Do NOT re-implement it. These files already exist and work:

```
/Users/simaocastro/4Dpapers/
├── dashboard/
│   ├── __init__.py
│   ├── app.py                 ← Panel entry point (Run/Outputs/Paper tabs)
│   ├── config.yaml            ← paths + tutorial config (needs paraview block added)
│   ├── utils.py               ← config loader, manifest reader, script runner
│   └── pages/
│       ├── __init__.py
│       ├── run_page.py        ← Script runner UI with code editor
│       ├── outputs_page.py    ← Artifact grid from plots.json
│       └── paper_page.py      ← Quarto rebuild UI (needs pvpython step added)
├── scripts/
│   ├── data_loader.py         ← OpenFOAM case reader (SimulationData class)
│   └── interactive_viz.py     ← PyVista/Trame plotter creator
├── tests/
│   ├── __init__.py
│   └── test_utils.py          ← existing utils tests (add to, don't replace)
├── analysis_report.qmd        ← Quarto paper (needs camera button + PNG check added)
├── requirements.txt
└── _quarto.yml
```

**Key reference files (read-only, in the other repo):**
- PVSM: `/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/example_state.pvsm`
  - OpenFOAMReader proxy: `id="10305"`, FileName property points to `Niederer.foam`
  - RenderView proxy: `id="7148"`, has `CameraPosition`, `CameraFocalPoint`, `CameraViewUp`
  - Pipeline: OpenFOAMReader → Clip filter on Vm field
- Foam case: `/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam`
- pvpython: `/Applications/ParaView-5.13.3.app/Contents/bin/pvpython`

---

## What Gets Added

```
/Users/simaocastro/4Dpapers/
├── state/
│   ├── .gitkeep               ← NEW: keeps the dir in git; actual files are gitignored
│   ├── camera_state.json      ← NEW: written by "Save Camera" button (gitignored)
│   └── render_output.png      ← NEW: written by pvpython render (gitignored)
├── dashboard/
│   ├── config.yaml            ← MODIFY: append paraview + state_dir blocks
│   ├── utils.py               ← MODIFY: append 3 functions
│   └── paraview_render.py     ← NEW: pvpython injector script
│   └── pages/
│       └── paper_page.py      ← MODIFY: pvpython step before quarto
├── tests/
│   └── test_utils.py          ← MODIFY: append camera state tests
├── analysis_report.qmd        ← MODIFY: camera button + PNG-first section
└── .gitignore                 ← MODIFY: add state/ entries
```

---

## Task 1 — State directory + gitignore + config additions

**Files:**
- Create: `state/.gitkeep`
- Modify: `.gitignore`
- Modify: `dashboard/config.yaml`

### Step 1.1 — Create state directory

```bash
cd /Users/simaocastro/4Dpapers
mkdir -p state
touch state/.gitkeep
```

### Step 1.2 — Update .gitignore

Check if `.gitignore` exists:
```bash
cat /Users/simaocastro/4Dpapers/.gitignore 2>/dev/null || echo "(no gitignore yet)"
```

Append these lines (create the file if it doesn't exist):
```
# Machine-local visualization state
state/camera_state.json
state/render_output.png
```

### Step 1.3 — Append paraview block to `dashboard/config.yaml`

Read the current file first, then append. The current file ends after the `tutorials:` block. Add these lines at the bottom:

```yaml
# ── ParaView headless render ────────────────────────────────────────────────
paraview:
  pvsm_path: "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/example_state.pvsm"
  foam_path: "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam"
  pvpython_path: "/Applications/ParaView-5.13.3.app/Contents/bin/pvpython"
  render_resolution: [3840, 2160]

# ── Shared state paths ───────────────────────────────────────────────────────
state_dir: "/Users/simaocastro/4Dpapers/state"
render_output: "/Users/simaocastro/4Dpapers/state/render_output.png"
camera_state: "/Users/simaocastro/4Dpapers/state/camera_state.json"
```

### Step 1.4 — Verify config loads correctly

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/python -c "
from dashboard.utils import load_config
cfg = load_config()
assert 'paraview' in cfg, 'paraview block missing'
assert 'state_dir' in cfg, 'state_dir missing'
assert 'camera_state' in cfg, 'camera_state missing'
print('Config OK:', list(cfg.keys()))
"
```

Expected output: `Config OK: ['cardiacfoam_root', 'quarto_paper_path', 'tutorials', 'paraview', 'state_dir', 'render_output', 'camera_state']`

### Step 1.5 — Commit

```bash
git add state/.gitkeep .gitignore dashboard/config.yaml
git commit -m "chore: add state dir, gitignore entries, and paraview config block"
```

---

## Task 2 — Write `dashboard/paraview_render.py`

**Files:**
- Create: `dashboard/paraview_render.py`

> **CRITICAL:** This script uses `paraview.simple` which is ONLY available inside ParaView's bundled pvpython. It will fail with `ModuleNotFoundError` if run with the `.venv` Python. This is expected and correct — the dashboard calls it via subprocess using the pvpython binary.

### Step 2.1 — Create the file

Create `/Users/simaocastro/4Dpapers/dashboard/paraview_render.py` with this exact content:

```python
"""
ParaView headless rendering injector.

MUST be run with pvpython (ParaView's bundled Python), NOT the project venv.

Usage:
    /Applications/ParaView-5.13.3.app/Contents/bin/pvpython \\
        dashboard/paraview_render.py \\
        <pvsm_path> <foam_path> <camera_json_path> <output_png> [width] [height]

Example:
    pvpython dashboard/paraview_render.py \\
        /path/to/example_state.pvsm \\
        /path/to/Niederer.foam \\
        state/camera_state.json \\
        state/render_output.png \\
        3840 2160
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def inject_and_render(
    pvsm_path: str,
    foam_path: str,
    camera_state_path: str,
    output_path: str,
    resolution: tuple[int, int] = (3840, 2160),
) -> None:
    """
    Load a ParaView state file, inject the target foam path and camera,
    then render a high-resolution screenshot.

    Parameters
    ----------
    pvsm_path:
        Absolute path to the master .pvsm state file.
    foam_path:
        Absolute path to the .foam marker file for the target case.
    camera_state_path:
        Path to camera_state.json (written by the "Save Camera" button).
    output_path:
        Where to write the output PNG.
    resolution:
        (width, height) in pixels. Default is 4K (3840×2160).
    """
    # Deferred import: only works inside pvpython
    from paraview.simple import (
        FindSource,
        GetActiveViewOrCreate,
        LoadState,
        SaveScreenshot,
    )

    # 1. Load the master pipeline state
    print(f"[paraview_render] Loading state: {pvsm_path}")
    LoadState(
        pvsm_path,
        LoadStateDataFileOptions="Use File Names From State",
    )

    # 2. Redirect the OpenFOAMReader to the target case
    reader = FindSource("OpenFOAMReader")
    if reader is None:
        raise RuntimeError(
            "OpenFOAMReader proxy not found in the loaded PVSM state. "
            "Ensure the master PVSM was saved with an OpenFOAM reader active."
        )
    reader.FileName = str(foam_path)
    reader.UpdatePipeline()
    print(f"[paraview_render] Data path set to: {foam_path}")

    # 3. Apply camera state from JSON
    with open(camera_state_path) as fh:
        cam = json.load(fh)

    view = GetActiveViewOrCreate("RenderView")
    view.CameraPosition   = cam["position"]
    view.CameraFocalPoint = cam["focal_point"]
    view.CameraViewUp     = cam["view_up"]
    if "parallel_scale" in cam:
        view.CameraParallelScale = cam["parallel_scale"]
    print(f"[paraview_render] Camera applied from: {camera_state_path}")

    # 4. Headless render at target resolution
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    SaveScreenshot(
        output_path,
        ImageResolution=list(resolution),
        OverrideColorPalette="PrintBackground",
    )
    print(
        f"[paraview_render] Rendered {resolution[0]}x{resolution[1]} px"
        f" → {output_path}"
    )


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(
            "Usage: pvpython paraview_render.py "
            "<pvsm> <foam> <camera_json> <output_png> [W] [H]"
        )
        sys.exit(1)

    _res = (
        (int(sys.argv[5]), int(sys.argv[6]))
        if len(sys.argv) > 6
        else (3840, 2160)
    )
    inject_and_render(
        pvsm_path=sys.argv[1],
        foam_path=sys.argv[2],
        camera_state_path=sys.argv[3],
        output_path=sys.argv[4],
        resolution=_res,
    )
```

### Step 2.2 — Verify it is importable by the venv Python (without crashing)

The file defers the `paraview.simple` import, so it should import cleanly:

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/python -c "import dashboard.paraview_render; print('import OK')"
```

Expected: `import OK`

If it raises `ModuleNotFoundError: No module named 'paraview'` — that means the import guard is broken. The `from paraview.simple import ...` must be INSIDE the `inject_and_render` function, not at module level.

### Step 2.3 — Commit

```bash
git add dashboard/paraview_render.py
git commit -m "feat: add pvpython headless render injector (paraview_render.py)"
```

---

## Task 3 — Extend `dashboard/utils.py` with camera helpers

**Files:**
- Modify: `dashboard/utils.py`
- Modify: `tests/test_utils.py`

### Step 3.1 — Write failing tests first

Open `tests/test_utils.py` and append these tests at the end (after all existing tests):

```python
# ── New tests for Task 3 ──────────────────────────────────────────────────────

class TestSaveCameraState:
    def test_writes_json_with_correct_keys(self, tmp_path):
        from dashboard.utils import save_camera_state
        path = tmp_path / "cam.json"
        save_camera_state(
            position=[1.0, 2.0, 3.0],
            focal_point=[0.01, 0.0015, 0.0035],
            view_up=[0.19, 0.91, -0.37],
            parallel_scale=None,
            output_path=path,
        )
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["position"] == [1.0, 2.0, 3.0]
        assert data["focal_point"] == [0.01, 0.0015, 0.0035]
        assert data["view_up"] == [0.19, 0.91, -0.37]
        assert "parallel_scale" not in data

    def test_includes_parallel_scale_when_provided(self, tmp_path):
        from dashboard.utils import save_camera_state
        path = tmp_path / "cam.json"
        save_camera_state(
            position=[0.0, 0.0, 1.0],
            focal_point=[0.0, 0.0, 0.0],
            view_up=[0.0, 1.0, 0.0],
            parallel_scale=0.05,
            output_path=path,
        )
        data = json.loads(path.read_text())
        assert data["parallel_scale"] == pytest.approx(0.05)

    def test_creates_parent_directory(self, tmp_path):
        from dashboard.utils import save_camera_state
        nested = tmp_path / "deep" / "nested" / "cam.json"
        save_camera_state(
            position=[0.0, 0.0, 1.0],
            focal_point=[0.0, 0.0, 0.0],
            view_up=[0.0, 1.0, 0.0],
            parallel_scale=None,
            output_path=nested,
        )
        assert nested.exists()


class TestLoadCameraState:
    def test_returns_dict_for_existing_file(self, tmp_path):
        from dashboard.utils import load_camera_state
        path = tmp_path / "cam.json"
        path.write_text(
            json.dumps({"position": [1, 2, 3], "focal_point": [0, 0, 0], "view_up": [0, 1, 0]})
        )
        result = load_camera_state(path)
        assert result is not None
        assert result["position"] == [1, 2, 3]

    def test_returns_none_when_missing(self, tmp_path):
        from dashboard.utils import load_camera_state
        result = load_camera_state(tmp_path / "no_such_file.json")
        assert result is None
```

### Step 3.2 — Run tests to verify they fail

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/python -m pytest tests/test_utils.py::TestSaveCameraState \
                           tests/test_utils.py::TestLoadCameraState -v 2>&1 | tail -20
```

Expected: `ImportError` or `AttributeError: module 'dashboard.utils' has no attribute 'save_camera_state'`

### Step 3.3 — Add the three functions to `dashboard/utils.py`

Open `dashboard/utils.py` and append at the very end of the file:

```python
# ── Camera state helpers ──────────────────────────────────────────────────────

def save_camera_state(
    position: list[float],
    focal_point: list[float],
    view_up: list[float],
    parallel_scale: float | None,
    *,
    output_path: "Path",
) -> None:
    """Serialize PyVista camera state to JSON for use by paraview_render.py."""
    payload: dict = {
        "position":    list(position),
        "focal_point": list(focal_point),
        "view_up":     list(view_up),
    }
    if parallel_scale is not None:
        payload["parallel_scale"] = float(parallel_scale)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))


def load_camera_state(path: "Path") -> "dict | None":
    """Return camera dict from JSON, or None if file does not exist."""
    if not path.exists():
        return None
    return json.loads(path.read_text())


def run_pvpython_render(
    *,
    pvpython_path: str,
    pvsm_path: str,
    foam_path: str,
    camera_state_path: "Path",
    output_path: "Path",
    resolution: list[int],
    log_lines: list[str],
) -> int:
    """
    Invoke pvpython to run dashboard/paraview_render.py as a subprocess.
    Streams stdout+stderr to log_lines line by line.
    Returns the process exit code (0 = success).
    """
    import subprocess
    import threading

    render_script = Path(__file__).parent / "paraview_render.py"
    cmd = [
        pvpython_path,
        str(render_script),
        str(pvsm_path),
        str(foam_path),
        str(camera_state_path),
        str(output_path),
        str(resolution[0]),
        str(resolution[1]),
    ]
    log_lines.append(f"[INFO] Running: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    def _read_output() -> None:
        for line in proc.stdout:
            log_lines.append(line.rstrip("\n"))

    thread = threading.Thread(target=_read_output, daemon=True)
    thread.start()
    proc.wait()
    thread.join()

    if proc.returncode != 0:
        log_lines.append(
            f"[ERROR] pvpython exited with code {proc.returncode}"
        )
    return proc.returncode
```

### Step 3.4 — Run tests to verify they pass

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/python -m pytest tests/test_utils.py -v
```

Expected: **All tests PASS** (existing + new ones).

### Step 3.5 — Commit

```bash
git add dashboard/utils.py tests/test_utils.py
git commit -m "feat: add save/load_camera_state and run_pvpython_render to utils"
```

---

## Task 4 — Update `dashboard/pages/paper_page.py`

**Files:**
- Modify: `dashboard/pages/paper_page.py`

The existing `paper_page.py` has a `_on_rebuild_click` method that calls `run_quarto_render` directly. We need to:
1. Add `run_pvpython_render` to the imports
2. Replace `_on_rebuild_click` with a version that first runs pvpython if camera state exists

### Step 4.1 — Read the current file

```bash
cat /Users/simaocastro/4Dpapers/dashboard/pages/paper_page.py
```

Note the exact current import line for `run_quarto_render` and the existing `_on_rebuild_click` method body.

### Step 4.2 — Update the import line

Find the line:
```python
from dashboard.utils import run_quarto_render
```

Replace it with:
```python
from dashboard.utils import run_pvpython_render, run_quarto_render
```

### Step 4.3 — Replace `_on_rebuild_click` entirely

Find the entire `_on_rebuild_click` method and replace it with:

```python
def _on_rebuild_click(self, event) -> None:
    if self.is_building:
        return
    self.is_building = True
    self._rebuild_btn.disabled = True
    self._log_lines.clear()
    self._status_badge.object = "Checking for camera state…"
    self._status_badge.alert_type = "warning"
    self._open_link.object = ""

    cfg = self._config
    camera_path = Path(cfg.get("camera_state", ""))
    render_output = Path(cfg.get("render_output", ""))
    pv_cfg = cfg.get("paraview", {})

    def _run() -> None:
        # ── Step 1: headless render (only if camera state exists) ──────────
        if camera_path and camera_path.exists() and pv_cfg:
            self._log_lines.append(
                "[INFO] Camera state found — running pvpython headless render…"
            )
            pn.state.execute(self._refresh_log)

            exit_code = run_pvpython_render(
                pvpython_path=pv_cfg.get(
                    "pvpython_path", "pvpython"
                ),
                pvsm_path=pv_cfg.get("pvsm_path", ""),
                foam_path=pv_cfg.get("foam_path", ""),
                camera_state_path=camera_path,
                output_path=render_output,
                resolution=pv_cfg.get("render_resolution", [1920, 1080]),
                log_lines=self._log_lines,
            )
            if exit_code != 0:
                pn.state.execute(lambda: self._finish(exit_code))
                return
            self._log_lines.append(
                f"[INFO] Render complete → {render_output}"
            )
        else:
            self._log_lines.append(
                "[INFO] No camera state found — skipping pvpython render."
            )

        # ── Step 2: quarto render ────────────────────────────────────────
        self._log_lines.append("[INFO] Running quarto render…")
        pn.state.execute(self._refresh_log)
        exit_code = run_quarto_render(self._qmd_path, self._log_lines)
        pn.state.execute(lambda: self._finish(exit_code))

    threading.Thread(target=_run, daemon=True).start()
    pn.state.add_periodic_callback(self._refresh_log, period=500, count=120)
```

Make sure `Path` is imported. The file already imports `from pathlib import Path` — if not, add it.

### Step 4.4 — Quick sanity check

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/python -c "
from unittest.mock import patch
FAKE_CFG = {
    'cardiacfoam_root': '/fake',
    'quarto_paper_path': '/fake/paper.qmd',
    'tutorials': {},
    'camera_state': '',
    'render_output': '',
    'paraview': {},
}
with patch('dashboard.utils.load_config', return_value=FAKE_CFG):
    from dashboard.pages.paper_page import build_paper_page
    page = build_paper_page(config=FAKE_CFG)
print('paper_page import OK')
"
```

Expected: `paper_page import OK`

### Step 4.5 — Commit

```bash
git add dashboard/pages/paper_page.py
git commit -m "feat: paper rebuild auto-runs pvpython if camera_state.json exists"
```

---

## Task 5 — Update `analysis_report.qmd`

**Files:**
- Modify: `analysis_report.qmd`

Two surgical additions to the existing QMD. Read the file carefully before editing.

### Step 5.1 — Read the current file structure

```bash
grep -n "^##\|^```{python}\|label:" /Users/simaocastro/4Dpapers/analysis_report.qmd | head -40
```

This will show section headings and code cell labels. Find:
- The line with `#| label: generate-tabs-vol` (or similar — the main 3D viewer cell)
- Any section heading for "Interactive 3D Visualization"

### Step 5.2 — Add Change 1: PNG-first check cell

Locate the Python cell that creates the interactive visualizations (the one with `display_fields` loop and `pl_int`). Insert a NEW code cell IMMEDIATELY BEFORE that cell:

````markdown
```{python}
#| label: check-render-output
#| output: asis
#| echo: false
from pathlib import Path
from IPython.display import display, Markdown, Image as IPImage
import time

_render_output = Path(__file__).parent / "state" / "render_output.png"

if _render_output.exists():
    _mtime = time.strftime(
        "%Y-%m-%d %H:%M", time.localtime(_render_output.stat().st_mtime)
    )
    display(Markdown(
        f"> **High-res ParaView render available** — generated {_mtime}  \n"
        f"> *To regenerate: adjust view in browser → Save Camera → Rebuild Paper.*"
    ))
    display(IPImage(str(_render_output), width=900))
    display(Markdown(
        "---\n"
        "*The interactive viewer below is active in `quarto preview` mode.*"
    ))
```
````

**Why before, not after:** The render check runs first. If a PNG exists, it displays it prominently at the top of the section. The interactive cells still execute below it — they're visible in `quarto preview` / live mode.

### Step 5.3 — Add Change 2: Camera-save button cell

Locate the END of the interactive viewer cell (the one containing `pl_int.show(...)` or the closing `print("\n:::\n")`). Insert a NEW code cell IMMEDIATELY AFTER it:

````markdown
```{python}
#| label: camera-capture-btn
#| output: asis
#| echo: false
"""
Camera-save button — only functional in `quarto preview` / live kernel mode.
In frozen Quarto renders this renders as a static (non-functional) button.
"""
import json
import panel as pn
from pathlib import Path

_STATE_DIR = Path(__file__).parent / "state"

# pl_int is the last PyVista plotter created in the loop above.
# In quarto preview (live kernel), its .camera properties reflect the
# user's current browser view via PyVista's Trame sync.
try:
    _plotter = pl_int  # noqa: F821  (defined in previous cell)
except NameError:
    _plotter = None


def _on_save_camera(event) -> None:
    if _plotter is None:
        _save_btn.name = "⚠ No plotter available"
        _save_btn.button_type = "warning"
        return

    cam_data: dict = {
        "position":    list(_plotter.camera.position),
        "focal_point": list(_plotter.camera.focal_point),
        "view_up":     list(_plotter.camera.view_up),
    }
    if _plotter.camera.is_parallel_projection:
        cam_data["parallel_scale"] = float(_plotter.camera.parallel_scale)

    _STATE_DIR.mkdir(exist_ok=True)
    out = _STATE_DIR / "camera_state.json"
    out.write_text(json.dumps(cam_data, indent=2))

    _save_btn.name = "✓ Camera saved → state/camera_state.json"
    _save_btn.button_type = "success"


_save_btn = pn.widgets.Button(
    name="📷  Save Camera State for High-Res Render",
    button_type="primary",
    width=380,
)
_save_btn.on_click(_on_save_camera)
display(_save_btn)
```
````

### Step 5.4 — Verify QMD parses without errors (no-execute dry run)

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/quarto check jupyter 2>&1 | tail -5
```

Then do a structure-only check:
```bash
.venv/bin/quarto render analysis_report.qmd --no-execute 2>&1 | tail -10
```

Expected: `Output created: _output/analysis_report.html` (execution skipped, structure valid).

If there are YAML parse errors, check that the code fences are correct (triple backticks with `{python}`, matching open/close).

### Step 5.5 — Commit

```bash
git add analysis_report.qmd
git commit -m "feat: add camera-save button and high-res render embed to Quarto paper"
```

---

## Task 6 — End-to-End Verification

This task verifies the full pipeline works. It has no code changes — it's a checklist run.

### Step 6.1 — Verify all existing tests still pass

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/python -m pytest tests/ -v
```

Expected: **All green**.

### Step 6.2 — Smoke-test dashboard startup

```bash
cd /Users/simaocastro/4Dpapers
timeout 8 .venv/bin/python -c "
from dashboard.app import create_app
app = create_app()
print('Dashboard startup: OK')
" 2>&1
```

Expected: `Dashboard startup: OK`

### Step 6.3 — Test camera save + load roundtrip via utils

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/python -c "
from pathlib import Path
from dashboard.utils import save_camera_state, load_camera_state

p = Path('/tmp/test_cam.json')
save_camera_state(
    position=[-0.01, 0.019, 0.035],
    focal_point=[0.01, 0.0015, 0.0035],
    view_up=[0.19, 0.91, -0.37],
    parallel_scale=None,
    output_path=p,
)
cam = load_camera_state(p)
assert cam['position'] == [-0.01, 0.019, 0.035]
print('Camera roundtrip: OK')
print('Saved:', p.read_text())
"
```

Expected: `Camera roundtrip: OK` followed by the JSON content.

### Step 6.4 — Verify pvpython binary exists

```bash
ls -la /Applications/ParaView-5.13.3.app/Contents/bin/pvpython
```

Expected: the file exists and is executable. If not, the pvpython path in `config.yaml` needs updating to match the installed ParaView version.

Find the installed version with:
```bash
find /Applications -name "pvpython" 2>/dev/null
```

Update `dashboard/config.yaml` `pvpython_path` if needed.

### Step 6.5 — Manual end-to-end (interactive)

**Terminal 1 — start the Quarto live preview:**
```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/quarto preview analysis_report.qmd --port 4567
```

**In the browser (localhost:4567):**
1. Navigate to the 3D Visualization section.
2. Find the PyVista viewer tab (e.g., "Vm" or "Activation Time").
3. Rotate/zoom the model to the desired camera angle.
4. Click **"📷 Save Camera State for High-Res Render"**.
5. Button should turn green: `✓ Camera saved → state/camera_state.json`.

**Terminal — verify JSON was written:**
```bash
cat /Users/simaocastro/4Dpapers/state/camera_state.json
```

Expected structure:
```json
{
  "position": [-0.009, 0.018, 0.035],
  "focal_point": [0.01, 0.0015, 0.0035],
  "view_up": [0.19, 0.91, -0.37]
}
```

**Terminal 2 — start the dashboard:**
```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/panel serve dashboard/app.py --show --port 5006
```

**In the dashboard (localhost:5006):**
1. Go to the **📄 Paper** tab.
2. Click **⚙ Rebuild Paper**.
3. Watch the log — it should show:
   ```
   [INFO] Camera state found — running pvpython headless render…
   [INFO] Running: /Applications/ParaView-5.13.3.app/.../pvpython ...
   [paraview_render] Loading state: ...example_state.pvsm
   [paraview_render] Data path set to: ...Niederer.foam
   [paraview_render] Camera applied from: ...camera_state.json
   [paraview_render] Rendered 3840x2160 px → .../state/render_output.png
   [INFO] Render complete → .../state/render_output.png
   [INFO] Running quarto render…
   Output created: _output/analysis_report.html
   ✓ Paper built successfully!
   ```
4. Click the "📄 Open analysis_report.html" link.
5. Verify the **high-res PNG** appears at the top of the 3D Visualization section.

**Terminal — verify the PNG was created:**
```bash
ls -lh /Users/simaocastro/4Dpapers/state/render_output.png
```

Expected: file exists, size > 1 MB for a 4K render.

### Step 6.6 — Test fallback (no camera state)

```bash
# Remove camera state to test fallback
rm /Users/simaocastro/4Dpapers/state/camera_state.json
```

Rebuild paper from the dashboard. Log should show:
```
[INFO] No camera state found — skipping pvpython render.
[INFO] Running quarto render…
```

Paper should show the Trame viewer (not the PNG).

### Step 6.7 — Final commit summary

```bash
cd /Users/simaocastro/4Dpapers
git log --oneline -8
```

Expected commits (most recent first):
```
feat: add camera-save button and high-res render embed to Quarto paper
feat: paper rebuild auto-runs pvpython if camera_state.json exists
feat: add save/load_camera_state and run_pvpython_render to utils
feat: add pvpython headless render injector (paraview_render.py)
chore: add state dir, gitignore entries, and paraview config block
```

---

## Summary Table

| Task | Files changed | Key outcome |
|------|--------------|-------------|
| 1 | `state/.gitkeep`, `.gitignore`, `dashboard/config.yaml` | State dir exists; paraview paths configured |
| 2 | `dashboard/paraview_render.py` | pvpython script loads PVSM, injects path + camera, renders PNG |
| 3 | `dashboard/utils.py`, `tests/test_utils.py` | save/load camera JSON + pvpython subprocess helper (tested) |
| 4 | `dashboard/pages/paper_page.py` | Rebuild Paper auto-runs pvpython before quarto if camera exists |
| 5 | `analysis_report.qmd` | PNG-first display + "Save Camera" button in live mode |
| 6 | — | End-to-end verified |

---

## Troubleshooting

**"OpenFOAMReader proxy not found"**
The `example_state.pvsm` may reference the reader under a different source name. Run in pvpython:
```python
from paraview.simple import LoadState, GetSources
LoadState("/path/to/example_state.pvsm", LoadStateDataFileOptions="Use File Names From State")
print(list(GetSources().keys()))
```
Use the actual source name in `paraview_render.py` instead of `"OpenFOAMReader"`.

**"Camera save button doesn't respond"**
The button only works in `quarto preview` (live kernel). In a frozen render (`quarto render`), it appears static. Check that `quarto preview` is running, not just the rendered HTML.

**"pvpython not found"**
Run `find /Applications -name "pvpython" 2>/dev/null` and update `pvpython_path` in `dashboard/config.yaml`.

**"render_output.png is blank or black"**
The foam data may not be loaded correctly. Check that `Niederer.foam` exists and the OpenFOAM case has been run. The `reader.UpdatePipeline()` call will fail silently if the case data is missing.
