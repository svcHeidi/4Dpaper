# Camera Lock, Panel Sync, and Timeseries Design

**Goal:** Three related camera-management features: (1) a per-figure padlock button that prevents accidental camera overwrites, (2) a `camera="sync"` mode for `4d-panel` that keeps all subfigure viewpoints in lock-step, and (3) a new `{{< 4d-timeseries >}}` shortcode that auto-generates a synced `N×1` panel from a single source at N time steps.

**Scope:** `4d-image`, `4d-panel`, and new `4d-timeseries` shortcodes. `4d-video` and `4d-pvsm` are out of scope for sync/lock (camera sync already works for `4d-image`; `4d-video` camera is separate).

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
| `{type:"4dpaper-lock-state", fig_id, locked:bool}` | Response to query |
| `{type:"4dpaper-lock-ack", fig_id, status:"ok"\|"error"}` | Response to toggle |

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

2. **JS additions** (inside the IIFE):
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

   // Listen for lock state messages from parent
   window.addEventListener("message", function(e) {
     if (!e.data) return;
     if (e.data.type === "4dpaper-lock-state" && e.data.fig_id === FIG_ID) {
       setLocked(!!e.data.locked);
     }
     if (e.data.type === "4dpaper-lock-ack" && e.data.fig_id === FIG_ID) {
       // button already updated optimistically; error revert if needed
       if (e.data.status !== "ok") setLocked(!locked);
     }
     // ... existing camera-ack handler unchanged ...
   });

   lockBtn.addEventListener("click", function() {
     var newVal = !locked;
     setLocked(newVal); // optimistic update
     if (window.parent !== window) {
       parent.postMessage({type:"4dpaper-lock-toggle", fig_id:FIG_ID, locked:newVal}, "*");
     } else {
       fetch("/camera-lock/" + FIG_ID, {
         method:"POST", headers:{"Content-Type":"application/json"},
         body:JSON.stringify({locked:newVal})
       }).catch(function(){ setLocked(!newVal); }); // revert on error
     }
   });
   ```

3. **In `sendCamera()`** — add at the very top:
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
            self.set_status(400); self.write({"status":"error"}); return
        lock_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}_lock.json"
        if lock_path.exists():
            self.write(json.loads(lock_path.read_text()))
        else:
            self.write({"locked": False})

    def post(self, fig_id):
        if not _SAFE_FIG_ID.fullmatch(fig_id):
            self.set_status(400); self.write({"status":"error"}); return
        body = json.loads(self.request.body)
        lock_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}_lock.json"
        lock_path.write_text(json.dumps({"locked": bool(body.get("locked", False))}))
        self.write({"status": "ok"})

ROUTES = [
    (r"/camera/(?P<fig_id>[^/]+)", CameraHandler),
    (r"/camera-lock/(?P<fig_id>[^/]+)", CameraLockHandler),   # new
]
```

### New relay handlers in `shortcodes.lua` `_RELAY_SCRIPT`

Add two new `else if` branches inside the `window.addEventListener("message", ...)` handler:

```js
} else if (e.data.type === "4dpaper-lock-query") {
  var lockFigId = e.data.fig_id;
  fetch("/camera-lock/" + lockFigId)
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(e.source) e.source.postMessage(
        {type:"4dpaper-lock-state", fig_id:lockFigId, locked:!!d.locked}, "*");
    }).catch(function(){
      if(e.source) e.source.postMessage(
        {type:"4dpaper-lock-state", fig_id:lockFigId, locked:false}, "*");
    });

} else if (e.data.type === "4dpaper-lock-toggle") {
  var lockFigId2 = e.data.fig_id;
  fetch("/camera-lock/" + lockFigId2, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({locked:!!e.data.locked})
  }).then(function(r){
    if(e.source) e.source.postMessage(
      {type:"4dpaper-lock-ack", fig_id:lockFigId2, status:r.ok?"ok":"error"}, "*");
  }).catch(function(){
    if(e.source) e.source.postMessage(
      {type:"4dpaper-lock-ack", fig_id:lockFigId2, status:"error"}, "*");
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

Add `"camera_mode": kwargs.get("camera", "independent")` to the returned dict. Valid values: `"sync"`, `"independent"`.

### `generate_panel_html()` — sync re_relay

`generate_panel_html` receives the panel dict. For `camera_mode == "sync"`, generate a different `re_relay` script that:

1. Embeds `var PANEL_ID = "<panel_id>";`
2. On `4dpaper-camera` from any child:
   - **Overrides** `e.data.fig_id` with `PANEL_ID` before forwarding UP (saves to `camera_<panel_id>.json`)
   - Broadcasts `{type:"4dpaper-camera-apply", camera:e.data.camera}` to **all** child iframes (for visual sync — no fig_id needed since they apply without saving)
3. On `4dpaper-camera-ack` from parent: relay DOWN to all children as today.

```js
// sync re_relay (Python f-string, panel_id substituted):
<script>
var PANEL_ID = "{panel_id}";
var SYNC_MODE = true;
window.addEventListener("message", function(e) {
  if (!e.data) return;
  if (e.data.type === "4dpaper-camera") {
    // Forward up with panel ID (not subfigure ID)
    var msg = Object.assign({}, e.data, {fig_id: PANEL_ID});
    top.postMessage(msg, "*");
    // Broadcast apply to all children (visual sync, no save loop)
    var iframes = document.querySelectorAll("iframe");
    for (var i = 0; i < iframes.length; i++) {
      iframes[i].contentWindow.postMessage(
        {type:"4dpaper-camera-apply", camera:e.data.camera}, "*");
    }
  }
  if (e.data.type === "4dpaper-camera-ack" || e.data.type === "4dpaper-field-ack") {
    var iframes2 = document.querySelectorAll("iframe");
    for (var j = 0; j < iframes2.length; j++) {
      iframes2[j].contentWindow.postMessage(e.data, "*");
    }
  }
  if (e.data.type === "4dpaper-field-update") { top.postMessage(e.data, "*"); }
});
</script>
```

Independent mode keeps the existing `re_relay` unchanged.

### `_camera_sync_snippet()` — apply incoming camera (all figures)

Add a new message handler inside `waitRenderer` callback for `4dpaper-camera-apply`:

```js
window.addEventListener("message", function(e) {
  if (!e.data || e.data.type !== "4dpaper-camera-apply") return;
  // Apply camera from sync panel without triggering a save
  var cam = e.data.camera;
  if (!cam) return;
  var c = renderer.getActiveCamera();
  if (cam.position)   c.setPosition(cam.position[0], cam.position[1], cam.position[2]);
  if (cam.focal_point) c.setFocalPoint(cam.focal_point[0], cam.focal_point[1], cam.focal_point[2]);
  if (cam.view_up)    c.setViewUp(cam.view_up[0], cam.view_up[1], cam.view_up[2]);
  if (cam.parallel_scale != null) c.setParallelScale(cam.parallel_scale);
  if (cam.parallel_projection != null) c.setParallelProjection(!!cam.parallel_projection);
  window.renderWindow.render();
});
```

This handler must be registered **inside** `waitRenderer` (needs `renderer` and `window.renderWindow` in scope).

### `generate_png_figure()` — new `camera_fig_id` parameter

```python
def generate_png_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
    camera_fig_id: str | None = None,   # NEW: if set, read camera from this ID
    background: str = "white",
    axis_color: str = "black",
    cmap: str = "coolwarm",
) -> None:
```

Inside the body, change camera lookup:
```python
# was: camera_path = (_project_root / "state" / f"camera_{fig_id}.json" if fig_id else None)
_cam_id = camera_fig_id or fig_id
camera_path = (_project_root / "state" / f"camera_{_cam_id}.json" if _cam_id else None)
```

### `generate_panel_png()` — use panel camera for sync mode

```python
def generate_panel_png(panel: dict, figures_dir: Path) -> None:
    ...
    camera_mode = panel.get("camera_mode", "independent")
    for sub in panel["subfigures"]:
        src = ...
        out = figures_dir / f"{sub['id']}.png"
        cam_id = panel["id"] if camera_mode == "sync" else sub["id"]
        generate_png_figure(src, sub["field"], sub["time"], out,
                            fig_id=sub["id"], camera_fig_id=cam_id, ...)
```

### Cache invalidation for sync panels

In `main()`, for sync panels, the camera dep is `camera_<panel_id>.json` (shared). The existing per-subfigure camera check is replaced with a single panel-level camera path when `camera_mode == "sync"`.

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

`steps` and `times` are mutually exclusive; `steps` takes precedence if both given. Default: `steps="4"`.

### `parse_timeseries_shortcodes(text) -> list[dict]`

Returns panel-compatible dicts:

```python
def parse_timeseries_shortcodes(text: str) -> list[dict]:
    """
    Parse {{< 4d-timeseries >}} shortcodes.

    Expands to a panel dict with camera_mode="sync", layout="Nx1", and
    auto-generated subfigures ts-vm-0 ... ts-vm-(N-1).

    Time steps resolved:
    - steps="N"  → [round(i*(total-1)/(N-1)) for i in range(N)]
    - times="first,3,7,last" → parsed token by token
      "first"→0, "last"→(total-1), integers as-is, clamped to [0, total-1]
    """
```

**Note:** Actual step count is resolved in `main()` when the simulation is loaded, not at parse time. `parse_timeseries_shortcodes` stores `steps` and `times` strings in the dict; `main()` expands them after loading the simulation.

Returned dict structure:
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
    "times":       kwargs.get("times", ""),    # explicit time spec
    "subfigures":  [],                          # filled by main()
}
```

### Step expansion in `main()`

For each timeseries shortcode:
1. Load simulation to get `n_steps`
2. Expand `steps` or `times` string into a list of integer step indices
3. Generate subfigures list: `[{"src":..., "id":f"{ts_id}-{i}", "field":..., "time":str(idx), "fields":""}]`
4. Set `panel["layout"] = f"{len(subfigures)}x1"`
5. Pass expanded panel dict into `generate_panel_html` / `generate_panel_png` (same as `4d-panel`)

```python
def _expand_timeseries_steps(ts: dict, n_steps: int) -> list[int]:
    """Expand steps/times string to list of integer step indices."""
    if ts["times"]:
        result = []
        for tok in ts["times"].split(","):
            tok = tok.strip()
            if tok == "first":   result.append(0)
            elif tok == "last":  result.append(max(0, n_steps - 1))
            else:
                try: result.append(max(0, min(int(tok), n_steps - 1)))
                except ValueError: pass
        return result or [0]
    else:
        N = max(2, int(ts.get("steps", "4")))
        if N == 1: return [0]
        return [round(i * (n_steps - 1) / (N - 1)) for i in range(N)]
```

### `shortcodes.lua` — `fourd_timeseries`

`fourd_timeseries` is a thin wrapper around `fourd_panel` logic:

```lua
local function fourd_timeseries(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))
  local height  = pandoc.utils.stringify(kwargs["height"]  or pandoc.Str("400px"))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-timeseries: missing required attribute <code>id</code></div>')
  end

  -- HTML: read sub-figure IDs from state/figures/<id>-0.html, <id>-1.html, ...
  -- (same as fourd_panel but IDs are auto-named <id>-0, <id>-1, ...)
  if quarto.doc.isFormat("html") then
    -- Collect cells: ts-vm-0, ts-vm-1, ... until file not found
    local cells = {}
    local i = 0
    while true do
      local sub_id = id .. "-" .. i
      local fig_path = "state/figures/" .. sub_id .. ".html"
      local f = io.open(fig_path, "r")
      if not f then break end
      f:close()
      -- embed cell (same srcdoc/src pattern as fourd_panel)
      ...
      i = i + 1
    end
    -- render grid (same layout/relay logic as fourd_panel)
    ...

  -- PDF: embed composite PNG (same as fourd_panel)
  else
    ...
  end
end
```

Registered in the return table: `["4d-timeseries"] = fourd_timeseries`.

---

## Files Changed

| File | Change |
|------|--------|
| `_extensions/4dpaper/4dpaper.py` | `_camera_sync_snippet` (lock button + apply handler), `generate_png_figure` (`camera_fig_id` param), `generate_panel_html` (sync `re_relay`), `generate_panel_png` (`camera_fig_id` for sync), `parse_panel_shortcodes` (`camera_mode`), `parse_timeseries_shortcodes` (new), `_expand_timeseries_steps` (new), `main()` (timeseries expansion + wiring) |
| `_extensions/4dpaper/shortcodes.lua` | `_RELAY_SCRIPT` (lock-query/toggle handlers), new `fourd_timeseries`, registered in return table |
| `dashboard/camera_plugin.py` | `CameraLockHandler` (new), `ROUTES` updated |
| `tests/test_camera_lock.py` | New test file |
| `tests/test_panel_sync.py` | New test file |
| `tests/test_timeseries.py` | New test file |

---

## Error Handling

- **Lock endpoint unavailable** (dashboard not running): `fetch()` failure is silently caught; button stays unlocked. Lock button is hidden-until-loaded by default — on fetch error it stays in default unlocked state.
- **Unknown `camera` value on `4d-panel`**: treated as `"independent"` (no warning needed).
- **`steps="1"`**: treated as `steps="2"` (minimum useful timeseries is 2 frames); single-frame timeseries is just a regular figure.
- **`times` token not parseable**: silently skipped; if no valid tokens remain, falls back to `steps="4"`.
- **Panel sync camera file missing** (`camera_<panel_id>.json` not found): falls back to isometric view for all subfigures — same as existing `generate_png_figure` fallback.

---

## Out of Scope

- Camera lock for `4d-video` and `4d-pvsm`
- `camera="sync"` for more than one level of nesting (panel-of-panels)
- Timeseries with multiple fields per step (use `4d-panel` manually for that)
- `steps` count > simulation step count (clamped silently)
