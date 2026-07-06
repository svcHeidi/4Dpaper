# Instant Figure Preview on OpenFOAM Upload — Design

Date: 2026-07-06
Status: Approved (pending spec review)

## Problem

Today, generating a 4Dpapers figure requires: drop a `.foam` case in the
Insert Figure modal → `/upload/finish` symlinks the case into `data/` and
hands back a `{{< 4d-image >}}` shortcode → the user pastes the shortcode
into a `.qmd` → clicks "Rebuild HTML" → a full Quarto compile runs, which
invokes the `_extensions/4dpaper/4dpaper.py` pre-render hook to actually
generate `state/figures/<id>.html` and `.png`.

There is no way to see the rendered figure without writing a shortcode and
running a full paper compile. The goal of this change is to render the
interactive 3D image and the static post-processing PNG **immediately on
upload**, reusing the exact rendering code the Quarto pipeline already uses,
scoped to just those two artifacts (no metrics, no other post-processing).

## Non-goals

- No frontend UI changes. `insert-figure-overlay.js` keeps inserting the
  shortcode and showing "Inserted ✓"; it does not show a thumbnail or embed
  the new preview anywhere yet.
- No new metrics/statistics computation of any kind.
- No changes to non-OpenFOAM upload paths (`mode="file"` is untouched).
- No changes to the existing Quarto-driven compile/export flow, other than
  sharing its render-serialization lock.

## Architecture

```
UploadFinishHandler.post()  [dashboard/upload_plugin.py, becomes async]
  1. create_case_symlink(...)                      — unchanged, sync, fast
  2. fig_id = slugify(case_name)                    — new
  3. async with _render_lock (shared with compile_plugin):
       result = await loop.run_in_executor(None, _run_preview_subprocess, dest_foam, fig_id, "auto")
  4. if result failed  -> fatal: 500-style error, no shortcode returned
     if result ok      -> generate_shortcode(..., field=result.field, fields=result.fields)
```

### New file: `scripts/render_case_preview.py`

A small standalone CLI script — **not** an in-process import — invoked as a
subprocess with `sys.executable` (the same interpreter running the
dashboard, guaranteeing the same venv/pyvista install).

Rationale for subprocess over direct import: every existing caller of
`generate_html_figure` / `generate_png_figure` runs inside a fresh `quarto`
subprocess (main thread, clean event loop, `nest_asyncio` patched once at
process start in `lib/config.py`). The dashboard is a long-running Tornado
process with its own event loop already active. Calling these functions
in-process from a thread-pool worker would be a new, untested execution
mode for code that pulls in `trame`/`panel`'s async internals. A subprocess
reuses the exact proven model instead.

CLI contract:

```
python scripts/render_case_preview.py \
    --case <path-to-.foam-or-source-file> \
    --fig-id <fig_id> \
    --decimate auto|none|<float-ratio> \
    [--field <field-name>]
```

Behavior:
1. Resolve `PROJECT_ROOT` the same way `lib/config.py` does (env var, else
   `QUARTO_PROJECT_DIR`, else parent of `scripts/`), and add
   `<PROJECT_ROOT>/_extensions/4dpaper` to `sys.path` (mirrors what
   `4dpaper.py` itself does) so `from lib.render import ...` resolves.
2. `from scripts.data_loader import SimulationData` (already resolvable —
   `PROJECT_ROOT` is on `sys.path`, consistent with how `lib/render.py`
   imports it via `_get_simulation`).
3. `sim = SimulationData(case).load()`.
4. Field selection: use `--field` if provided and non-empty, else
   `sim.fields[0]` if `sim.fields` is non-empty, else `""`.
5. `output_dir = <PROJECT_ROOT>/state/figures` (created if missing).
6. Call `generate_html_figure(src_path=case, field=field, time_spec="mid",
   output_path=output_dir/f"{fig_id}.html", fig_id=fig_id,
   available_fields=sim.fields, decimate=decimate)`.
7. Call `generate_png_figure(src_path=case, field=field, time_spec="mid",
   output_path=output_dir/f"{fig_id}.png", fig_id=fig_id,
   decimate=decimate)`.
8. On success: print one JSON line to stdout:
   `{"status": "ok", "field": "<field>", "fields": ["a", "b", ...]}`.
9. On any exception: print the error to stderr and exit non-zero. No
   partial-success signaling — either both artifacts render or the call is
   treated as failed.

### `dashboard/upload_plugin.py` changes

- `UploadFinishHandler.post` becomes `async def post`.
- After `create_case_symlink` returns `dest_foam`, compute (reusing
  `case_name = foam_path.parent.name`, the same variable `create_case_symlink`
  already derives internally):
  ```python
  fig_id = "fig-" + re.sub(r"[^a-z0-9_-]+", "-", case_name.lower()).strip("-")
  ```
  (falls back to a fixed default like `"fig-case"` if the slug is empty).
- Run the subprocess in the executor, holding `_render_lock`:
  ```python
  async with _render_lock:
      proc_result = await loop.run_in_executor(None, _run_preview_subprocess, dest_foam, fig_id, "auto")
  ```
  `_run_preview_subprocess` wraps `subprocess.run([sys.executable, SCRIPT_PATH, "--case", str(dest_foam), "--fig-id", fig_id, "--decimate", "auto"], capture_output=True, text=True)`.
- If `returncode != 0`: respond with a 500 and an error detail built from
  stderr (truncated), and **do not** include a `shortcode` key. The case
  symlink under `data/` is left in place — no rollback, consistent with how
  other partial-failure paths in this handler already behave.
- If `returncode == 0`: parse the JSON line from stdout to get `field` and
  `fields`; pass both into `generate_shortcode(...)`.
- `generate_shortcode()` gains a `fields: list[str]` parameter. When more
  than one field is present, emit a `fields="a,b,c"` attribute on the
  shortcode (matching the existing `4d-image` shortcode contract in
  `CLAUDE.md` §3.1) so the live field switcher survives a later full
  Quarto recompile — without it, the next compile would only know about the
  single `field=` value and the switcher would silently disappear.

### `dashboard/compile_plugin.py` / `dashboard/utils.py` changes

- Move `_render_lock = asyncio.Semaphore(1)` out of `compile_plugin.py` and
  into `dashboard/utils.py` as the single shared instance. Both
  `compile_plugin.py` and `upload_plugin.py` import it from there. This
  serializes preview-subprocess renders against full Quarto compiles for
  the same resource-exhaustion reason the lock already existed for.

## Error handling

| Failure | Behavior |
|---|---|
| Case has 0 timesteps / unreadable mesh | Subprocess raises inside `generate_png_figure`/`generate_html_figure`, exits non-zero. Handler returns 500, no shortcode. |
| Subprocess times out | Wrap `subprocess.run` with a timeout (e.g. 120s); on `TimeoutExpired`, treat identically to a non-zero exit. |
| Subprocess stdout isn't valid JSON on exit 0 | Treat as failure (defensive — should not happen if the script always prints the JSON line last). |
| Concurrent uploads | Serialized by the shared `_render_lock`; second upload's render simply waits. |

## Testing

- Unit tests for `scripts/render_case_preview.py`'s field-selection logic
  (given a stubbed `SimulationData` with `.fields`), independent of PyVista.
- Unit test for the `fig_id` slugify helper in `upload_plugin.py`
  (edge cases: uppercase, spaces, leading/trailing punctuation, empty).
- Integration test on `UploadFinishHandler` using an existing small fixture
  `.foam` case from `tests/`: assert `state/figures/<fig_id>.html` and
  `.png` exist after `/upload/finish`, and the JSON response's `shortcode`
  contains the expected `fields=` attribute when the fixture has >1 field.
- Failure-path test: monkeypatch `_run_preview_subprocess` to return a
  non-zero code and assert the handler responds with an error and omits
  `shortcode`.
