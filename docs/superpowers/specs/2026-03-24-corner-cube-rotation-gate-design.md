# Corner Cube Rotation Gate Design

## Goal

Replace the axes strip button with a small live orientation cube in the lower-left corner of each figure. The cube tracks camera orientation at all times and acts as the only way to unlock mesh rotation — clicking it enables the vtk.js interactor and shows a preset-view popup. Closing the popup re-locks the figure.

## Motivation

Scientific paper figures should not rotate accidentally while a reader scrolls or clicks. Currently the vtk.js interactor is always enabled, so any mouse drag on a figure changes the view. Gating rotation behind an intentional click on the corner cube eliminates accidental rotations without hiding the feature.

## Architecture

Single file change: `_extensions/4dpaper/4dpaper.py`, inside `_controls_strip_snippet`.

No new Python functions, no new endpoints, no Lua changes.

---

## Component: Corner Cube Widget

### Positioning

Fixed at `position:fixed; bottom:4px; left:4px; z-index:9999` inside the srcdoc iframe viewport.

### Size

28×28px SVG element (`id="cs-svg-axes-{fig_id_safe}"`). Same element ID as before — just relocated from inside the axes popup to the corner.

### Appearance

Draws three coloured axis lines projected from the current camera view matrix:
- X axis → red (`#f66`)
- Y axis → green (`#6f6`)
- Z axis → blue (`#66f`)
- Labels "x", "y", "z" at each tip
- Background: `rgba(10,10,20,0.55)` rounded rect behind the SVG for legibility
- Semi-transparent border: `1px solid rgba(255,255,255,0.12)`
- Cursor: `pointer`

### Live tracking

The `_axLoop` requestAnimationFrame loop runs continuously once the renderer is available (not gated behind popup open state). It reads `renderer.getActiveCamera()` on every frame and redraws the SVG. This is the same projection math already implemented in `_controls_strip_snippet`.

### Scope gate

The corner cube is only emitted when `show_orientation=True`. When `show_orientation=False` (non-first timeseries subfigures), the cube is absent and the interactor remains enabled (unchanged behaviour).

---

## Component: Interactor Lock

### Default state

`_iact` is declared at snippet scope and initialised to `null`:
```js
var _iact = null;
```

As soon as the renderer is found by the `_wR` polling loop, `_iact` is set and the interactor is locked:
```js
_iact = window.renderWindow.getInteractor();
if (_iact) _iact.setEnabled(0);
```

If `getInteractor()` returns `null` (e.g. a stub HTML without a full vtk renderer), `_iact` stays `null` and all calls below that guard with `if (_iact)` are safe no-ops.

If the user clicks the cube before the renderer is ready (`_iact` is still `null`), `_openRotation` does not call `setEnabled` but still shows the popup — the figure was never locked in the first place so rotation is already possible.

### Unlock / re-lock

```js
function _openRotation() {
    if (_iact) _iact.setEnabled(1);
    document.getElementById('cs-pop-axes-{fig_id_safe}').style.display = 'flex';
}
function _closeRotation() {
    if (_iact) _iact.setEnabled(0);
    document.getElementById('cs-pop-axes-{fig_id_safe}').style.display = 'none';
}
```

Toggle on cube click:
```js
document.getElementById('cs-svg-axes-{fig_id_safe}').addEventListener('click', function() {
    var pop = document.getElementById('cs-pop-axes-{fig_id_safe}');
    if (pop.style.display === 'none' || pop.style.display === '') {
        _openRotation();
    } else {
        _closeRotation();
    }
});
```

### Camera sync interaction

Camera save (`_sendCam`) fires on `mouseup` / `touchend`. When a preset button is clicked, `_closeRotation()` is called first (disabling the interactor), then the `mouseup` from the button click fires `_sendCam`. This is safe: `_locked` auto-resets to `false` after the fetch completes, so no stuck state is possible. The ordering is: preset click → `_closeRotation()` (interactor off) → `mouseup` → `_sendCam` fires → fetch completes → `_locked = false`. No changes needed to the camera sync logic.

---

## Component: Preset Popup

### Positioning

`position:fixed; bottom:36px; left:4px` — appears directly above the corner cube.

Same element ID: `cs-pop-axes-{fig_id_safe}`.

### Contents

Four preset buttons in a 2×2 grid:

```
[ Iso ]  [ +X ]
[ +Y  ]  [ +Z ]
```

Each button calls `csSetView_{fig_id_safe}('iso'|'+X'|'+Y'|'+Z')`. `_closeRotation()` is called as the **last line inside the `csSetView_` function body** (not as a wrapper at the call site), so every preset application — whether triggered by button click or programmatically — always re-locks the interactor and hides the popup.

### Styling

Same dark panel as the existing popups:
```
background: rgba(20,20,30,0.88)
border: 1px solid rgba(255,255,255,0.12)
border-radius: 6px
padding: 8px
```

No "done" button needed — clicking a preset or clicking the cube closes the popup.

---

## Strip Changes

Previously the axes popup was accessed via three elements all emitted by `_controls_strip_snippet`:
- `cs-btn-axes-{fig_id_safe}` — strip button (🧭), **removed**
- `cs-svg-axes-{fig_id_safe}` — SVG inside the popup, **relocated to corner widget**
- `cs-pop-axes-{fig_id_safe}` — popup panel, **repositioned to above corner widget**

After this change:
- `cs-btn-axes-{fig_id_safe}` is **no longer emitted** (removed from strip HTML).
- `cs-svg-axes-{fig_id_safe}` is now a direct child of the corner widget div, not inside the popup.
- `cs-pop-axes-{fig_id_safe}` still exists but is now anchored at `bottom:36px; left:4px` instead of the strip popup position.
- Lock, field, and time strip buttons are unchanged.
- If `show_orientation=False`, none of the three axes elements are emitted.

---

## Behaviour Summary

### `show_orientation=True` (default)

| State | Interactor | Corner cube visible | Popup visible |
|---|---|---|---|
| On load | disabled | yes (tracking) | no |
| Cube clicked | enabled | yes | yes |
| Preset clicked | disabled | yes | no |
| Cube clicked again | disabled | yes | no |

### `show_orientation=False` (non-first timeseries subfigures)

| State | Interactor | Corner cube visible | Popup visible |
|---|---|---|---|
| Always | enabled (unchanged) | no | no |

No locking logic is injected when `show_orientation=False`.

---

## Testing

All tests live in `tests/test_controls_strip.py`.

### New tests to add

**`TestControlsStripHtml`**
- `test_corner_cube_present_when_show_orientation` — `cs-svg-axes-` in HTML, positioned `bottom:4px;left:4px`
- `test_axes_button_absent_from_strip` — `cs-btn-axes-` NOT in HTML when `show_orientation=True`
- `test_axes_popup_above_corner` — `cs-pop-axes-` positioned `bottom:36px;left:4px`
- `test_corner_cube_absent_when_orientation_hidden` — no `cs-svg-axes-` when `show_orientation=False`

**`TestControlsStripJs`**
- `test_interactor_disabled_on_load` — `setEnabled(0)` present in snippet when `show_orientation=True`
- `test_interactor_not_disabled_when_orientation_hidden` — `setEnabled(0)` absent when `show_orientation=False` (interactor stays free)
- `test_iact_declared_at_top` — `var _iact = null` present before the `_wR` polling block
- `test_interactor_enabled_on_open` — `setEnabled(1)` present in `_openRotation` function body
- `test_null_interactor_safe` — both `_openRotation` and `_closeRotation` contain `if (_iact)` guard before `setEnabled` call
- `test_click_handler_on_svg` — `cs-svg-axes-` addEventListener click in snippet
- `test_preset_closes_popup` — `_closeRotation()` appears inside the `csSetView_` function body (check that the string `_closeRotation()` appears between the opening `function csSetView_` and its closing `}`)

### Existing tests to update

- `test_axes_raf_loop_absent_when_hidden` — already tests that `_axLoop` is absent when `show_orientation=False`. No change needed.
- Any test asserting `cs-btn-axes-` is present — update to assert it is **absent** (button removed from strip).
- Any test asserting `cs-svg-axes-` position — update expected position to `bottom:4px;left:4px` (corner, not strip popup).

---

## What does NOT change

- `generate_html_figure` call signature — no new parameters
- Camera sync logic (`_sendCam`, `_wR`, `_showBadge`, `_locked`)
- Field switcher and time scrubber popup behaviour
- Camera lock button in the right strip
- `show_orientation` parameter semantics
- PDF/PNG generation path
