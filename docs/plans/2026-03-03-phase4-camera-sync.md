# Phase 4 — Camera Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Sync the vtk.js camera from the browser to the server so that PDF figures use exactly the angle the user set in the HTML interactive viewer.

**Architecture:** vtk.js exposes `window.renderWindow` globally. On each rotation end, injected JS POSTs `{position, focal_point, view_up}` to a Tornado endpoint on the Panel server. Before PNG generation, PyVista checks for a saved camera JSON and applies it instead of the default isometric view.

**Tech Stack:** vtk.js (`window.renderWindow`, `onEndInteractionEvent`), Panel 1.8 `--plugins` + Tornado `RequestHandler`, PyVista camera API, JSON files in `state/`

---

## Pre-existing work (skip these — already done)

- `save_camera_state()` and `load_camera_state()` in `dashboard/utils.py` ✓
- Tests for both in `tests/test_utils.py` ✓
- Design doc at `docs/plans/2026-03-03-phase4-camera-sync-design.md` ✓

---

## vtk.js API notes (read before implementing Task 3)

The HTML produced by PyVista `export_html()` contains a minified vtk.js bundle that sets:

```javascript
window.renderWindow = renderWindowInstance  // via webpack globalThis
```

This is available synchronously as soon as `OfflineLocalView.load(container, { base64Str })` is called (the last line of the generated HTML). The scene loads asynchronously, but the user cannot rotate until it's done, so hooking `onEndInteractionEvent` on the interactor is safe.

Relevant vtk.js API (confirmed from bundle inspection):
- `window.renderWindow.getInteractor()` → interactor
- `interactor.onEndInteractionEvent(fn)` → registers end-of-drag callback
- `window.renderWindow.getRenderers().getFirst()` → first renderer
- `renderer.getActiveCamera()` → camera
- `camera.getPosition()` → `[x, y, z]`
- `camera.getFocalPoint()` → `[x, y, z]`
- `camera.getViewUp()` → `[x, y, z]`

The badge uses `position: fixed` so it floats over the vtk.js canvas inside the iframe.

---

## Task 1: Tornado camera endpoint via Panel plugin

**Files:**
- Create: `dashboard/camera_plugin.py`
- Create: `tests/test_camera_plugin.py`

**Why `--plugins`:** Panel's `panel serve --plugins <module>` loads the module and extends Tornado URL patterns with `module.ROUTES`. This adds routes directly to the running Panel/Bokeh Tornado server on port 5006 — no extra port, no threading, no private APIs.

**Updated launch command** (replace the existing one in README / wherever it's documented):

```bash
panel serve dashboard/app.py \
  --plugins dashboard.camera_plugin \
  --static-dirs output=_output \
  --show --port 5006
```

---

### Step 1: Write the failing test

```python
# tests/test_camera_plugin.py
"""Tests for the camera sync Tornado plugin."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_camera_plugin_imports():
    from dashboard.camera_plugin import CameraHandler, ROUTES
    assert CameraHandler is not None
    assert len(ROUTES) == 1
    assert "/camera/" in ROUTES[0][0]


def test_camera_handler_post_writes_json(tmp_path):
    """CameraHandler.post() writes camera state JSON to state/camera_<fig_id>.json."""
    from dashboard.camera_plugin import CameraHandler

    body = json.dumps({
        "position": [1.0, 2.0, 3.0],
        "focal_point": [0.0, 0.0, 0.0],
        "view_up": [0.0, 1.0, 0.0],
    }).encode()

    # Build a minimal fake Tornado request
    request = MagicMock()
    request.body = body

    handler = CameraHandler.__new__(CameraHandler)
    handler.request = request
    handler._finished = False
    handler._headers = {}
    handler._write_buffer = []

    state_dir = tmp_path / "state"
    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.post("fig-vm")

    cam_path = tmp_path / "state" / "camera_fig-vm.json"
    assert cam_path.exists(), "camera JSON not written"
    data = json.loads(cam_path.read_text())
    assert data["position"] == [1.0, 2.0, 3.0]
    assert data["focal_point"] == [0.0, 0.0, 0.0]
    assert data["view_up"] == [0.0, 1.0, 0.0]
```

### Step 2: Run test, verify it fails

```bash
.venv/bin/pytest tests/test_camera_plugin.py -v
```

Expected: `ImportError: No module named 'dashboard.camera_plugin'`

### Step 3: Create `dashboard/camera_plugin.py`

```python
"""
Panel plugin: per-figure camera state sync endpoint.

Add to panel serve with:
    panel serve dashboard/app.py --plugins dashboard.camera_plugin ...

Panel reads the ROUTES list and registers the handlers with Tornado.
The srcdoc iframe has a null origin, so CORS headers allow all origins.
"""
from __future__ import annotations

import json
from pathlib import Path

import tornado.web

from dashboard.utils import save_camera_state

_PROJECT_ROOT = Path(__file__).parent.parent


class CameraHandler(tornado.web.RequestHandler):
    def set_default_headers(self) -> None:
        # srcdoc iframes have a null origin — allow all for local-only server
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def options(self, fig_id: str) -> None:
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def post(self, fig_id: str) -> None:
        body = json.loads(self.request.body)
        cam_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}.json"
        save_camera_state(
            position=body["position"],
            focal_point=body["focal_point"],
            view_up=body["view_up"],
            parallel_scale=body.get("parallel_scale"),
            output_path=cam_path,
        )
        self.write({"status": "ok"})


ROUTES = [
    (r"/camera/(?P<fig_id>[^/]+)", CameraHandler),
]
```

### Step 4: Run test, verify it passes

```bash
.venv/bin/pytest tests/test_camera_plugin.py -v
```

Expected: 2 PASS

### Step 5: Commit

```bash
git add dashboard/camera_plugin.py tests/test_camera_plugin.py
git commit -m "feat: add Tornado camera sync endpoint via Panel plugin"
```

---

## Task 2: PNG generation respects saved camera state

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py`
- Modify: `tests/test_extension.py`

Three changes:
1. `is_cache_valid()` gains optional `camera_path` param — PNG is stale if camera JSON is newer
2. `generate_png_figure()` gains `fig_id` param — applies saved camera before screenshotting
3. `main()` passes `fig_id` and `camera_path` to both functions

---

### Step 1: Write failing tests

Add to `TestIsCacheValid` class in `tests/test_extension.py`:

```python
def test_stale_when_camera_newer_than_png(self, tmp_path):
    mod = _load_4dpaper()
    src = tmp_path / "case.foam"
    src.write_text("")
    fig = tmp_path / "fig.png"
    fig.write_text("")
    time.sleep(0.05)
    cam = tmp_path / "camera_fig.json"
    cam.write_text("{}")
    # camera newer than fig → cache NOT valid
    assert mod.is_cache_valid(fig, src, camera_path=cam) is False

def test_valid_when_png_newer_than_camera(self, tmp_path):
    mod = _load_4dpaper()
    src = tmp_path / "case.foam"
    src.write_text("")
    cam = tmp_path / "camera_fig.json"
    cam.write_text("{}")
    time.sleep(0.05)
    fig = tmp_path / "fig.png"
    fig.write_text("")
    # png newer than camera → cache IS valid
    assert mod.is_cache_valid(fig, src, camera_path=cam) is True

def test_valid_when_camera_file_absent(self, tmp_path):
    mod = _load_4dpaper()
    src = tmp_path / "case.foam"
    src.write_text("")
    time.sleep(0.05)
    fig = tmp_path / "fig.png"
    fig.write_text("")
    cam = tmp_path / "nonexistent_camera.json"
    # no camera file → behaves as before (compare fig vs src only)
    assert mod.is_cache_valid(fig, src, camera_path=cam) is True
```

### Step 2: Run tests, verify they fail

```bash
.venv/bin/pytest tests/test_extension.py::TestIsCacheValid -v
```

Expected: 3 new tests FAIL with `TypeError: is_cache_valid() got an unexpected keyword argument 'camera_path'`

### Step 3: Update `is_cache_valid` in `_extensions/4dpaper/4dpaper.py`

Replace the current `is_cache_valid` function (lines 66–75) with:

```python
def is_cache_valid(
    fig_path: Path,
    src_path: Path,
    camera_path: Path | None = None,
) -> bool:
    """
    Return True if fig_path exists, is newer than src_path, and is newer
    than camera_path (if given and present).

    Returns True (assume valid) if src_path does not exist.
    """
    if not fig_path.exists():
        return False
    fig_mtime = fig_path.stat().st_mtime
    if src_path.exists() and fig_mtime <= src_path.stat().st_mtime:
        return False
    if camera_path is not None and camera_path.exists():
        if fig_mtime <= camera_path.stat().st_mtime:
            return False
    return True
```

### Step 4: Run tests, verify they pass

```bash
.venv/bin/pytest tests/test_extension.py::TestIsCacheValid -v
```

Expected: all TestIsCacheValid tests PASS (including the 3 new ones)

### Step 5: Update `generate_png_figure` signature and camera loading

Replace the `generate_png_figure` function signature and the `pl.isometric_view()` call in `_extensions/4dpaper/4dpaper.py`:

**New signature** (add `fig_id` param):

```python
def generate_png_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
) -> None:
```

**Replace the `pl.isometric_view()` line** (currently line 136) with:

```python
    # Apply saved camera if available, else fall back to isometric view
    camera_path = (
        _project_root / "state" / f"camera_{fig_id}.json"
        if fig_id else None
    )
    if camera_path is not None and camera_path.exists():
        import json as _json
        cam = _json.loads(camera_path.read_text())
        pl.camera.position = cam["position"]
        pl.camera.focal_point = cam["focal_point"]
        pl.camera.view_up = cam["view_up"]
        print(f"[4dpaper] Applied saved camera for {fig_id}", file=sys.stderr)
    else:
        pl.isometric_view()
```

### Step 6: Update `main()` to pass `fig_id` and `camera_path`

In `main()`, replace the PNG section (currently lines 270–279):

```python
        out_png = figures_dir / f"{fig_id}.png"
        camera_path = _project_root / "state" / f"camera_{fig_id}.json"
        if is_cache_valid(out_png, src, camera_path=camera_path):
            print(f"[4dpaper] {fig_id}.png is up to date — skipping.", file=sys.stderr)
        else:
            print(f"[4dpaper] Generating {fig_id}.png …", file=sys.stderr)
            try:
                generate_png_figure(src, field, time_spec, out_png, fig_id=fig_id)
            except Exception as exc:
                print(f"[4dpaper] ERROR generating {fig_id}.png: {exc}", file=sys.stderr)
                sys.exit(1)
```

### Step 7: Run full test suite

```bash
.venv/bin/pytest tests/ -q
```

Expected: 26+ tests PASS, 0 FAIL

### Step 8: Commit

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_extension.py
git commit -m "feat: generate_png_figure applies saved camera state when available"
```

---

## Task 3: JS camera sync injection in HTML figures

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py`
- Modify: `tests/test_extension.py`

Two changes:
1. Add `_camera_sync_snippet(fig_id)` module-level helper that returns the HTML+JS badge
2. `generate_html_figure()` gains `fig_id` param; injects snippet into the HTML
3. `main()` passes `fig_id` to `generate_html_figure()`

---

### Step 1: Write failing tests

Add to `tests/test_extension.py`:

```python
class TestCameraSyncSnippet:
    def test_contains_fig_id(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-test")
        assert "fig-test" in snippet

    def test_contains_event_hook(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        assert "onEndInteractionEvent" in snippet

    def test_contains_badge_element(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        assert "camera-badge" in snippet
        assert "Default view" in snippet

    def test_contains_fetch_url(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        assert "localhost:5006/camera/" in snippet

    def test_custom_server_url(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm", server_url="http://localhost:9000")
        assert "localhost:9000/camera/" in snippet
        assert "localhost:5006" not in snippet
```

### Step 2: Run tests, verify they fail

```bash
.venv/bin/pytest tests/test_extension.py::TestCameraSyncSnippet -v
```

Expected: `AttributeError: module has no attribute '_camera_sync_snippet'`

### Step 3: Add `_camera_sync_snippet` to `_extensions/4dpaper/4dpaper.py`

Add this function after `is_cache_valid` and before `generate_png_figure`:

```python
def _camera_sync_snippet(fig_id: str, server_url: str = "http://localhost:5006") -> str:
    """
    Return an HTML+JS snippet that:
    - Shows a '📷 Default view' badge (position:fixed, top-right of iframe)
    - After each rotation end, POSTs {position, focal_point, view_up} to the server
    - Updates the badge to '📷 Camera synced' on success

    vtk.js exposes window.renderWindow after OfflineLocalView.load() is called.
    The interactor's onEndInteractionEvent fires after each drag ends.
    The fetch is debounced 500ms so rapid drags only send one request.
    """
    import json as _json
    fig_id_js = _json.dumps(fig_id)
    server_js = _json.dumps(server_url)
    return (
        f'<div id="camera-badge-{fig_id}" style="position:fixed;top:8px;right:8px;'
        f'background:rgba(80,80,80,0.75);color:#fff;padding:4px 8px;'
        f'border-radius:4px;font-size:11px;font-family:monospace;'
        f'z-index:9999;pointer-events:none;">&#128247; Default view</div>\n'
        f'<script>\n'
        f'(function(){{\n'
        f'  var FIG_ID={fig_id_js}, SERVER={server_js};\n'
        f'  var badge=document.getElementById("camera-badge-{fig_id}");\n'
        f'  var timer=null;\n'
        f'  function waitRW(cb){{\n'
        f'    if(window.renderWindow){{cb(window.renderWindow);}}\n'
        f'    else{{setTimeout(function(){{waitRW(cb);}},100);}}\n'
        f'  }}\n'
        f'  waitRW(function(rw){{\n'
        f'    rw.getInteractor().onEndInteractionEvent(function(){{\n'
        f'      clearTimeout(timer);\n'
        f'      timer=setTimeout(function(){{\n'
        f'        var cam=rw.getRenderers().getFirst().getActiveCamera();\n'
        f'        fetch(SERVER+"/camera/"+FIG_ID,{{\n'
        f'          method:"POST",\n'
        f'          headers:{{"Content-Type":"application/json"}},\n'
        f'          body:JSON.stringify({{\n'
        f'            position:cam.getPosition(),\n'
        f'            focal_point:cam.getFocalPoint(),\n'
        f'            view_up:cam.getViewUp()\n'
        f'          }})\n'
        f'        }}).then(function(r){{\n'
        f'          if(r.ok){{badge.innerHTML="&#128247; Camera synced";'
        f'badge.style.background="rgba(0,160,0,0.75);";}}\n'
        f'        }}).catch(function(){{\n'
        f'          badge.innerHTML="&#128247; Sync error";\n'
        f'          badge.style.background="rgba(180,0,0,0.75)";\n'
        f'        }});\n'
        f'      }},500);\n'
        f'    }});\n'
        f'  }});\n'
        f'}})();\n'
        f'</script>'
    )
```

### Step 4: Run tests, verify they pass

```bash
.venv/bin/pytest tests/test_extension.py::TestCameraSyncSnippet -v
```

Expected: 5 PASS

### Step 5: Update `generate_html_figure` signature and inject snippet

**New signature** (add `fig_id` param):

```python
def generate_html_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
) -> None:
```

**At the end of the function**, after the existing `html.replace("100vw", "900px").replace("100vh", "600px")` line and before `output_path.write_text(html)`, add:

```python
    if fig_id:
        html = html.replace("</body>", _camera_sync_snippet(fig_id) + "\n</body>")
```

So the final block becomes:

```python
    html = output_path.read_text()
    html = html.replace("100vw", "900px").replace("100vh", "600px")
    if fig_id:
        html = html.replace("</body>", _camera_sync_snippet(fig_id) + "\n</body>")
    output_path.write_text(html)
```

### Step 6: Update `main()` to pass `fig_id` to `generate_html_figure`

In `main()`, replace the HTML generation call (currently):

```python
                generate_html_figure(src, field, time_spec, out_html)
```

With:

```python
                generate_html_figure(src, field, time_spec, out_html, fig_id=fig_id)
```

### Step 7: Run full test suite

```bash
.venv/bin/pytest tests/ -q
```

Expected: 31+ tests PASS, 0 FAIL

### Step 8: Commit

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_extension.py
git commit -m "feat: inject camera sync JS badge into HTML figures"
```

---

## Task 4: Update launch command documentation + end-to-end verify

**Files:**
- Modify: `dashboard/README.md` (or wherever the launch command is documented)
- No new tests needed — manual verification steps

---

### Step 1: Find and update the launch command

Search for the `panel serve` command in README or docs:

```bash
grep -r "panel serve" . --include="*.md" --include="*.txt" -l
```

Update the command to include `--plugins dashboard.camera_plugin`:

```bash
panel serve dashboard/app.py \
  --plugins dashboard.camera_plugin \
  --static-dirs output=_output \
  --show --port 5006
```

### Step 2: Run the full test suite one final time

```bash
.venv/bin/pytest tests/ -q
```

Expected: all tests PASS

### Step 3: Manual smoke test (verify JS injection)

```bash
# Generate a fresh HTML figure (delete cached one first)
rm -f state/figures/fig-vm.html
QUARTO_PYTHON=.venv/bin/python QUARTO_PROJECT_DIR=. .venv/bin/python _extensions/4dpaper/4dpaper.py
```

Check the generated HTML:

```bash
grep -c "camera-badge" state/figures/fig-vm.html
grep -c "onEndInteractionEvent" state/figures/fig-vm.html
```

Expected: both return `1`

### Step 4: Manual smoke test (verify PNG uses camera)

```bash
# Write a fake camera JSON
mkdir -p state
echo '{"position":[0,0,0.5],"focal_point":[0,0,0],"view_up":[0,1,0]}' > state/camera_fig-vm.json

# Delete cached PNG to force regeneration
rm -f state/figures/fig-vm.png

# Run the pre-render hook
QUARTO_PYTHON=.venv/bin/python QUARTO_PROJECT_DIR=. .venv/bin/python _extensions/4dpaper/4dpaper.py
```

Expected log: `[4dpaper] Applied saved camera for fig-vm`

### Step 5: Commit

```bash
git add -A
git commit -m "docs: update launch command to include camera plugin"
```

---

## Appendix: Key files summary

| File | Change |
|------|--------|
| `dashboard/camera_plugin.py` | NEW — Tornado `CameraHandler` + `ROUTES` for Panel `--plugins` |
| `tests/test_camera_plugin.py` | NEW — tests for camera plugin |
| `_extensions/4dpaper/4dpaper.py` | `is_cache_valid` + `camera_path`; `generate_png_figure` + `fig_id`; `generate_html_figure` + JS injection; `main()` passes `fig_id` |
| `tests/test_extension.py` | New `TestIsCacheValid` cases + `TestCameraSyncSnippet` |

## Appendix: What does NOT change

- `dashboard/utils.py` — `save_camera_state` and `load_camera_state` already there
- `dashboard/pages/paper_page.py` — no changes needed
- `_extensions/4dpaper/shortcodes.lua` — no changes needed
- `analysis_report.qmd` — no changes needed
