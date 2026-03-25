# PVSM Controls Parity Design

## Overview

PVSM figures (`4d-pvsm` shortcode) currently have no controls injected — no lock button, no camera sync, no orientation widget, no time scrubber. This spec brings them to full parity with `4d-image` and `4d-timeseries` figures.

**Conditional time scrubber:** when the `time=` attribute is absent from the shortcode, all available time steps are rendered and embedded (scrubber enabled). When `time="T"` is specified, a single static render is produced (lock + orientation only).

---

## Background: Two Rendering Paths

| Path | Source | How rendered |
|------|--------|-------------|
| `4d-image` / `4d-timeseries` | `.foam` OpenFOAM case | PyVista reads case directly; `generate_html_figure` injects `_controls_strip_snippet` |
| `4d-pvsm` | ParaView state file (`.pvsm`) pointing to a `.foam` case | pvpython executes full pipeline → `.vtu` → PyVista `export_html()` → `generate_pvsm_figure`; **no controls injected today** |

The PVSM path applies arbitrary ParaView filters (clipping, streamlines, isovolumes) before the VTU is written. The output mesh may differ from the raw `.foam` mesh, but the time-varying scalar data follows the same base64 Float32Array embedding as regular figures.

---

## Topology Safety Guard

**Problem:** if the pipeline changes mesh topology between time steps (e.g. a threshold filter that shrinks the mesh), the client-side field-swap approach breaks because the number of points changes.

**This risk exists equally for `.foam` and `.pvsm`.**

**Guard (applies to both paths):** before building `time_data_b64`, verify that all per-time scalar arrays have the same number of points as the base mesh. If any mismatch is found:
- Skip `time_data_b64` / `time_labels` entirely (no scrubber)
- Render static at the last available time step
- Print a warning to stderr: `[4dpaper] WARNING: {fig_id} — mesh topology changes between time steps; time scrubber disabled.`

This guard is added to `generate_html_figure` (`.foam` path) as well as `generate_pvsm_figure`.

---

## `pvsm_render.py` Changes

The script gains an `--all-times` flag (no argument; presence triggers multi-time mode).

### Single-time mode (existing, `--time T` or no flag + no `--all-times`)
Unchanged: renders at the specified time, saves one `{fig_id}-pipeline.vtu`.

### All-times mode (`--all-times`, only when `--time` is absent)

1. Query available time steps: `times = GetAnimationScene().TimeKeeper.TimestepValues`
2. For **time step 0**: `GetAnimationScene().AnimationTime = times[0]` → `GetActiveSource().UpdatePipeline()` → save `{fig_id}-pipeline.vtu` via `SaveData` (geometry for HTML base)
3. For **each time step i**: `GetAnimationScene().AnimationTime = times[i]` → `GetActiveSource().UpdatePipeline()` → `vtk_output = GetActiveSource().GetClientSideObject().GetOutput()` → extract named array from point data via `vtk_output.GetPointData().GetArray(scalar_name)` → convert to numpy float32 → save `{fig_id}-scalars-t{i}.bin` (raw float32 little-endian, no header)
4. Produce `{fig_id}.png`: render at `times[-1]` (last time step) applying `--camera` if provided, same as single-time mode
5. Save `{fig_id}-times.json`: list of time label strings (`[str(t) for t in times]`)

The scalar name is passed via a new `--scalar` argument (already known from `color_info` in `generate_pvsm_figure`).

Output files for N time steps:
```
{fig_id}-pipeline.vtu          ← geometry from t=0 (once)
{fig_id}-scalars-t0.bin        ← float32 scalar values at t=0
{fig_id}-scalars-t1.bin        ← float32 scalar values at t=1
...
{fig_id}-scalars-t{N-1}.bin
{fig_id}-times.json            ← ["0.0", "0.01", ..., "0.09"]
{fig_id}.png                   ← screenshot at t=last (with camera if provided)
```

---

## `generate_pvsm_figure` Changes

### Lock + orientation (always)

After `generate_html_from_vtu` writes `{fig_id}.html`, inject `_controls_strip_snippet`:

```python
html = out_html.read_text()
inj_html = _controls_strip_snippet(
    fig_id=fig_id,
    show_lock_btn=True,
    show_orientation=True,
    time_labels=time_labels,        # None when time_spec set
    time_data_b64=time_data_b64,    # None when time_spec set
    time_global_range=global_range, # None when time_spec set
    time_field=scalar_name,         # always the PVSM scalar
) + "\n</body>"
html = html.replace("</body>", inj_html, 1)
out_html.write_text(html)
```

### Time scrubber (conditional on `time_spec`)

**`time_spec` is set (`time="T"`):**
- Existing single-render behaviour unchanged
- `time_labels=None`, `time_data_b64=None` → no scrubber, lock + orientation only

**`time_spec` is None (includes `time=""` — existing code maps both to `None` via `.strip() or None`):**
1. Pass `--all-times --scalar {scalar_name}` to pvpython subprocess
2. Read `{fig_id}-times.json` → `time_labels`
3. Load base VTU via `pv.read(out_vtu)` → `vtu_point_count = mesh.n_points`
4. For each `{fig_id}-scalars-t{i}.bin`:
   - Load raw bytes → `np.frombuffer(bytes, dtype=np.float32)`
   - **Topology guard:** if `len(arr) != vtu_point_count` → clear `time_data_b64` / `time_labels`, log warning, break
   - Otherwise encode base64 → append to `time_data_b64`
5. Compute `global_range = [min over all frames, max over all frames]`
6. Pass all to `_controls_strip_snippet`

The reference point count is `pv.read(out_vtu).n_points` — the PyVista-loaded mesh — because the `.bin` scalars are extracted from the same pipeline output that produces the VTU. This keeps the comparison apples-to-apples regardless of any PyVista post-processing (surface extraction, multiblock flattening) that `generate_html_from_vtu` may apply later.

### Caching

In `main()`, the existing `cache_ok` block (before calling `generate_pvsm_figure`) is extended. When `time_spec is None`, cache is only valid if all expected output files exist:

```python
scalar_bins_ok = True
if time_spec is None:
    times_json = figures_dir / f"{fig_id}-times.json"
    if times_json.exists():
        import json as _json
        n = len(_json.loads(times_json.read_text()))
        scalar_bins_ok = all(
            (figures_dir / f"{fig_id}-scalars-t{i}.bin").exists()
            for i in range(n)
        )
    else:
        scalar_bins_ok = False

cache_ok = (
    not script_newer
    and scalar_bins_ok
    and is_cache_valid(out_html, pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
    and is_cache_valid(out_png,  pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
)
```

---

## Lua Shortcode (`fourd_pvsm`)

No changes required. The controls strip is injected into the HTML file at generation time. Whether Lua embeds via `srcdoc` or `src=` URL, the JS in the file communicates with `window.parent` via postMessage and works either way.

---

## Testing

New test class `TestPvsmControls` in `tests/test_pvsm_figure.py`. All tests mock the pvpython subprocess and write fake output files to a `tmp_path`.

| Test | Assertion |
|------|-----------|
| `test_pvsm_controls_injected` | Output HTML contains `cs-lock-widget-` |
| `test_pvsm_orientation_injected` | Output HTML contains `cs-svg-axes-` |
| `test_pvsm_time_scrubber_when_no_time_spec` | Fake VTU + N scalar bins → HTML contains `cs-time-slider-` |
| `test_pvsm_no_scrubber_when_time_spec_set` | `time_spec="0.5"` → HTML contains lock, NOT `cs-time-slider-` |
| `test_pvsm_topology_guard` | Scalar bins with mismatched point count → no `cs-time-slider-`, warning in stderr |
| `test_pvsm_topology_guard` | Scalar bins with mismatched point count → no `cs-time-slider-`, warning in stderr |
| `test_pvsm_topology_guard_foam` | In `generate_html_figure`, patch `pv.read` to return meshes with differing `n_points` across time frames → `time_data_b64` not passed to `_controls_strip_snippet`, warning in stderr |
| `test_pvsm_global_range_computed` | `global_range` spans all frames (min/max across all scalar bins) |
| `test_pvsm_cache_includes_scalar_bins` | When scalar bins are missing, `cache_ok` is False even if `out_html` and `out_png` are up to date |
