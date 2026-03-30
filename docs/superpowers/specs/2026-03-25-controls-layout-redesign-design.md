# Controls Layout Redesign Design

## Overview

Three changes to `_controls_strip_snippet` in `4dpaper.py`:

1. **Lock bug fix** — `_drawAxes()` does not check `_locked`; axes animate even when figure is locked. Fix: add `if(_locked)return;` early in `_drawAxes()`.
2. **Reference toggle** — The 56×56 axis SVG is always visible. Add a small 26×26 toggle button that shows/hides it. SVG starts hidden.
3. **Layout redesign** — Move the timeseries button from the right-side strip to the bottom-left cluster. Reposition the timeseries popup to open above the bottom-left cluster.

---

## Bug Fix: `_drawAxes` respects lock

Add `if(_locked)return;` immediately after the existing guard `if(!_renderer||!_svg)return;` in `_drawAxes()`.

When `_locked=true`, `_drawAxes` returns early each frame — axes freeze at their last drawn position. Camera snap (`csSetView_`) is already blocked by the SVG click listener gate; this fix ensures the visual also stops updating.

---

## Reference Toggle Button

**New element** in `cs-corner-{id}` div:

```html
<button id="cs-btn-ref-{fig_id_safe}"
        style="width:26px;height:26px;background:rgba(20,20,30,0.72);
               border:1px solid rgba(255,255,255,0.18);border-radius:5px;
               cursor:pointer;font-size:13px;line-height:1;color:#fff;
               display:flex;align-items:center;justify-content:center;"
        title="Toggle orientation reference">⊕</button>
```

**JS**:
- `var _refShown=false;` — reference starts hidden.
- SVG element starts with `style="...;display:none;"`.
- Button click handler (IIFE, same pattern as lock widget):
  ```js
  _refShown=!_refShown;
  var sv=document.getElementById("cs-svg-axes-{fig_id_safe}");
  if(sv)sv.style.display=_refShown?"block":"none";
  ```
- No lock gate on the toggle — user can always show/hide the reference widget.

---

## Layout: Bottom-Left Cluster

The `cs-corner-{id}` div is a `display:flex;align-items:center;gap:6px;` row. It is rendered when `show_orientation=True` OR `has_time`. Its children depend on which features are active:

| Child | Rendered when |
|-------|--------------|
| SVG `cs-svg-axes-{id}` (`display:none` initially) | `show_orientation=True` |
| `cs-btn-ref-{id}` reference toggle | `show_orientation=True` |
| `cs-btn-time-{id}` time button | `has_time=True` |
| `cs-btn-iso-{id}` iso cycle button | `show_orientation=True` |
| `cs-iso-flash-{id}` flash span | `show_orientation=True` |

Order in the flex row: SVG → ref-btn → time-btn → iso-btn → flash span (each rendered only if its condition is met).

**Right strip** (`cs-strip-{id}`) — now only contains the field button (`cs-btn-field-{id}`) when `has_fields`. If no fields, the strip div is not rendered.

---

## Timeseries Popup Repositioning

Change `cs-pop-time-{id}` CSS from:
```
position:fixed;right:38px;top:50%;transform:translateY(-50%);
```
to:
```
position:fixed;bottom:36px;left:4px;
```

Remove `transform:translateY(-50%)` (no longer needed). The popup opens above the bottom-left cluster. All other popup styles (`z-index`, background, border, padding) unchanged.

---

## HTML Assembly Order

```python
html_block = ""
if strip_btns:      # only field button now
    html_block += cs-strip div
html_block += lock_widget + lock_badge + field_pop + time_pop + corner_widget
```

`strip_btns` is now built only from `has_fields` (not `has_time`). The time button HTML is generated separately and embedded in `corner_widget`.

---

## `_controls_strip_snippet` Changes Summary

| Location | Change |
|----------|--------|
| `_drawAxes()` body | Add `if(_locked)return;` after `if(!_renderer||!_svg)return;` |
| `strip_btns` assembly | Remove time button from strip_btns |
| `corner_widget` HTML | Add ref toggle btn before time btn; add time btn (conditional); SVG starts `display:none` |
| `time_pop` CSS | `bottom:36px;left:4px` instead of `right:38px;top:50%;transform:...` |
| JS (orientation block) | Add `_refShown=false` var; add ref-toggle listener IIFE |

---

## Testing

**Existing tests to update:**
- `test_time_button_present_when_time_data` (in `TestControlsStripHtml`) — currently checks `cs-btn-time-` is in HTML (no location check). After this change it still appears in HTML (in the corner div), so the assertion may continue to pass. But verify it doesn't check for strip membership.
- Any test asserting `cs-btn-time-` is inside `cs-strip-` — rewrite to assert it is inside `cs-corner-` instead.
- Any test asserting the timeseries popup uses `right:38px` or `top:50%` — update to `bottom:36px` / `left:4px`.
- `test_strip_present_when_time_data` — if it exists, rewrite: strip only renders for field data, not time data.

**New tests to add:**
- `test_ref_toggle_button_present` — `cs-btn-ref-` in output when `show_orientation=True`; `⊕` in output.
- `test_ref_toggle_button_absent_when_orientation_hidden` — `cs-btn-ref-` absent when `show_orientation=False`.
- `test_svg_starts_hidden` — SVG element has `display:none` in initial HTML.
- `test_ref_toggle_js_present` — `_refShown` in JS output; `cs-btn-ref-` in JS block.
- `test_drawaxes_respects_lock` — `if(_locked)return;` appears inside `_drawAxes` function body (after the initial guard).
- `test_time_button_in_corner_not_strip` — when `has_time=True`: `cs-btn-time-` present in corner widget section; NOT in strip section.
- `test_time_popup_bottom_left` — `cs-pop-time-` CSS contains `bottom:36px` and `left:4px`; does NOT contain `right:38px`.
- `test_strip_has_no_time_button` — strip div does not contain `cs-btn-time-` even when `has_time=True`.
- `test_corner_rendered_when_has_time_only` — when `show_orientation=False` and `has_time=True`: corner div rendered; strip div not rendered.
