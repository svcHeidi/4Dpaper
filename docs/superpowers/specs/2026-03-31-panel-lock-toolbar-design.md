# Panel-Level Lock Toolbar — Design Spec
**Date:** 2026-03-31
**Status:** Approved

## Goal

Replace the per-subfigure 🔒 lock buttons with a single panel-level lock toolbar that appears above every sync-mode panel (`4d-panel`, `4d-timeseries`). Clicking the toolbar lock locks or unlocks all subfigures simultaneously. Non-synced standalone figures (`4d-image` in independent mode) are unaffected.

## Problem

The current lock button lives inside each subfigure's srcdoc iframe. Locking one subfigure saves its own `camera_<fig_id>_lock.json` and acknowledges only the source figure — siblings are never notified. The result: rotating a "locked" figure still syncs to unlocked siblings.

## Architecture

### Overview

Three targeted changes, all in existing files:

| File | Change |
|------|--------|
| `_extensions/4dpaper/4dpaper.py` | Inject lock toolbar in `generate_panel_html()` (sync mode only) |
| `_extensions/4dpaper/4dpaper.py` | Add two message listeners to subfigure JS (`4dpaper-lock-all`, `4dpaper-hide-lock-btn`) |
| No other files | `/camera-lock/<id>` endpoint already works for panel IDs |

### 1. Panel Lock Toolbar (in `generate_panel_html()`)

Injected only when `camera_mode == "sync"`. Positioned as a `<div>` directly above the figure grid inside the panel's outer container.

**HTML structure:**
```html
<div class="panel-lock-bar" id="plb-<panel_id_safe>">
  <button id="plb-btn-<panel_id_safe>">🔓</button>
  <span id="plb-label-<panel_id_safe>">Sync active</span>
</div>
```

**JS behaviour (inline, inside the panel HTML):**

- **On load**: GET `/camera-lock/<panel_id>` → restore lock state → broadcast `4dpaper-lock-all` to all child iframes → broadcast `4dpaper-hide-lock-btn` to all child iframes (hides per-figure buttons).
- **On button click**: toggle local state → POST `/camera-lock/<panel_id>` → broadcast `4dpaper-lock-all` to all child iframes.

Broadcast is a direct `iframe.contentWindow.postMessage(msg, "*")` loop over `document.querySelectorAll("iframe")` inside the panel container.

**Button states:**

| State | Button text | Label text |
|-------|-------------|------------|
| Unlocked | 🔓 | Sync active |
| Locked | 🔒 | Camera locked |

### 2. Subfigure JS — Two New Message Listeners

Added to the existing `window.addEventListener("message", ...)` handler inside each subfigure's generated HTML (the `_camera_sync_snippet` in `4dpaper.py`):

```javascript
if (e.data.type === "4dpaper-lock-all") {
    _setLocked(!!e.data.locked);
}
if (e.data.type === "4dpaper-hide-lock-btn") {
    var w = document.getElementById("cs-lock-widget-<fig_id_safe>");
    if (w) w.style.display = "none";
}
```

`_setLocked()` already handles all UI + interactor side effects (lock icon, shield overlay, disabling VTK interactor) — no changes needed there.

### 3. Scope Guard

`generate_panel_html()` is called only for `4d-panel` and `4d-timeseries` shortcodes with `camera_mode="sync"`. The toolbar injection is inside the `if camera_mode == "sync"` branch. Standalone `4d-image` figures never call this function, so their lock buttons are unaffected.

## State Transitions

```
Panel toolbar button clicked (unlock → lock)
  → _setPanelLocked(true)           # update toolbar UI
  → POST /camera-lock/<panel_id>    # persist
  → for each iframe:
      postMessage({type:"4dpaper-lock-all", locked:true})
  → subfigure receives message
      → _setLocked(true)            # per-figure UI + VTK interactor disabled
```

```
Page load / panel first render
  → GET /camera-lock/<panel_id>     # restore persisted state
  → _setPanelLocked(state.locked)   # restore toolbar UI
  → for each iframe:
      postMessage({type:"4dpaper-lock-all", locked:state.locked})
      postMessage({type:"4dpaper-hide-lock-btn"})
```

## Out of Scope

- Per-figure lock buttons on standalone `4d-image` figures — unchanged
- Field sync (already panel-level)
- Keyboard shortcut for lock toggle
- Visual indication on which individual subfigure triggered a rotation when locked (camera is blocked at `_sendCam` level — existing behaviour)
