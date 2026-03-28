# Camera Sync Bug Fix

**Date**: 2026-03-04
**Status**: Approved (separate workstream)

## Problem

After changing the camera in the interactive HTML figure, the PDF export still shows the default/isometric view. Camera state is never synced.

## Root Cause

In `_extensions/4dpaper/4dpaper.py`, the `generate_html_figure()` function patches `OfflineLocalView.load()` by appending `.then(function(obj){...})` to capture the renderWindow and renderer.

**The bug**: `OfflineLocalView.load()` is a **void function** — it does NOT return a Promise. Calling `.then()` on `undefined` throws a silent TypeError, so `window.renderWindow` and `window.__4dRenderer` are never set by our patch. The camera sync snippet polls for these globals forever and never fires.

**Evidence from the bundled vtk.js** (in `state/figures/fig-vm.html`):
```js
// qC IS OfflineLocalView.load — it's a void function
function qC(e,t){
  // ...
  const r = ub.newInstance({...}).getRenderWindow();
  // vtk.js ALREADY sets: n.g.renderWindow = r  (i.e. window.renderWindow = r)
  // But it does NOT return a Promise
}
```

vtk.js already sets `window.renderWindow` internally. But it does NOT expose the renderer as a global.

## Fix

### 1. Remove the `.then()` patch from `generate_html_figure()`

Delete the `_old_load` / `_new_load` replacement block (lines 316-334 of `4dpaper.py`). vtk.js already sets `window.renderWindow` — no patch needed for that.

### 2. Update `_camera_sync_snippet()` to use vtk.js globals directly

Change the `waitRW` function to:
- Poll for `window.renderWindow` only (vtk.js already sets this)
- Derive the renderer via `window.renderWindow.getRenderers().getFirst()`
- Remove dependency on `window.__4dRenderer`

```js
function waitRW(cb) {
  function check() {
    var rw = window.renderWindow;
    if (rw && rw.getRenderers) {
      var renderer = rw.getRenderers().getFirst();
      if (renderer) { cb(rw, renderer); return; }
    }
    setTimeout(check, 200);
  }
  check();
}
```

### 3. Add a timing guard

vtk.js sets `window.renderWindow` early, but the scene may not be fully loaded yet (the `synchronize(e.scene)` call is inside a callback). Add a check that the renderer has actors before hooking the interactor:

```js
waitRW(function(rw, renderer) {
  // Wait for scene to have content
  if (renderer.getActors().length === 0) {
    setTimeout(function(){ waitRW(cb); }, 200);
    return;
  }
  rw.getInteractor().onEndInteractionEvent(function(){ ... });
});
```

## Files Affected

| File | Change |
|------|--------|
| `_extensions/4dpaper/4dpaper.py` | Remove `.then()` patch, update `_camera_sync_snippet()` |
| `tests/test_extension.py` | Update camera sync snippet tests (remove `__4dRenderer` assertions) |

## Verification

1. `quarto render analysis_report.qmd --to html` — generates HTML with updated snippet
2. Open HTML in browser, rotate the 3D view → badge should change to "Camera synced"
3. Check `state/camera_fig-vm.json` has updated values
4. `quarto render analysis_report.qmd --to pdf` — PNG should reflect saved camera
5. All tests pass: `.venv/bin/python -m pytest tests/ -v`
