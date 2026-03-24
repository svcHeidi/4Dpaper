# Lock Redesign Design

## Goal

Four focused changes to `_controls_strip_snippet` in `_extensions/4dpaper/4dpaper.py`:

1. Fix time-slider rendering when the vtk.js interactor is disabled
2. Move the lock to a permanent top-right corner widget; remove the lock popup
3. Make the lock a hard gate — blocking field, time, and corner-cube interaction
4. Show a "locked" badge to the left of the lock icon when a blocked interaction fires

---

## Single-file change

All changes are inside `_controls_strip_snippet` in `_extensions/4dpaper/4dpaper.py`. No new Python functions, no Lua changes, no new endpoints.

---

## Component 1: Rendering Fix

### Problem

The time slider `input` handler calls `renderWindow.render()` but vtk.js may suppress the redraw when the interactor is disabled via `setEnabled(0)`. The result: the displayed mesh does not update until the user moves the view.

### Fix

In the time slider `input` event handler, move `renderWindow.render()` to fire immediately after `arr.setData()` / `arr.modified()` / `pd.modified()`, before any debounce timer. Only the postMessage to the parent frame is debounced (100 ms). The render call itself is synchronous and unconditional.

```js
// Before (render inside debounce):
clearTimeout(_tTimer);
_tTimer = setTimeout(function(){
    arr.setData(_decT(b64), 1);
    arr.modified(); pd.modified();
    window.renderWindow.render();   // ← inside debounce
    parent.postMessage(...);
}, 100);

// After (render immediate, postMessage debounced):
arr.setData(_decT(b64), 1);
arr.modified(); pd.modified();
window.renderWindow.render();       // ← immediate
clearTimeout(_tTimer);
_tTimer = setTimeout(function(){
    parent.postMessage(...);
}, 100);
```

---

## Component 2: Lock Widget at Top-Right

### Position

`position:fixed; top:4px; right:4px; z-index:9999` — inside the srcdoc iframe viewport, symmetric with the corner cube at `bottom:4px; left:4px`.

### Element

```html
<div id="cs-lock-{fig_id_safe}"
     style="position:fixed;top:4px;right:4px;z-index:9999;
            width:26px;height:26px;
            background:rgba(20,20,30,0.72);
            border:1px solid rgba(255,255,255,0.18);
            border-radius:5px;cursor:pointer;font-size:13px;
            display:flex;align-items:center;justify-content:center;
            color:#fff;"
     title="Lock / unlock figure">🔒</div>
```

The icon is `🔒` when locked, `🔓` when unlocked.

### Toggle behaviour

Clicking the widget directly toggles `_locked` (a boolean declared at snippet scope) and updates the icon in place. No popup is opened. The `4dpaper-lock-toggle` postMessage to the parent frame fires on each toggle so the dashboard can persist lock state server-side. This replaces the previous lock button (`cs-btn-lock-{fig_id_safe}`) in the right strip.

### Removal of lock popup

`cs-pop-lock-{fig_id_safe}` is no longer emitted. The camera-sync badge previously inside it is also removed. Camera sync confirmation is no longer surfaced in the UI (the sync still happens — only the visual confirmation badge is removed).

### Strip changes

`cs-btn-lock-{fig_id_safe}` is removed from the strip HTML. The right strip now contains only field and time buttons. If neither is needed, the strip is absent entirely. The `show_lock_btn` parameter still controls whether the top-right lock widget is emitted (default `True`).

---

## Component 3: Hard Lock Gate

When `_locked` is `true`, three interactions are blocked:

### Field and time strip buttons

`csToggle_()` checks `_locked` before acting:

```js
function csToggle_{fig_id_safe}(name) {
    if (_locked) { _showLockedBadge(); return; }
    // ... existing toggle logic
}
```

The strip buttons remain visible. They simply do not open their popups while locked.

### Corner cube

The SVG click listener checks `_locked` before calling `_openRotation()`:

```js
svg.addEventListener('click', function() {
    if (_locked) { _showLockedBadge(); return; }
    // ... existing open/close logic
});
```

### Camera send

`_sendCam()` already returns early when `_locked` — unchanged.

---

## Component 4: "Locked" Badge

### Element

```html
<div id="cs-lock-badge-{fig_id_safe}"
     style="position:fixed;top:4px;right:36px;z-index:9999;
            display:none;
            background:rgba(20,20,30,0.88);
            border:1px solid rgba(255,255,255,0.12);
            border-radius:4px;padding:2px 6px;
            font-family:monospace;font-size:10px;color:#f88;">
  locked</div>
```

Positioned immediately to the left of the lock icon (`right:36px` = 4px margin + 26px icon + 6px gap).

### Show / hide

```js
var _lockBadgeTimer = null;
function _showLockedBadge() {
    var b = document.getElementById('cs-lock-badge-{fig_id_safe}');
    b.style.display = 'block';
    clearTimeout(_lockBadgeTimer);
    _lockBadgeTimer = setTimeout(function(){ b.style.display = 'none'; }, 1500);
}
```

One shared function and one shared timer serve all three blocked interactions.

---

## Behaviour Summary

| State | Lock icon | Strip buttons | Corner cube | Time/field popups | Locked badge |
|---|---|---|---|---|---|
| Unlocked | 🔓 | respond normally | respond normally | open normally | hidden |
| Locked | 🔒 | no response | no response | do not open | flashes 1.5 s on click |

---

## Testing

All tests live in `tests/test_controls_strip.py`.

### New tests — `TestControlsStripHtml`

- `test_lock_widget_present_when_show_lock` — `cs-lock-{fig_id_safe}` present, `top:4px` and `right:4px` in its style
- `test_lock_widget_absent_when_hide` — `cs-lock-{fig_id_safe}` absent when `show_lock_btn=False`
- `test_lock_badge_present_when_show_lock` — `cs-lock-badge-{fig_id_safe}` present when `show_lock_btn=True`
- `test_lock_popup_absent` — `cs-pop-lock-{fig_id_safe}` NOT in HTML
- `test_lock_button_absent_from_strip` — `cs-btn-lock-{fig_id_safe}` NOT in HTML

### New tests — `TestControlsStripJs`

- `test_show_locked_badge_function_present` — `_showLockedBadge` in snippet when `show_lock_btn=True`
- `test_toggle_checks_locked_flag` — `if(_locked)` appears before the toggle loop body in `csToggle_`
- `test_corner_cube_checks_locked_flag` — `if(_locked)` in the SVG click listener when both `show_orientation=True` and `show_lock_btn=True`
- `test_render_before_debounce` — `renderWindow.render()` appears before `setTimeout` in time snippet (when time data provided)

### Existing tests to update

- `test_lock_button_in_strip_when_show_lock` — update: assert `cs-btn-lock-` is **absent** (moved to corner widget)
- `test_popup_panels_present_for_active_features` — remove assertion for `cs-pop-lock-{fig_id_safe}`
- `test_lock_toggle_sends_postmessage` — verify `4dpaper-lock-toggle` still present (in lock widget click handler, not popup)
- Any test asserting `cs-pop-lock-` is present — invert to assert absent

---

## What does NOT change

- `generate_html_figure` call signature — no new parameters
- `show_lock_btn` parameter semantics
- `_locked` variable declaration (still present when `show_lock_btn=True`)
- `_sendCam()` early-return on `_locked` — unchanged
- `4dpaper-lock-toggle` postMessage — still fires on lock toggle
- Corner cube widget position and orientation tracking
- Field switcher and time scrubber logic (except render timing fix)
- Camera apply listener
