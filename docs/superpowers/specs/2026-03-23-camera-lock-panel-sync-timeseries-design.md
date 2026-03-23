# Camera Lock, Panel Sync, and Timeseries Design

**Goal:** Three related camera-management features: (1) a per-figure padlock button that prevents accidental camera overwrites, (2) a `camera="sync"` mode for `4d-panel` that keeps all subfigure viewpoints in lock-step, and (3) a new `{{< 4d-timeseries >}}` shortcode that auto-generates a synced `N×1` panel from a single source at N time steps.

**Scope:** `4d-image`, `4d-panel`, and new `4d-timeseries` shortcodes. `4d-video` and `4d-pvsm` are out of scope for sync/lock.

**Tech stack:** Existing postMessage relay pattern, new Tornado endpoints in `camera_plugin.py`, Python `_camera_sync_snippet` additions, `re_relay` changes in `generate_panel_html`, new `parse_timeseries_shortcodes`, new `fourd_timeseries` Lua handler.

---

## Feature 1: Camera Lock

### Behaviour

A small padlock button (🔓/🔒) is overlaid in the **top-left corner** of every `4d-image` vtk.js iframe (opposite the existing camera badge at top-right).

- **Unlocked (default):** interactions save camera exactly as today.
- **Locked:** `sendCamera()` returns immediately — nothing is posted, no badge appears. The 3D view still rotates visually; only persistence is blocked.
- **Lock state persists** across page reloads via a new server endpoint.

### Message protocol (new types)

All use the existing postMessage relay in `shortcodes.lua`:

| Message (iframe → parent) | Meaning |
|---|---|
| `{type:"4dpaper-lock-query", fig_id}` | Fetch current lock state on load |
| `{type:"4dpaper-lock-toggle", fig_id, locked:bool}` | Save new lock state |

| Message (parent → iframe) | Meaning |
|---|---|
| `{type:"4dpaper-lock-state", fig_id, locked:bool}` | Response to query — sent to `e.source` |
| `{type:"4dpaper-lock-ack", fig_id, status:"ok"\|"error"}` | Response to toggle — sent to `e.source` |

When `window.parent === window` (direct view, no parent relay): `fetch()` both endpoints directly.

### Changes to `_camera_sync_snippet(fig_id)` in `4dpaper.py`

Add to the returned HTML+JS:

1. **Lock button element** (top-left, always visible):
   ```html
   <button id="lock-btn-{fig_id}" style="position:fixed;top:8px;left:8px;
     background:rgba(0,0,0,0.45);border:none;border-radius:4px;
     font-size:14px;cursor:pointer;padding:4px 6px;z-index:9999;
     color:#fff;opacity:0.7;" title="Lock camera">🔓</button>
   ```

2. **JS additions** (inside the IIFE, before `waitRenderer`):
   ```js
   var locked = false;
   var lockBtn = document.getElementById("lock-btn-{fig_id}");

   function setLocked(v) {
     locked = v;
     lockBtn.textContent = v ? "🔒" : "🔓";
     lockBtn.style.opacity = v ? "1" : "0.7";
   }

   // Initialize lock state from server
   if (window.parent !== window) {
     parent.postMessage({type:"4dpaper-lock-query", fig_id:FIG_ID}, "*");
   } else {
     fetch("/camera-lock/" + FIG_ID)
       .then(function(r){ return r.json(); })
       .then(function(d){ setLocked(!!d.locked); })
       .catch(function(){});
   }

   lockBtn.addEventListener("click", function() {
     var newVal = !locked;
     var expected = newVal;  // capture at toggle time; `locked` may change before ack arrives
     setLocked(newVal); // optimistic update
     if (window.parent !== window) {
       parent.postMessage({type:"4dpaper-lock-toggle", fig_id:FIG_ID, locked:newVal}, "*");
     } else {
       fetch("/camera-lock/" + FIG_ID, {
         method:"POST", headers:{"Content-Type":"application/json"},
         body:JSON.stringify({locked:newVal})
       }).catch(function(){ setLocked(!expected); }); // revert on error
     }
   });
   ```

3. **Extend the existing `window.addEventListener("message", ...)` handler** (add inside the existing listener, alongside the camera-ack branch):
   ```js
   if (e.data.type === "4dpaper-lock-state" && e.data.fig_id === FIG_ID) {
     setLocked(!!e.data.locked);
   }
   if (e.data.type === "4dpaper-lock-ack" && e.data.fig_id === FIG_ID) {
     // NOTE: use e.data.expected (not local `locked`) to avoid stale state on rapid toggles.
     // The relay path cannot carry `expected` — on error, set to opposite of the acked locked value.
     // For the relay path, we accept the minor race: reverting on a fast double-click may land
     // in the wrong state. To eliminate it entirely, track per-toggle sequence numbers (future).
     if (e.data.status !== "ok") setLocked(!locked); // best-effort revert
   }
   ```

4. **In `sendCamera()`** — add at the very top:
   ```js
   function sendCamera(renderer) {
     if (locked) return;   // ← new guard
     clearTimeout(timer);
     // ... rest unchanged ...
   }
   ```

### New backend in `camera_plugin.py`

```python
class CameraLockHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def options(self, fig_id):
        self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def get(self, fig_id):
        if not _SAFE_FIG_ID.fullmatch(fig_id):
            self.set_status(400); self.write({"status": "error"}); return
        lock_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}_lock.json"
        if lock_path.exists():
            self.write(json.loads(lock_path.read_text()))
        else:
            self.write({"locked": False})

    def post(self, fig_id):
        if not _SAFE_FIG_ID.fullmatch(fig_id):
            self.set_status(400); self.write({"status": "error"}); return
        body = json.loads(self.request.body)
        lock_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}_lock.json"
        lock_path.write_text(json.dumps({"locked": bool(body.get("locked", False))}))
        self.write({"status": "ok"})

ROUTES = [
    (r"/camera/(?P<fig_id>[^/]+)", CameraHandler),
    (r"/camera-lock/(?P<fig_id>[^/]+)", CameraLockHandler),   # new
]
```

### Updated `4dpaper-camera` handler in `shortcodes.lua` `_RELAY_SCRIPT`

The existing `4dpaper-camera` handler sends `4dpaper-camera-ack` only to `_f2.contentWindow` (the camera overlay iframe). This must also send to `e.source` so that:
- Main-paper figure iframes receive their badge ack (existing gap, fixed here)
- Sync panel composite iframes receive the ack so they can re-relay it to children

**Replace** the existing camera handler:
```js
} else if (e.data.type === "4dpaper-camera") {
  var figId = e.data.fig_id;
  var _f2 = document.getElementById('fourd-cam-iframe');
  var _ss2 = document.getElementById('fourd-cam-sttxt');
  fetch('/camera/' + figId, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(e.data.camera)
  }).then(function(r) {
    if (_ss2) {
      if (r.ok) { _ss2.textContent = '✓ Camera saved — click "Rebuild HTML" to apply'; _ss2.style.color = '#4caf50'; }
      else       { _ss2.textContent = '✗ Save failed (server error)'; _ss2.style.color = '#f44336'; }
    }
    var ack = {type: '4dpaper-camera-ack', fig_id: figId, status: r.ok ? 'ok' : 'error'};
    // Send to camera overlay iframe (for badge when using Camera Setup modal)
    if (_f2 && _f2.contentWindow) _f2.contentWindow.postMessage(ack, '*');
    // Also send back to source (for badge in main paper or sync panel re-relay)
    if (e.source && e.source !== (_f2 && _f2.contentWindow)) e.source.postMessage(ack, '*');
  }).catch(function() {
    if (_ss2) { _ss2.textContent = '✗ Save failed (network error)'; _ss2.style.color = '#f44336'; }
    var ack = {type: '4dpaper-camera-ack', fig_id: figId, status: 'error'};
    if (_f2 && _f2.contentWindow) _f2.contentWindow.postMessage(ack, '*');
    if (e.source && e.source !== (_f2 && _f2.contentWindow)) e.source.postMessage(ack, '*');
  });
```

**Add** two new `else if` branches for lock:
```js
} else if (e.data.type === "4dpaper-lock-query") {
  var lockFigId = e.data.fig_id;
  fetch("/camera-lock/" + lockFigId)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (e.source) e.source.postMessage(
        {type: "4dpaper-lock-state", fig_id: lockFigId, locked: !!d.locked}, "*");
    }).catch(function() {
      if (e.source) e.source.postMessage(
        {type: "4dpaper-lock-state", fig_id: lockFigId, locked: false}, "*");
    });

} else if (e.data.type === "4dpaper-lock-toggle") {
  var lockFigId2 = e.data.fig_id;
  fetch("/camera-lock/" + lockFigId2, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({locked: !!e.data.locked})
  }).then(function(r) {
    if (e.source) e.source.postMessage(
      {type: "4dpaper-lock-ack", fig_id: lockFigId2, status: r.ok ? "ok" : "error"}, "*");
  }).catch(function() {
    if (e.source) e.source.postMessage(
      {type: "4dpaper-lock-ack", fig_id: lockFigId2, status: "error"}, "*");
  });
}
```

---

## Feature 2: Panel Camera Sync Mode

### Shortcode

```
{{< 4d-panel camera="sync" id="panel-vm" layout="2x1" ... >}}
```

`camera` defaults to `"independent"`. Any value other than `"sync"` is treated as `"independent"`.

### Parser change — `parse_panel_shortcodes()`

Add `"camera_mode": kwargs.get("camera", "independent")` to the returned dict.

### `generate_panel_html()` — sync re_relay

For `camera_mode == "sync"`, generate a different `re_relay` script (Python f-string with `{panel_id}` substituted):

```js
<script>
var PANEL_ID = "{panel_id}";
window.addEventListener("message", function(e) {
  if (!e.data) return;
  if (e.data.type === "4dpaper-camera") {
    // Override fig_id → panel ID so camera saves to camera_<panel_id>.json
    var msg = Object.assign({}, e.data, {fig_id: PANEL_ID});
    top.postMessage(msg, "*");
    // Broadcast visual-sync to all children (no save loop — apply does not trigger pointerup)
    var iframes = document.querySelectorAll("iframe");
    for (var i = 0; i < iframes.length; i++) {
      iframes[i].contentWindow.postMessage(
        {type: "4dpaper-camera-apply", camera: e.data.camera}, "*");
    }
  }
  if (e.data.type === "4dpaper-camera-ack") {
    // Rewrite fig_id to "*" so ALL subfigure _camera_sync_snippets show the badge.
    // (All subfigures share the same camera in sync mode.)
    var camAck = Object.assign({}, e.data, {fig_id: "*"});
    var iframes2 = document.querySelectorAll("iframe");
    for (var j = 0; j < iframes2.length; j++) {
      iframes2[j].contentWindow.postMessage(camAck, "*");
    }
  }
  if (e.data.type === "4dpaper-field-ack") {
    // Keep original fig_id — field selection is per-subfigure; only the sender's badge updates.
    var iframes3 = document.querySelectorAll("iframe");
    for (var k = 0; k < iframes3.length; k++) {
      iframes3[k].contentWindow.postMessage(e.data, "*");
    }
  }
  if (e.data.type === "4dpaper-field-update") { top.postMessage(e.data, "*"); }
  // Lock messages: pass up to top, pass down to children
  if (e.data.type === "4dpaper-lock-query" || e.data.type === "4dpaper-lock-toggle") {
    top.postMessage(e.data, "*");
  }
  if (e.data.type === "4dpaper-lock-state" || e.data.type === "4dpaper-lock-ack") {
    var iframes4 = document.querySelectorAll("iframe");
    for (var l = 0; l < iframes4.length; l++) {
      iframes4[l].contentWindow.postMessage(e.data, "*");
    }
  }
});
</script>
```

**Independent mode `re_relay`** — independent panels are rendered as inline subfigure iframes in Lua (no composite iframe). Lock messages from subfigures post **directly** to the Quarto page's `_RELAY_SCRIPT` (no intermediate re_relay hop). Therefore the independent re_relay in the composite HTML needs no lock pass-through for the normal paper rendering path. However, for consistency when the composite HTML is viewed standalone (direct URL), add the same lock pass-through to the independent re_relay:

```js
// Lock pass-through (standalone composite HTML path only)
if (e.data.type === "4dpaper-lock-query" || e.data.type === "4dpaper-lock-toggle") {
  top.postMessage(e.data, "*");
}
if (e.data.type === "4dpaper-lock-state" || e.data.type === "4dpaper-lock-ack") {
  var iframes = document.querySelectorAll("iframe");
  for (var k = 0; k < iframes.length; k++) {
    iframes[k].contentWindow.postMessage(e.data, "*");
  }
}
```

**`_field_sync_snippet` ack filter**: no change needed. `4dpaper-field-ack` in sync re_relay keeps the original `fig_id` (see above), so the existing `if (e.data.fig_id !== FIG_ID) return;` check in `_field_sync_snippet` correctly routes field acks to the right subfigure.

**`_camera_sync_snippet` ack filter** — change the existing ack check from:
```js
if (e.data.fig_id !== FIG_ID) return;
```
to:
```js
if (e.data.fig_id !== FIG_ID && e.data.fig_id !== "*") return;
```
This allows the sync panel's wildcard ack to reach subfigure badges while still filtering unrelated acks in independent-panel and standalone contexts.

### `_camera_sync_snippet()` — apply incoming camera (all figures)

Add a `4dpaper-camera-apply` listener **inside the `waitRenderer` callback** (where `renderer` and `window.renderWindow` are in scope):

```js
waitRenderer(function(renderer) {
  // ... existing pointerup/mouseup/touchend listeners unchanged ...

  // NEW: apply camera from sync panel without triggering a save
  window.addEventListener("message", function(e) {
    if (!e.data || e.data.type !== "4dpaper-camera-apply") return;
    var cam = e.data.camera;
    if (!cam) return;
    var c = renderer.getActiveCamera();
    if (cam.position)            c.setPosition(cam.position[0], cam.position[1], cam.position[2]);
    if (cam.focal_point)         c.setFocalPoint(cam.focal_point[0], cam.focal_point[1], cam.focal_point[2]);
    if (cam.view_up)             c.setViewUp(cam.view_up[0], cam.view_up[1], cam.view_up[2]);
    if (cam.parallel_scale != null) c.setParallelScale(cam.parallel_scale);
    if (cam.parallel_projection != null) c.setParallelProjection(!!cam.parallel_projection);
    window.renderWindow.render();
  });
});
```

`4dpaper-camera-apply` carries no `fig_id` — it applies to whichever figure receives it. Loop-safety: applying a camera does not trigger pointer events, so `sendCamera` is never re-called.

### `generate_png_figure()` — new `camera_fig_id` parameter

```python
def generate_png_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
    camera_fig_id: str | None = None,   # NEW: override camera lookup ID
    background: str = "white",
    axis_color: str = "black",
    cmap: str = "coolwarm",
) -> None:
```

Change camera lookup in body:
```python
_cam_id = camera_fig_id or fig_id
camera_path = (_project_root / "state" / f"camera_{_cam_id}.json" if _cam_id else None)
```

**Standalone `4d-image` callsite in `main()`** (line ~1676): unchanged — `camera_fig_id` defaults to `None` and falls back to `fig_id`, so no update required.

**`generate_html_figure`**: unchanged — it does not read camera JSON at all (camera is applied in the vtk.js viewer at interaction time). No `camera_fig_id` param needed.

### `generate_panel_png()` — use panel camera for sync mode

```python
def generate_panel_png(panel: dict, figures_dir: Path) -> None:
    ...
    camera_mode = panel.get("camera_mode", "independent")
    for sub in panel["subfigures"]:
        src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]
        out = figures_dir / f"{sub['id']}.png"
        cam_id = panel["id"] if camera_mode == "sync" else sub["id"]
        # Style params: panels have no style config; rely on generate_png_figure defaults.
        generate_png_figure(src, sub["field"], sub["time"], out,
                            fig_id=sub["id"], camera_fig_id=cam_id)
```

### Cache invalidation for sync panels in `main()`

The existing panel PNG loop uses a manual `max_dep_mtime` comparison (not `is_cache_valid`). The relevant section iterates subfigures and skips re-generation if the output PNG is newer than all deps. Replace the per-subfigure camera path logic:

```python
panel_id = panel["id"]
camera_mode = panel.get("camera_mode", "independent")

# For sync panels: one shared camera file for all subfigures.
# For independent panels: each subfigure has its own camera file.
if camera_mode == "sync":
    shared_cam = _project_root / "state" / f"camera_{panel_id}.json"

for sub in panel["subfigures"]:
    out = figures_dir / f"{sub['id']}.png"
    src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]

    if out.exists():
        dep_mtimes = [src.stat().st_mtime, py_file_mtime]
        if camera_mode == "sync":
            if shared_cam.exists():
                dep_mtimes.append(shared_cam.stat().st_mtime)
        else:
            sub_cam = _project_root / "state" / f"camera_{sub['id']}.json"
            if sub_cam.exists():
                dep_mtimes.append(sub_cam.stat().st_mtime)
        if out.stat().st_mtime >= max(dep_mtimes):
            continue  # cache valid — skip this subfigure

    generate_png_figure(...)  # as before
```

### `shortcodes.lua` — updated `fourd_panel`

`fourd_panel` branches on `camera` kwarg:

- **`camera="sync"`** (or any explicit sync value): read `state/figures/<id>.html` (the Python-generated composite HTML containing subfigure iframes + sync re_relay) and embed as a **single iframe**. The composite handles all sync logic internally.
- **`camera="independent"` (default, omitted)**: existing behaviour — build a grid of subfigure iframes inline. Lock messages flow directly to `_RELAY_SCRIPT` without needing re_relay.

```lua
local function fourd_panel(args, kwargs)
  local id          = pandoc.utils.stringify(kwargs["id"]     or pandoc.Str(""))
  local caption     = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))
  local height      = pandoc.utils.stringify(kwargs["height"]  or pandoc.Str("500px"))
  local camera_mode = pandoc.utils.stringify(kwargs["camera"]  or pandoc.Str("independent"))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-panel: missing required attribute <code>id</code></div>')
  end

  if quarto.doc.isFormat("html") then
    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end

    if camera_mode == "sync" then
      -- Sync mode: embed composite HTML as single iframe so sync re_relay executes.
      local composite_path = "state/figures/" .. id .. ".html"
      local f = io.open(composite_path, "r")
      if not f then
        return pandoc.RawBlock("html",
          '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;">' ..
          '⚠ 4D Panel <code>' .. id .. '</code> not yet rendered — ' ..
          'click <strong>Rebuild HTML</strong> in the dashboard.</div>')
      end
      local composite_iframe
      if _app_mode then
        f:close()
        composite_iframe = '<iframe src="/state/figures/' .. id .. '.html" ' ..
                           'style="width:100%;height:' .. height .. ';border:none;" frameborder="0"></iframe>'
      else
        local content = f:read("*all"); f:close()
        local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")
        composite_iframe = '<iframe srcdoc="' .. escaped .. '" ' ..
                           'style="width:100%;height:' .. height .. ';border:none;" frameborder="0"></iframe>'
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        composite_iframe .. '\n' ..
        (caption ~= "" and
          '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
          or "") ..
        '</figure>\n' .. relay_script)
    else
      -- Independent mode: existing inline-subfigure grid (existing implementation unchanged).
      -- Build N-cell grid by reading id1, id2, ... kwargs until absent.
      -- (existing fourd_panel body here — see current shortcodes.lua for this branch)
    end

  else
    -- PDF: single composite PNG (existing logic unchanged)
    -- state/figures/<id>.png — written by generate_panel_png
  end
end
```

The `-- (existing fourd_panel body here)` placeholder means: **keep the current `fourd_panel` independent-mode Lua code exactly as-is** for the independent branch. Only add the `camera_mode == "sync"` branch above it, guarded by the `if camera_mode == "sync"` check.

---

## Feature 3: Timeseries Shortcode

### Shortcode syntax

```
{{< 4d-timeseries src="..." field="Vm" id="ts-vm" steps="4" caption="..." >}}
```

Or explicit times:
```
{{< 4d-timeseries src="..." field="Vm" id="ts-vm" times="first,3,7,last" caption="..." >}}
```

`steps` and `times` are mutually exclusive; `times` takes precedence if both given. Default: `steps="4"`.

### `parse_timeseries_shortcodes(text) -> list[dict]`

Returns raw (unexpanded) dicts — step expansion happens in `main()` after the simulation is loaded:

```python
{
    "id":          kwargs["id"],
    "layout":      None,          # set by main() after step expansion
    "height":      kwargs.get("height", "400px"),
    "caption":     kwargs.get("caption", ""),
    "camera_mode": "sync",
    "timeseries":  True,
    "src":         kwargs["src"],
    "field":       kwargs.get("field", ""),
    "steps":       kwargs.get("steps", "4"),   # used if times not given
    "times":       kwargs.get("times", ""),    # takes precedence over steps
    "subfigures":  [],                          # filled by main()
}
```

### `_expand_timeseries_steps(ts: dict, n_steps: int) -> list[int]`

```python
def _expand_timeseries_steps(ts: dict, n_steps: int) -> list[int]:
    """Expand steps/times string to list of integer step indices.

    times= takes precedence. If all tokens are invalid, falls back to steps= logic.
    steps="1" is treated as steps="2" (minimum useful timeseries).
    """
    if ts["times"]:
        result = []
        for tok in ts["times"].split(","):
            tok = tok.strip()
            if tok == "first":
                result.append(0)
            elif tok == "last":
                result.append(max(0, n_steps - 1))
            else:
                try:
                    result.append(max(0, min(int(tok), n_steps - 1)))
                except ValueError:
                    pass  # skip invalid tokens
        if result:
            return result
        # All tokens invalid — fall through to steps= logic
    if n_steps <= 1:
        print(f"[4dpaper] WARNING: timeseries '{ts['id']}' source has only {n_steps} step(s) — generating single frame.", file=sys.stderr)
        return [0]
    N = max(2, int(ts.get("steps", "4")))
    return [round(i * (n_steps - 1) / (N - 1)) for i in range(N)]
```

**Note on double-load:** `main()` calls `SimulationData(src).load().n_steps` once for step expansion per timeseries shortcode. `generate_html_figure` and `generate_png_figure` also call `SimulationData(src).load()` internally per subfigure. This means the simulation is loaded `1 + N` times per timeseries shortcode. `SimulationData` does not cache across calls. This is acceptable for typical use (simulations are small-to-medium and already on local disk); a future optimisation could pass a pre-loaded sim object to the generators.

### Step expansion in `main()`

Timeseries shortcodes are collected alongside panels and expanded before the panel processing loop:

```python
# Collect all shortcode types
figures   = parse_shortcodes(text)
videos    = parse_video_shortcodes(text)
panels    = parse_panel_shortcodes(text)
pvsm_figs = parse_pvsm_shortcodes(text)
ts_raw    = parse_timeseries_shortcodes(text)

if not any([figures, videos, panels, pvsm_figs, ts_raw]):
    print("[4dpaper] No shortcodes found.", file=sys.stderr)
    return

# Expand timeseries into panel-compatible dicts
for ts in ts_raw:
    src = Path(ts["src"]) if Path(ts["src"]).is_absolute() else _project_root / ts["src"]
    sim = SimulationData(str(src)).load()
    step_indices = _expand_timeseries_steps(ts, sim.n_steps)
    ts["subfigures"] = [
        {"src": ts["src"], "id": f"{ts['id']}-{i}",
         "field": ts["field"], "time": str(idx), "fields": ""}
        for i, idx in enumerate(step_indices)
    ]
    ts["layout"] = f"{len(step_indices)}x1"
    panels.append(ts)   # merged into panels list — same processing loop
```

After merging, timeseries dicts flow through `generate_panel_html` / `generate_panel_png` exactly as `4d-panel` dicts do.

### Lua rendering strategy for sync panels and timeseries

The Python-generated composite HTML (`state/figures/<panel_id>.html`) contains:
- All subfigure iframes
- The sync `re_relay` script that rewrites `fig_id → panel_id` and broadcasts `4dpaper-camera-apply`

For this relay to execute, Lua must render the **composite HTML as a single iframe**, not render subfigure iframes individually.

**Rule:**
- `camera_mode == "independent"` (default for `4d-panel`): Lua renders subfigure iframes directly inline. Composite HTML is not used. Lock messages are forwarded by the independent re_relay.
- `camera_mode == "sync"` (explicit on `4d-panel`) or `fourd_timeseries` (always sync): Lua renders a **single iframe** pointing to/embedding `state/figures/<id>.html` (the composite HTML). The composite's sync `re_relay` handles all camera coordination internally.

For `fourd_timeseries`, this means it does **not** probe for `<id>-0.html`, `<id>-1.html` directly. Instead it probes for `state/figures/<id>.html` (the composite) and embeds it as one full-height iframe. The placeholder "not yet rendered" message fires if the composite is absent.

### `shortcodes.lua` — `fourd_timeseries`

`fourd_timeseries` looks for the Python-generated composite HTML (`state/figures/<id>.html`) and embeds it as a **single iframe**. It does not probe for individual subfigure files.

Unlike `fourd_panel` (which knows `id1`, `id2`, ... from explicit kwargs), `fourd_timeseries` has no explicit subfigure list, making the composite-iframe approach the only viable Lua path.

```lua
local function fourd_timeseries(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))
  local height  = pandoc.utils.stringify(kwargs["height"]  or pandoc.Str("400px"))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-timeseries: missing required attribute <code>id</code></div>')
  end

  if quarto.doc.isFormat("html") then
    -- Timeseries is always sync — embed the Python-generated composite HTML as one iframe.
    -- The composite contains subfigure iframes + the sync re_relay script.
    local composite_path = "state/figures/" .. id .. ".html"
    local f = io.open(composite_path, "r")

    if not f then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;">' ..
        '⚠ 4D Timeseries <code>' .. id .. '</code> not yet rendered — ' ..
        'click <strong>Rebuild HTML</strong> in the dashboard.</div>')
    end

    local composite_iframe
    if _app_mode then
      f:close()
      composite_iframe = '<iframe src="/state/figures/' .. id .. '.html" ' ..
                         'style="width:100%;height:' .. height .. ';border:none;" frameborder="0"></iframe>'
    else
      local content = f:read("*all"); f:close()
      local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")
      composite_iframe = '<iframe srcdoc="' .. escaped .. '" ' ..
                         'style="width:100%;height:' .. height .. ';border:none;" frameborder="0"></iframe>'
    end

    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end
    return pandoc.RawBlock("html",
      '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
      composite_iframe .. '\n' ..
      (caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
        or "") ..
      '</figure>\n' .. relay_script)

  else
    -- PDF: single composite PNG at state/figures/<id>.png
    local fig_path = "state/figures/" .. id .. ".png"
    local f = io.open(fig_path, "r")
    if f then
      f:close()
      local img = pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, {width = "100%"}))
      return pandoc.Para({img})
    else
      return pandoc.Para({
        pandoc.Str("[Timeseries "), pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
  end
end
```

Registered: `["4d-timeseries"] = fourd_timeseries`.

---

## Files Changed

| File | Change |
|------|--------|
| `_extensions/4dpaper/4dpaper.py` | `_camera_sync_snippet` (lock button + apply handler), `generate_png_figure` (`camera_fig_id` param), `generate_panel_html` (sync `re_relay`), `generate_panel_png` (`camera_fig_id` for sync), `parse_panel_shortcodes` (`camera_mode`), `parse_timeseries_shortcodes` (new), `_expand_timeseries_steps` (new), `main()` (timeseries expansion + merged into panels) |
| `_extensions/4dpaper/shortcodes.lua` | `_RELAY_SCRIPT` (camera ack routing fix + lock-query/toggle handlers), `fourd_panel` (sync mode → single composite iframe; independent mode keeps existing subfigure iframes but adds lock pass-through to re_relay), new `fourd_timeseries` (single composite iframe always), registered in return table |
| `dashboard/camera_plugin.py` | `CameraLockHandler` (new), `ROUTES` updated |
| `tests/test_camera_lock.py` | New: `CameraLockHandler` GET/POST, lock JS snippet shape, `sendCamera` guard |
| `tests/test_panel_sync.py` | New: `parse_panel_shortcodes` camera_mode, `generate_panel_png` camera routing, `re_relay` sync logic |
| `tests/test_timeseries.py` | New: `parse_timeseries_shortcodes`, `_expand_timeseries_steps`, `main()` expansion + merge |

---

## Error Handling

- **Lock endpoint unavailable** (dashboard not running): `fetch()` failure is silently caught; button stays in default unlocked state.
- **Unknown `camera` value on `4d-panel`**: treated as `"independent"` (no warning).
- **`steps="1"`**: if `n_steps > 1`, treated as `steps="2"` via `max(2, ...)`. If `n_steps <= 1`, returns `[0]` (single frame, warning logged).
- **Source with 1 step** (`n_steps <= 1`): `_expand_timeseries_steps` warns and returns `[0]` — generates a single-frame panel rather than crashing.
- **`times` with all-invalid tokens**: falls through to `steps=` logic (not a silent `[0]`).
- **Panel sync camera file missing** (`camera_<panel_id>.json` not found): isometric view fallback for all subfigures.
- **Timeseries with zero discovered files in Lua**: renders a "not yet rendered" placeholder, same pattern as `fourd_panel`.

---

## Out of Scope

- Camera lock for `4d-video` and `4d-pvsm`
- `camera="sync"` for nested panels
- Timeseries with multiple fields per step (use `4d-panel` manually)
- `SimulationData` cross-call caching (future optimisation)
