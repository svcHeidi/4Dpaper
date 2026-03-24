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

The time slider `input` handler calls `renderWindow.render()` inside a 100 ms debounce. When the vtk.js interactor is disabled via `setEnabled(0)`, the deferred render may be suppressed, causing the mesh to not redraw until the user moves the view.

### Fix

Move `renderWindow.render()` to fire immediately after `arr.setData()` / `arr.modified()` / `pd.modified()`, before the debounce timer. Only the postMessage to the parent frame remains inside the `setTimeout`. The render call is synchronous and unconditional.

```js
// After fix:
arr.setData(_decT(b64), 1);
arr.modified(); pd.modified();
window.renderWindow.render();       // immediate — not inside debounce
clearTimeout(_tTimer);
_tTimer = setTimeout(function(){
    parent.postMessage(...);
}, 100);
```

---

## Component 2: Lock Widget at Top-Right

### Position

`position:fixed; top:4px; right:4px; z-index:9999` — inside the srcdoc iframe viewport, symmetric with the corner cube at `bottom:4px; left:4px`.

### Element ID

`cs-lock-widget-{fig_id_safe}` (distinct from the old `cs-lock-{fig_id_safe}` which was the button inside the now-removed lock popup).

### HTML

```html
<div id="cs-lock-widget-{fig_id_safe}"
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

### `_setLocked(bool)` helper

Toggling lock is handled by a `_setLocked(v)` helper (declared at snippet scope when `show_lock_btn=True`). This centralises icon updates and `_locked` state for both the widget click handler and the postMessage-based lock-state handler:

```js
function _setLocked(v) {
    _locked = v;
    var w = document.getElementById('cs-lock-widget-{fig_id_safe}');
    if (w) w.textContent = v ? '🔒' : '🔓';
}
```

The widget click handler calls `_setLocked(!_locked)` then fires the `4dpaper-lock-toggle` postMessage to the parent frame so the dashboard can persist lock state server-side.

### `4dpaper-lock-state` and `4dpaper-lock-ack` message handlers

Both handlers currently call `_setLocked`. They are retained unchanged — they now call the new `_setLocked` helper above. No behaviour change.

### Removal of lock popup and camera-sync badge

`cs-pop-lock-{fig_id_safe}` is no longer emitted. The `_showBadge` function and the `4dpaper-camera-ack` message handler that called it are removed. Camera sync still fires (`_sendCam` is unchanged) but no visual confirmation is shown in the figure. The `_showBadge` stub that was previously emitted when `show_lock_btn=False` is also removed.

### Strip changes

`cs-btn-lock-{fig_id_safe}` is removed from the strip HTML. The right strip now contains only field and time buttons.

### Early-exit guard update

The guard that returns `""` when nothing is active must now also account for the lock widget:

```python
if not strip_btns and not show_orientation and not show_lock_btn:
    return ""
```

This ensures that `_controls_strip_snippet("fig-vm", show_lock_btn=True)` with no fields/time/orientation still emits the lock widget. `test_returns_empty_when_all_hidden` passes `show_lock_btn=False, show_orientation=False` and still expects `""` — it passes unchanged.

### `"lock"` removed from `_CS_ALL`

`_CS_ALL` changes from `["axes","lock","field","time"]` to `["axes","field","time"]`. The popup `cs-pop-lock-{fig_id_safe}` no longer exists, so `csToggle_()` must not try to look it up.

---

## Component 3: Hard Lock Gate

When `_locked` is `true`, two additional interactions are blocked (camera send already had this gate).

### Field and time strip buttons

`csToggle_()` checks `_locked` first:

```js
function csToggle_{fig_id_safe}(name) {
    if (_locked) { _showLockedBadge(); return; }
    // ... existing toggle logic
}
```

`_showLockedBadge` is only called when `show_lock_btn=True` (it is only emitted then). The strip buttons are still visible but do not open popups while locked.

### Corner cube — gated only when `show_lock_btn=True`

The corner cube SVG click listener includes the lock gate **only when both `show_orientation=True` and `show_lock_btn=True`**. When `show_lock_btn=False` and `show_orientation=True`, the lock gate and `_showLockedBadge` call are omitted — the corner cube behaves as before with no lock gate.

```js
// Emitted only when show_lock_btn=True:
if (_locked) { _showLockedBadge(); return; }
```

This avoids a `ReferenceError` from calling `_showLockedBadge()` when the badge element was never emitted.

### `_showBadge` removal

`_showBadge` is removed entirely (along with its no-op stub). Existing test `test_show_badge_always_declared` is **removed** — it tested a function that no longer exists.

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

Positioned immediately to the left of the lock icon (`right:36px` = 4 px margin + 26 px icon + 6 px gap). Starts hidden (`display:none`). Emitted only when `show_lock_btn=True`.

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

One shared function and timer serve all blocked interactions.

---

## Behaviour Summary

| State | Lock icon | Strip buttons | Corner cube | Locked badge |
|---|---|---|---|---|
| Unlocked | 🔓 | respond normally | respond normally | hidden |
| Locked | 🔒 | no response | no response (if show_lock_btn=True) | flashes 1.5 s on blocked click |
| show_lock_btn=False | — | respond normally | respond normally (no gate) | — |

---

## Testing

All tests live in `tests/test_controls_strip.py`.

### New tests — `TestControlsStripHtml`

- `test_lock_widget_present_when_show_lock` — `cs-lock-widget-fig_vm` present; `top:4px` and `right:4px` in its style
- `test_lock_widget_absent_when_hide` — `cs-lock-widget-fig_vm` absent when `show_lock_btn=False`
- `test_lock_badge_present_when_show_lock` — `cs-lock-badge-fig_vm` present and `display:none` in its inline style when `show_lock_btn=True`
- `test_lock_badge_absent_when_hide` — `cs-lock-badge-fig_vm` absent when `show_lock_btn=False`
- `test_lock_popup_absent` — `cs-pop-lock-fig_vm` NOT in HTML
- `test_lock_button_absent_from_strip` — `cs-btn-lock-fig_vm` NOT in HTML
- `test_lock_widget_absent_show_lock_btn_false_orientation_true` — when `show_lock_btn=False, show_orientation=True`: `cs-lock-widget-fig_vm` absent, `cs-lock-badge-fig_vm` absent

### New tests — `TestControlsStripJs`

- `test_show_locked_badge_function_present` — `_showLockedBadge` in snippet when `show_lock_btn=True`
- `test_show_locked_badge_absent_when_hide` — `_showLockedBadge` NOT in snippet when `show_lock_btn=False`
- `test_set_locked_helper_present` — `_setLocked` function in snippet when `show_lock_btn=True`
- `test_toggle_checks_locked_flag` — `if(_locked)` appears before the toggle loop body in `csToggle_` when `show_lock_btn=True`
- `test_corner_cube_checks_locked_flag` — `if(_locked)` in the SVG click listener when both `show_orientation=True` and `show_lock_btn=True`
- `test_corner_cube_no_locked_gate_when_lock_hidden` — `if(_locked)` NOT in the SVG click listener when `show_lock_btn=False` and `show_orientation=True`
- `test_render_before_debounce` — when time data provided: `renderWindow.render()` appears before the `setTimeout` in the time slider handler

### Existing tests to remove

- `test_show_badge_always_declared` — `_showBadge` is removed entirely; this test is deleted

### Existing tests to update

- `test_lock_button_in_strip_when_show_lock` → renamed `test_lock_button_absent_from_strip` (or updated to assert absent)
- `test_popup_panels_present_for_active_features` — remove assertion for `cs-pop-lock-fig_vm`; keep assertion for `cs-pop-axes-fig_vm`
- `test_lock_toggle_sends_postmessage` — verify `4dpaper-lock-toggle` still present (now in lock widget click handler, not popup button)
- `test_returns_empty_when_all_hidden` — guard call now `show_lock_btn=False, show_orientation=False`; test already passes these so no change needed, but verify it still returns `""`

---

## What does NOT change

- `generate_html_figure` call signature — no new parameters
- `show_lock_btn` parameter semantics (still controls lock widget emission)
- `_locked` variable declaration (still present at snippet scope when `show_lock_btn=True`)
- `_sendCam()` early-return on `_locked` — unchanged
- `4dpaper-lock-toggle` postMessage — still fires on lock toggle
- `4dpaper-lock-state` and `4dpaper-lock-ack` message handlers — retained, now call `_setLocked`
- Corner cube widget position and orientation tracking
- Field switcher logic
- Camera apply listener
