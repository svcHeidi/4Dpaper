# Instant Figure Preview on OpenFOAM Upload — Design

Date: 2026-07-06
Status: Approved (revised 2026-07-06 after spec review)

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

## Prerequisite: complete the serial-case copy in `copy_case_data`

All modal uploads are staged under `state/upload_tmp`, so `create_case_symlink`
always takes the copy path (`upload_plugin.py:85-87`), never the symlink path.
Today `copy_case_data` copies only the `.foam` file, `constant/polyMesh`, and
`processor*` time directories — a serial/reconstructed case loses its
root-level time directories and `system/`, so `SimulationData` sees
`n_steps == 0`. Under the current flow this is a latent bug that only surfaces
at compile time; under this design's fatal-error policy it would turn **every
serial-case upload into a hard 500**.

The first commit of this change must extend `copy_case_data` to also copy:

- root-level numeric time directories (same `float(name)` filter the
  `processor*` branch already uses), and
- the `system/` directory when present (the VTK OpenFOAM reader expects
  `system/controlDict`).

Regression test: stage a minimal fake serial case (`case.foam`,
`system/controlDict`, `constant/polyMesh/points`, `0/T`, `0.1/T`) through
`/upload/finish` and assert the time directories and `system/` exist under
`data/<case>/` after staging.

## Architecture

```
UploadFinishHandler.post()  [dashboard/upload_plugin.py, becomes async]
  1. create_case_symlink(...)                      — unchanged, sync, fast
  2. fig_id = slugify(case_name)                    — new
  3. acquire _render_lock (shared with compile_plugin, bounded wait):
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
1. Resolve the **app root** relative to the script's own file
   (`Path(__file__).resolve().parent.parent`) — correct both in the repo
   layout and in Docker, where `scripts/` and `_extensions/` are baked into
   `/app` while `PROJECT_ROOT=/workspace`, so
   `<PROJECT_ROOT>/_extensions/4dpaper` may not exist. Insert the app root
   and `<app_root>/_extensions/4dpaper` into `sys.path` so both
   `from lib.render import ...` and `from scripts.data_loader import ...`
   resolve. Do **not** assume `PROJECT_ROOT` is already on `sys.path` — that
   is only true inside `4dpaper.py`, which inserts it explicitly
   (`4dpaper.py:23-25`); a fresh subprocess only has `scripts/` on its path.
2. Resolve `PROJECT_ROOT` the same way `lib/config.py` does (env var, else
   `QUARTO_PROJECT_DIR`, else the app-root parent) — used only to locate the
   `state/figures` output directory, not for imports.
3. `sim = _get_simulation(case)` (imported from `lib.render`) instead of
   constructing `SimulationData` directly: the two `generate_*_figure` calls
   below hit the same module-level `_SIMULATION_CACHE`, so the case is loaded
   exactly once instead of twice (case loading is the slowest step for large
   OpenFOAM data).
4. Field selection: use `--field` if provided and non-empty, else
   `sim.fields[0]` if `sim.fields` is non-empty, else `""`.
5. `output_dir = <PROJECT_ROOT>/state/figures` (created if missing).
6. Call `generate_html_figure(src_path=case, field=field, time_spec="mid",
   output_path=output_dir/f"{fig_id}.html", fig_id=fig_id,
   available_fields=sim.fields, decimate=decimate)`.
7. Call `generate_png_figure(src_path=case, field=field, time_spec="mid",
   output_path=output_dir/f"{fig_id}.png", fig_id=fig_id,
   decimate=decimate)`. Note: `generate_png_figure` also writes
   `<fig_id>.pdf` via `save_graphic()` (`lib/render.py:614`) — three artifacts
   total; the PDF sidecar is expected and must not be "cleaned up".
8. On success: print one JSON line to stdout **as the final line**:
   `{"status": "ok", "field": "<field>", "fields": ["a", "b", ...]}`.
   The `generate_*_figure` functions already print progress lines to stdout
   (`Generated (PNG): ...`), so the handler parses the **last non-empty
   line** of stdout as JSON.
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
- Run the subprocess in the executor, holding `_render_lock`. Acquire the
  lock with a **bounded wait**: an in-flight Quarto compile holds the lock for
  up to 1800 s (`run_quarto_render`'s timeout in `dashboard/utils.py`), and
  the 120 s subprocess timeout does not cover lock-wait time — without a
  bound, the upload request (and the frontend's "Staging + generating
  shortcode..." status) can hang for half an hour:
  ```python
  try:
      await asyncio.wait_for(_render_lock.acquire(), timeout=15)
  except asyncio.TimeoutError:
      self.set_status(503)
      self.write({"status": "error",
                  "detail": "A compile is currently running — try again shortly."})
      return
  try:
      proc_result = await loop.run_in_executor(None, _run_preview_subprocess, dest_foam, fig_id, "auto")
  finally:
      _render_lock.release()
  ```
  `_run_preview_subprocess` wraps `subprocess.run([python, SCRIPT_PATH, "--case", str(dest_foam), "--fig-id", fig_id, "--decimate", "auto"], capture_output=True, text=True, timeout=120)`,
  where `python` prefers `<PROJECT_ROOT>/.venv/bin/python` when it exists
  (mirroring the re-exec in `4dpaper.py:28-41`, so preview and compile render
  with the same library versions) and falls back to `sys.executable`.
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

### `dashboard/compile_plugin.py` / `dashboard/render_lock.py` changes

- Move `_render_lock = asyncio.Semaphore(1)` out of `compile_plugin.py` and
  into a new dependency-free module `dashboard/render_lock.py` as the single
  shared instance. Both `compile_plugin.py` and `upload_plugin.py` import it
  from there. This serializes preview-subprocess renders against full Quarto
  compiles for the same resource-exhaustion reason the lock already existed
  for. (Not `dashboard/utils.py` as originally drafted: `utils.py` imports
  the `cryptography`-backed signing helpers, and the lock module must stay
  import-light so `upload_plugin` doesn't inherit that dependency chain.)

## Error handling

| Failure | Behavior |
|---|---|
| Case has 0 timesteps / unreadable mesh | Subprocess raises inside `generate_png_figure`/`generate_html_figure`, exits non-zero. Handler returns 500, no shortcode. |
| Subprocess times out | Wrap `subprocess.run` with a timeout (300s; a real 158-step cardiac case measured ~90s); on `TimeoutExpired`, treat identically to a non-zero exit. |
| Render lock held by a long compile | `asyncio.wait_for` on lock acquisition times out after 15s → 503 "compile in progress", no shortcode, symlinked case left in place. |
| Last non-empty stdout line isn't valid JSON on exit 0 | Treat as failure (defensive — the script prints the JSON line last, after the generators' progress output). |
| Concurrent uploads | Serialized by the shared `_render_lock`; second upload's render waits (within the same 15s acquisition bound). |

## Testing

There is **no `.foam` fixture case anywhere under `tests/` today** (consistent
with CLAUDE.md §6.0 — OpenFOAM is "missing redistributable local fixtures"),
so handler tests must stub the render subprocess and the real-render
integration test must be gated on fixture presence.

- Unit tests for `scripts/render_case_preview.py`'s field-selection logic
  (given a stubbed `SimulationData` with `.fields`), independent of PyVista.
- Unit test for the `fig_id` slugify helper in `upload_plugin.py`
  (edge cases: uppercase, spaces, leading/trailing punctuation, empty).
- **Update the existing test**
  `test_figure_mode_copies_staged_openfoam_case_into_data_dir`: it uploads a
  one-byte fake `case.foam` and asserts a 200 — under the fatal-preview
  policy it would flip to 500. Monkeypatch `_run_preview_subprocess` to
  return a successful result with a known `field`/`fields` payload.
- Success-path handler test (same stub): assert the JSON response's
  `shortcode` contains the expected `fields=` attribute when the stub reports
  more than one field.
- Failure-path test: monkeypatch `_run_preview_subprocess` to return a
  non-zero code and assert the handler responds with an error and omits
  `shortcode`.
- Lock-busy test: hold `_render_lock` in the test, call `/upload/finish`, and
  assert a 503 response.
- Serial-case copy regression test (see Prerequisite section above).
- Real-render integration test (assert `state/figures/<fig_id>.html` and
  `.png` exist after `/upload/finish`): mark with `pytest.mark.skipif` on the
  presence of a committed fixture case at `tests/data/foam_case/`. Committing
  a redistributable minimal OpenFOAM case is tracked separately as part of
  the CLAUDE.md §6.0 verification-status work.

## Notes

- Field auto-selection reads the fields present on the mesh **at the rendered
  timestep** (`_fields_at_step`, the "mid" index), not `sim.fields` (which
  reads step 0). Verified necessary on 2026-07-07: the real monodomainHeart
  case carries setup fields (`conductivity`, `fiber`, ...) only at time 0 and
  the solved fields (`Vm`, `activationTime`, ...) in later time dirs — step-0
  detection picked `conductivity`, which then rendered as bare geometry with
  6 "field not found" warnings. Detecting at the rendered step yields `Vm`.
  The chosen field is the alphabetically-first of those (deterministic);
  `--field` overrides it.
- Because the preview writes `state/figures/<fig_id>.html`/`.png` *after* the
  case copy, `is_cache_valid` treats them as fresh on the next compile — the
  user's first "Rebuild HTML" after upload reuses the preview assets for
  free. This is the main payoff of reusing the exact Quarto render code.
