# Camera Sync Bug Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix camera sync so that rotating the 3D figure in HTML actually persists the camera state to JSON, and PDF export uses that saved camera.

**Architecture:** Remove the broken `.then()` patch on `OfflineLocalView.load()` (which is a void function, not a Promise). Update the camera sync JS snippet to poll for `window.renderWindow` (already set by vtk.js internally) and derive the renderer via `window.renderWindow.getRenderers().getFirst()`.

**Tech Stack:** Python (4dpaper.py pre-render hook), JavaScript (camera sync snippet in generated HTML), pytest

---

### Task 1: Update `_camera_sync_snippet()` — remove `__4dRenderer` dependency

The snippet currently waits for both `window.renderWindow` AND `window.__4dRenderer`. vtk.js already sets `window.renderWindow` but never sets `__4dRenderer`. Fix the snippet to derive the renderer from `window.renderWindow.getRenderers().getFirst()`.

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py:91-152`
- Test: `tests/test_extension.py:169-234`

**Step 1: Update failing tests first**

In `tests/test_extension.py`, update `TestCameraSyncSnippet`:

- `test_waits_for_renderer_global` (line 211-216): Change assertion from `window.__4dRenderer` to `getRenderers` — the snippet now derives the renderer from renderWindow, not a separate global.
- `test_camera_api_chain` (line 204-209): Keep as-is — `renderer.getActiveCamera()` is still used.

```python
# test_waits_for_renderer_global — replace assertion
def test_waits_for_renderer_global(self):
    mod = _load_4dpaper()
    snippet = mod._camera_sync_snippet("fig-vm")
    # Snippet derives renderer from renderWindow.getRenderers()
    assert "getRenderers" in snippet
    assert "window.__4dRenderer" not in snippet
```

**Step 2: Run tests — verify they fail**

Run: `.venv/bin/python -m pytest tests/test_extension.py::TestCameraSyncSnippet::test_waits_for_renderer_global -v`
Expected: FAIL — old snippet still has `window.__4dRenderer`

**Step 3: Update `_camera_sync_snippet()` in `4dpaper.py`**

Replace `_camera_sync_snippet` function (lines 91-152) with:

```python
def _camera_sync_snippet(fig_id: str, server_url: str = "http://localhost:5006") -> str:
    """
    Return an HTML+JS snippet that:
    - Shows a '📷 Default view' badge (position:fixed, top-right of iframe)
    - After each rotation end, POSTs {position, focal_point, view_up} to the server
    - Updates the badge to '📷 Camera synced' on success

    vtk.js sets window.renderWindow internally via OfflineLocalView.load().
    The renderer is derived via renderWindow.getRenderers().getFirst().
    The interactor's onEndInteractionEvent fires after each drag ends.
    The fetch is debounced 500ms so rapid drags only send one request.
    """
    fig_id_js = json.dumps(fig_id).replace("</", "<\\/")
    camera_prefix_js = json.dumps(server_url.rstrip("/") + "/camera/").replace("</", "<\\/")
    fig_id_safe = fig_id.replace("</", "<\\/")
    return (
        f'<div id="camera-badge-{fig_id}" style="position:fixed;top:8px;right:8px;'
        f'background:rgba(80,80,80,0.75);color:#fff;padding:4px 8px;'
        f'border-radius:4px;font-size:11px;font-family:monospace;'
        f'z-index:9999;pointer-events:none;">&#128247; Default view</div>\n'
        f'<script>\n'
        f'(function(){{\n'
        f'  var FIG_ID={fig_id_js}, CAM_PREFIX={camera_prefix_js};\n'
        f'  var badge=document.getElementById("camera-badge-{fig_id_safe}");\n'
        f'  var timer=null;\n'
        f'  function waitRW(cb){{\n'
        f'    function check(){{\n'
        f'      var rw=window.renderWindow;\n'
        f'      if(rw&&rw.getRenderers){{\n'
        f'        var renderer=rw.getRenderers().getFirst();\n'
        f'        if(renderer){{cb(rw,renderer);return;}}\n'
        f'      }}\n'
        f'      setTimeout(check,200);\n'
        f'    }}\n'
        f'    check();\n'
        f'  }}\n'
        f'  waitRW(function(rw,renderer){{\n'
        f'    rw.getInteractor().onEndInteractionEvent(function(){{\n'
        f'      clearTimeout(timer);\n'
        f'      timer=setTimeout(function(){{\n'
        f'        var cam=renderer.getActiveCamera();\n'
        f'        fetch(CAM_PREFIX+FIG_ID,{{\n'
        f'          method:"POST",\n'
        f'          headers:{{"Content-Type":"application/json"}},\n'
        f'          body:JSON.stringify({{\n'
        f'            position:cam.getPosition(),\n'
        f'            focal_point:cam.getFocalPoint(),\n'
        f'            view_up:cam.getViewUp()\n'
        f'          }})\n'
        f'        }}).then(function(r){{\n'
        f'          if(r.ok){{badge.innerHTML="&#128247; Camera synced";'
        f'badge.style.background="rgba(0,160,0,0.75)";}}\n'
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

**Step 4: Run snippet tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/test_extension.py::TestCameraSyncSnippet -v`
Expected: All 11 tests PASS

**Step 5: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_extension.py
git commit -m "fix: update camera sync snippet to derive renderer from renderWindow"
```

---

### Task 2: Remove the broken `.then()` patch from `generate_html_figure()`

The `OfflineLocalView.load()` is a void function — `.then()` on `undefined` silently fails. Since vtk.js already sets `window.renderWindow` internally, the patch is unnecessary. Remove it.

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py:312-334`

**Step 1: Remove the patch block**

Delete the entire block from line 312 to 334 in `4dpaper.py`:

```python
    # DELETE THIS ENTIRE BLOCK (lines 312-334):
    # Patch OfflineLocalView.load to expose window.renderWindow and
    # window.__4dRenderer so the camera sync snippet can hook into them.
    # ...
    _old_load = "OfflineLocalView.load(container, { base64Str });"
    _new_load = (...)
    if _old_load in html:
        html = html.replace(_old_load, _new_load, 1)
    else:
        print(...)
```

**Step 2: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS (the generate_html_figure smoke test still creates valid HTML)

**Step 3: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py
git commit -m "fix: remove broken .then() patch on void OfflineLocalView.load()"
```

---

### Task 3: Manual end-to-end verification

**Step 1: Regenerate HTML figures**

Delete cached figures to force regeneration:
```bash
rm -f state/figures/fig-vm.html state/figures/fig-vm.png
```

Then rebuild:
```bash
quarto render analysis_report.qmd --to html
```

Verify the generated HTML no longer has the `.then(function(obj){...})` patch:
```bash
grep "then(function(obj)" state/figures/fig-vm.html  # should return nothing
grep "window.renderWindow" state/figures/fig-vm.html  # should find it (set by vtk.js)
grep "getRenderers" state/figures/fig-vm.html  # should find it (our snippet)
```

**Step 2: Test camera sync in browser**

1. Start dashboard: `panel serve dashboard/app.py --plugins dashboard.camera_plugin --static-dirs output=_output --show --port 5006`
2. Click "Rebuild HTML"
3. In the preview iframe, interact with the 3D figure (rotate it)
4. Watch the badge — it should change from "📷 Default view" to "📷 Camera synced"
5. Check the saved file: `cat state/camera_fig-vm.json` — should have new camera values

**Step 3: Test PDF export with saved camera**

1. Click "Export PDF" in the dashboard
2. Open `_output/analysis_report.pdf`
3. The figure should show the rotated camera view, NOT the default isometric view

**Step 4: Commit verified state**

```bash
git add -A
git commit -m "fix: camera sync now works end-to-end (HTML → JSON → PDF)"
```
