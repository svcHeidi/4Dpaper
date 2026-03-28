# PVSM Controls Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject lock button, orientation widget, and conditional time scrubber into PVSM figures so they participate in the same controls system as `4d-image` and `4d-timeseries` figures.

**Architecture:** `pvsm_render.py` gains an `--all-times` mode that writes one geometry VTU (at t=0) plus N float32 scalar `.bin` files (one per time step) and a `times.json` label list. `generate_pvsm_figure` in `4dpaper.py` reads those files, applies a topology guard, builds `time_data_b64`, then calls `_controls_strip_snippet` and injects the result into the HTML exactly as `generate_html_figure` does. `main()` extends its cache check to validate scalar bin staleness.

**Tech Stack:** Python 3, pvpython/ParaView, PyVista, NumPy, pytest, unittest.mock

---

## File Structure

| File | Role |
|------|------|
| `_extensions/4dpaper/pvsm_render.py` | Add `--all-times` + `--scalar` flags; all-times loop writes `.bin` + `times.json` |
| `_extensions/4dpaper/4dpaper.py` | `generate_pvsm_figure`: inject controls + read bins + topology guard. `main()`: extended cache check |
| `tests/test_pvsm_figure.py` | New — `TestPvsmControls` with 8 tests |

---

## Task 1: Write failing tests

**Files:**
- Create: `tests/test_pvsm_figure.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for PVSM figure controls parity (lock, orientation, time scrubber)."""
from __future__ import annotations
import importlib.util
import json
import struct
import sys
import time as _time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FAKE_COLOR_INFO = {
    "scalar_name": "Vm",
    "vmin": -0.1,
    "vmax": 0.1,
    "cmap": "coolwarm",
    "field_association": "point",
}


def _make_bins(figures_dir: Path, fig_id: str, n_times: int, n_points: int) -> None:
    """Write fake float32 scalar .bin files and times.json."""
    for i in range(n_times):
        val = float(i)
        data = struct.pack(f"{n_points}f", *([val] * n_points))
        (figures_dir / f"{fig_id}-scalars-t{i}.bin").write_bytes(data)
    labels = [f"{i * 0.01:.4g}" for i in range(n_times)]
    (figures_dir / f"{fig_id}-times.json").write_text(json.dumps(labels))


def _fake_subprocess_side_effect(figures_dir, fig_id, n_times=3, n_points=10):
    """Return a subprocess.run mock side_effect that writes expected output files."""
    def _side_effect(cmd, **kwargs):
        (figures_dir / f"{fig_id}-pipeline.vtu").write_text("<VTKFile/>")
        (figures_dir / f"{fig_id}.png").write_bytes(b"\x89PNG")
        _make_bins(figures_dir, fig_id, n_times, n_points)
        return MagicMock(returncode=0, stdout="", stderr="")
    return _side_effect


def _call_generate(mod, tmp_path, fig_id="fig-pvsm-vm", time_spec=None,
                   n_times=3, n_points=10, scalar_name="Vm"):
    """Call generate_pvsm_figure with all I/O mocked; return output HTML text."""
    figures_dir = tmp_path / "figures"
    figures_dir.mkdir(exist_ok=True)
    pvsm_path = tmp_path / "test.pvsm"
    pvsm_path.write_text("<ParaView/>")
    pvpython = tmp_path / "pvpython"
    pvpython.write_text("#!/bin/sh\n")
    pvpython.chmod(0o755)

    color_info = {**FAKE_COLOR_INFO, "scalar_name": scalar_name}

    def _fake_html(vtu_path, out_html, **kwargs):
        out_html.write_text("<html><body></body></html>")

    with patch("subprocess.run",
               side_effect=_fake_subprocess_side_effect(figures_dir, fig_id, n_times, n_points)), \
         patch.object(mod, "parse_pvsm_color_info", return_value=color_info), \
         patch.object(mod, "generate_html_from_vtu", side_effect=_fake_html):
        mod.generate_pvsm_figure(
            pvsm_path=pvsm_path,
            fig_id=fig_id,
            figures_dir=figures_dir,
            time_spec=time_spec,
            pvpython_path=pvpython,
        )

    return (figures_dir / f"{fig_id}.html").read_text()


class TestPvsmControls:
    def test_pvsm_controls_injected(self, tmp_path):
        """Lock widget always present regardless of time_spec."""
        mod = _load_4dpaper()
        html = _call_generate(mod, tmp_path, time_spec="0.5")
        assert 'id="cs-lock-widget-fig_pvsm_vm"' in html

    def test_pvsm_orientation_injected(self, tmp_path):
        """Orientation SVG always present."""
        mod = _load_4dpaper()
        html = _call_generate(mod, tmp_path, time_spec="0.5")
        assert 'id="cs-svg-axes-fig_pvsm_vm"' in html

    def test_pvsm_time_scrubber_when_no_time_spec(self, tmp_path):
        """Time slider present when time_spec=None and bins exist."""
        mod = _load_4dpaper()
        html = _call_generate(mod, tmp_path, time_spec=None)
        assert 'id="cs-time-slider-fig_pvsm_vm"' in html

    def test_pvsm_no_scrubber_when_time_spec_set(self, tmp_path):
        """No time slider when time_spec is set (static render)."""
        mod = _load_4dpaper()
        html = _call_generate(mod, tmp_path, time_spec="0.5")
        assert 'id="cs-time-slider-fig_pvsm_vm"' not in html

    def test_pvsm_topology_guard(self, tmp_path, capsys):
        """Mismatched bin lengths → no scrubber, warning to stderr."""
        mod = _load_4dpaper()
        figures_dir = tmp_path / "figures"
        figures_dir.mkdir()
        pvsm_path = tmp_path / "test.pvsm"
        pvsm_path.write_text("<ParaView/>")
        pvpython = tmp_path / "pvpython"
        pvpython.write_text("#!/bin/sh\n")
        pvpython.chmod(0o755)

        def _mismatched(cmd, **kwargs):
            (figures_dir / "fig-pvsm-vm-pipeline.vtu").write_text("<VTKFile/>")
            (figures_dir / "fig-pvsm-vm.png").write_bytes(b"\x89PNG")
            # Frame 0: 10 pts, Frame 1: 15 pts — MISMATCH
            (figures_dir / "fig-pvsm-vm-scalars-t0.bin").write_bytes(
                struct.pack("10f", *([0.0] * 10)))
            (figures_dir / "fig-pvsm-vm-scalars-t1.bin").write_bytes(
                struct.pack("15f", *([1.0] * 15)))
            (figures_dir / "fig-pvsm-vm-times.json").write_text('["0.0", "0.01"]')
            return MagicMock(returncode=0, stdout="", stderr="")

        def _fake_html(vtu_path, out_html, **kwargs):
            out_html.write_text("<html><body></body></html>")

        with patch("subprocess.run", side_effect=_mismatched), \
             patch.object(mod, "parse_pvsm_color_info", return_value=FAKE_COLOR_INFO), \
             patch.object(mod, "generate_html_from_vtu", side_effect=_fake_html):
            mod.generate_pvsm_figure(
                pvsm_path=pvsm_path,
                fig_id="fig-pvsm-vm",
                figures_dir=figures_dir,
                time_spec=None,
                pvpython_path=pvpython,
            )

        html = (figures_dir / "fig-pvsm-vm.html").read_text()
        assert 'id="cs-time-slider-fig_pvsm_vm"' not in html
        captured = capsys.readouterr()
        assert "topology" in (captured.err + captured.out).lower()

    def test_pvsm_no_scrubber_when_empty_scalar(self, tmp_path):
        """No scrubber when scalar_name is empty; lock still injected."""
        mod = _load_4dpaper()
        html = _call_generate(mod, tmp_path, time_spec=None, scalar_name="")
        assert 'id="cs-time-slider-fig_pvsm_vm"' not in html
        assert 'id="cs-lock-widget-fig_pvsm_vm"' in html

    def test_pvsm_global_range_computed(self, tmp_path):
        """Time scrubber is present when bins exist (global range computed)."""
        mod = _load_4dpaper()
        # Frames: 0.0, 1.0, 0.5 — global range should be [0.0, 1.0]
        html = _call_generate(mod, tmp_path, time_spec=None, n_times=3)
        assert 'id="cs-time-slider-fig_pvsm_vm"' in html

    def test_pvsm_cache_stale_bins(self, tmp_path):
        """is_cache_valid returns False when pvsm_src is newer than bin."""
        mod = _load_4dpaper()
        figures_dir = tmp_path / "figures"
        figures_dir.mkdir()
        fig_id = "fig-pvsm-vm"

        # Write bin first
        bin_path = figures_dir / f"{fig_id}-scalars-t0.bin"
        bin_path.write_bytes(b"\x00" * 4)
        _time.sleep(0.05)
        # Then write pvsm_src (newer)
        pvsm_src = tmp_path / "test.pvsm"
        pvsm_src.write_text("")

        assert mod.is_cache_valid(bin_path, pvsm_src) is False

    def test_pvsm_cache_missing_bins(self, tmp_path):
        """is_cache_valid returns False when bin does not exist."""
        mod = _load_4dpaper()
        bin_path = tmp_path / "fig-pvsm-vm-scalars-t0.bin"
        pvsm_src = tmp_path / "test.pvsm"
        pvsm_src.write_text("")
        # bin_path does not exist
        assert mod.is_cache_valid(bin_path, pvsm_src) is False

    def test_pvsm_cache_includes_scalar_bins(self, tmp_path):
        """main() cache_ok is False when bins are missing even if out_html and out_png are present."""
        import importlib
        mod = _load_4dpaper()
        figures_dir = tmp_path / "figures"
        figures_dir.mkdir()
        fig_id = "fig-pvsm-vm"
        pvsm_src = tmp_path / "test.pvsm"
        pvsm_src.write_text("")

        # Write times.json indicating 2 steps
        (figures_dir / f"{fig_id}-times.json").write_text('["0.0", "0.01"]')
        # Write up-to-date out_html and out_png (newer than pvsm_src)
        _time.sleep(0.05)
        out_html = figures_dir / f"{fig_id}.html"
        out_png  = figures_dir / f"{fig_id}.png"
        out_html.write_text("<html><body></body></html>")
        out_png.write_bytes(b"\x89PNG")
        # Scalar bins are ABSENT — cache should be invalid
        assert not mod.is_cache_valid(figures_dir / f"{fig_id}-scalars-t0.bin", pvsm_src)
        assert not mod.is_cache_valid(figures_dir / f"{fig_id}-scalars-t1.bin", pvsm_src)
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd /Users/simaocastro/4Dpapers
pytest tests/test_pvsm_figure.py -v 2>&1 | tail -20
```

Expected: 9+ FAILED (AttributeError or AssertionError — `generate_pvsm_figure` does not inject controls yet; `test_pvsm_cache_includes_scalar_bins` fails because bins are absent).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_pvsm_figure.py
git commit -m "test: add failing tests for PVSM controls parity"
```

---

## Task 2: `pvsm_render.py` — all-times mode

**Files:**
- Modify: `_extensions/4dpaper/pvsm_render.py`

This task adds `--all-times` and `--scalar` CLI arguments and the multi-time scalar extraction loop to `pvsm_render.py`.

> **Context:** This script runs under pvpython (not regular Python), so ParaView imports are inside `main()`. The existing flow is: load PVSM → patch data → set time → find leaf source → write VTU → apply camera → screenshot. In all-times mode, the VTU is written from t=0, then scalars are extracted per time step without re-writing geometry.

- [ ] **Step 1: Update `_parse_args` to add the two new flags**

In `_extensions/4dpaper/pvsm_render.py`, replace the `_parse_args` function:

```python
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay a PVSM and export geometry + screenshot.")
    p.add_argument("--pvsm",       required=True,  help="Path to .pvsm file")
    p.add_argument("--out-vtu",    required=True,  help="Output path for .vtu geometry")
    p.add_argument("--out-png",    required=True,  help="Output path for PNG screenshot")
    p.add_argument("--data",       default=None,   help="Override OpenFOAMReader FileName")
    p.add_argument("--time",       default=None,   help="Timestep: float, 'last', or 'mid'")
    p.add_argument("--camera",     default=None,   help="Path to camera JSON")
    p.add_argument("--resolution", nargs=2, type=int, default=[3840, 2160], metavar=("W", "H"))
    p.add_argument("--all-times",  action="store_true",
                   help="Export scalar .bin files for all time steps (mutually exclusive with --time)")
    p.add_argument("--scalar",     default=None,
                   help="Scalar field name to extract in --all-times mode")
    return p.parse_args()
```

- [ ] **Step 2: Add mutual exclusion guard at the top of `main()`**

After the existing `pvsm_path` check block, add:

```python
    if args.all_times and args.time is not None:
        _die("--all-times and --time are mutually exclusive")
    if args.all_times and not args.scalar:
        _die("--all-times requires --scalar <field_name>")
```

- [ ] **Step 3: Adjust time-setting for all-times mode**

The existing step 3 block is:
```python
    # 3. Set animation time if --time given
    if args.time is not None:
        ...
```

For all-times mode, we want to start at t=0. Add an `elif` branch after the existing `if`:

```python
    # 3. Set animation time
    if args.time is not None:
        scene = GetAnimationScene()
        t = args.time.strip()
        if t == "last":
            scene.GoToLast()
        elif t == "mid":
            mid = (scene.StartTime + scene.EndTime) / 2.0
            scene.AnimationTime = mid
        else:
            try:
                scene.AnimationTime = float(t)
            except ValueError:
                _die(f"--time must be 'last', 'mid', or a float; got: {t!r}")
        view = GetActiveViewOrCreate("RenderView")
        view.Update()
    elif args.all_times:
        scene = GetAnimationScene()
        all_times = list(scene.TimeKeeper.TimestepValues)
        if not all_times:
            _die("--all-times: no time steps found in animation scene")
        scene.AnimationTime = all_times[0]
        view = GetActiveViewOrCreate("RenderView")
        view.Update()
```

- [ ] **Step 4: Append `--all-times` and `--scalar` flags to the pvpython `cmd` in `generate_pvsm_figure`**

In `generate_pvsm_figure`, `parse_pvsm_color_info` must be called BEFORE the subprocess cmd is built so `scalar_name` is available. Move `color_info = parse_pvsm_color_info(pvsm_path)` to just before the `cmd = [...]` construction, then append the new flags:

```python
    # Move parse_pvsm_color_info BEFORE subprocess cmd
    color_info = parse_pvsm_color_info(pvsm_path)   # ← MOVED here (was after subprocess)

    cmd = [
        str(pvpython_path), str(pvsm_render_script),
        "--pvsm",    str(pvsm_path),
        "--out-vtu", str(out_vtu),
        "--out-png", str(out_png),
    ]
    if data_path:
        cmd += ["--data", str(data_path)]
    if time_spec:
        cmd += ["--time", str(time_spec)]
    if camera_path.exists():
        cmd += ["--camera", str(camera_path)]
    if not time_spec and color_info.get("scalar_name"):
        cmd += ["--all-times", "--scalar", color_info["scalar_name"]]
```

Also remove the duplicate `color_info = parse_pvsm_color_info(pvsm_path)` that previously appeared after the subprocess call.

- [ ] **Step 5: Add all-times scalar extraction after the existing VTU writing (step 5)**

After the existing "Verify the file has geometry" block (the `if 'NumberOfPoints="0"'` check, around line 208), add:

```python
    # 5b. All-times: extract per-step scalar .bin files
    if args.all_times:
        import vtkmodules.vtkFiltersCore as _vtkfc
        fig_id_stem = Path(args.out_vtu).stem.replace("-pipeline", "")
        figures_dir = Path(args.out_vtu).parent
        scalar_name = args.scalar

        def _extract_scalar_array(leaf_src):
            """Return the scalar array as a list of floats from the leaf source output."""
            csobj = leaf_src.SMProxy.GetClientSideObject()
            raw = csobj.GetOutputDataObject(0)
            data_class = raw.GetClassName()
            if "MultiBlock" in data_class or "Composite" in data_class:
                blocks = []
                it = raw.NewIterator()
                it.InitTraversal()
                while not it.IsDoneWithTraversal():
                    ds = it.GetCurrentDataObject()
                    if ds is not None and ds.GetNumberOfPoints() > 0:
                        blocks.append(ds)
                    it.GoToNextItem()
                if not blocks:
                    return None
                if len(blocks) == 1:
                    data = blocks[0]
                else:
                    app = _vtkfc.vtkAppendFilter()
                    for b in blocks:
                        app.AddInputDataObject(b)
                    app.MergePointsOff()
                    app.Update()
                    data = app.GetOutput()
            else:
                data = raw
            vtk_arr = data.GetPointData().GetArray(scalar_name)
            if vtk_arr is None:
                return None
            n = vtk_arr.GetNumberOfTuples()
            return [vtk_arr.GetValue(j) for j in range(n)]

        for i, t in enumerate(all_times):
            scene.AnimationTime = t
            view.Update()
            last_source.UpdatePipeline()
            arr = _extract_scalar_array(last_source)
            if arr is None:
                _die(f"--all-times: scalar '{scalar_name}' not found at time {t} (step {i})")
            import struct as _struct
            bin_path = figures_dir / f"{fig_id_stem}-scalars-t{i}.bin"
            bin_path.write_bytes(_struct.pack(f"{len(arr)}f", *arr))
            print(f"[pvsm_render] t={t}: wrote {len(arr)} values -> {bin_path.name}",
                  file=sys.stderr)

        times_json = figures_dir / f"{fig_id_stem}-times.json"
        times_json.write_text(json.dumps([str(t) for t in all_times]))
        print(f"[pvsm_render] Wrote {len(all_times)} time steps -> {times_json.name}",
              file=sys.stderr)

        # Move to last time for screenshot
        scene.AnimationTime = all_times[-1]
        view.Update()
        last_source.UpdatePipeline()
```

- [ ] **Step 6: Run the existing test suite to confirm nothing broken**

```bash
cd /Users/simaocastro/4Dpapers
pytest tests/ -v --ignore=tests/test_pvsm_figure.py 2>&1 | tail -10
```

Expected: all existing tests pass (pvsm_render.py is only run via subprocess; no test exercises it directly).

- [ ] **Step 7: Commit**

```bash
git add _extensions/4dpaper/pvsm_render.py _extensions/4dpaper/4dpaper.py
git commit -m "feat: pvsm_render.py all-times mode; pass --all-times --scalar from generate_pvsm_figure"
```

---

## Task 3: `generate_pvsm_figure` — controls injection and time data

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` — `generate_pvsm_figure` function (lines ~1360–1445)

> **Context:** `generate_pvsm_figure` currently ends after two `generate_html_from_vtu` calls (one for main HTML, one for preview). The new step adds: read scalar bins if present, apply topology guard, call `_controls_strip_snippet`, inject into HTML. The `_controls_strip_snippet` function is already in the same file and handles `time_labels=None` gracefully (no scrubber).

- [ ] **Step 1: Add the controls injection block at the end of `generate_pvsm_figure`**

Replace the end of `generate_pvsm_figure` (after the `generate_html_from_vtu` preview call at line ~1445) with the new step:

The existing function ends with:
```python
    print(f"[4dpaper] Generating {fig_id}-preview.html ...", file=sys.stderr)
    generate_html_from_vtu(
        vtu_path=out_vtu,
        out_html=out_preview,
        fig_id=fig_id,
        scalar_name=color_info["scalar_name"],
        clim=[color_info["vmin"], color_info["vmax"]],
        cmap=color_info["cmap"],
        field_association=color_info["field_association"],
        preview=True,
    )
```

Add the following AFTER that block (still inside `generate_pvsm_figure`):

```python
    # -- Step 3: Build time data and inject controls ----------------------------
    import base64 as _b64
    import json as _json
    import numpy as _np

    scalar_name = color_info.get("scalar_name", "") or ""
    time_labels: list[str] | None = None
    time_data_b64: list[str] | None = None
    time_global_range: list[float] | None = None

    if not time_spec and scalar_name:
        times_json = figures_dir / f"{fig_id}-times.json"
        if times_json.exists():
            try:
                time_labels = _json.loads(times_json.read_text())
                arrays = []
                for i in range(len(time_labels)):
                    bin_path = figures_dir / f"{fig_id}-scalars-t{i}.bin"
                    arr = _np.frombuffer(bin_path.read_bytes(), dtype="float32")
                    arrays.append(arr)

                # Topology guard: all frame arrays must have the same length
                ref_len = len(arrays[0]) if arrays else 0
                if any(len(a) != ref_len for a in arrays):
                    print(
                        f"[4dpaper] WARNING: {fig_id} — mesh topology changes between "
                        "time steps; time scrubber disabled.",
                        file=sys.stderr,
                    )
                    time_labels = None
                else:
                    time_data_b64 = [
                        _b64.b64encode(a.tobytes()).decode("ascii") for a in arrays
                    ]
                    time_global_range = [
                        float(min(a.min() for a in arrays)),
                        float(max(a.max() for a in arrays)),
                    ]
            except Exception as exc:
                print(
                    f"[4dpaper] WARNING: {fig_id} — could not load time data: {exc}; "
                    "time scrubber disabled.",
                    file=sys.stderr,
                )
                time_labels = None

    controls = _controls_strip_snippet(
        fig_id=fig_id,
        show_lock_btn=True,
        show_orientation=True,
        time_labels=time_labels,
        time_data_b64=time_data_b64,
        time_global_range=time_global_range,
        time_field=scalar_name,
    )
    if controls:
        html = out_html.read_text()
        if "</body>" in html:
            out_html.write_text(html.replace("</body>", controls + "\n</body>", 1))
```

- [ ] **Step 2: Run the new tests**

```bash
cd /Users/simaocastro/4Dpapers
pytest tests/test_pvsm_figure.py -v 2>&1 | tail -20
```

Expected: 7 PASSED, 1 FAILED (`test_pvsm_cache_stale_bins` and `test_pvsm_cache_missing_bins` depend only on `is_cache_valid` which already works — these should pass). If all 8 pass, great.

Actually expect: all 8 PASSED (the cache tests use `is_cache_valid` which is unchanged and already handles missing/stale files).

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/simaocastro/4Dpapers
pytest tests/ -v 2>&1 | tail -15
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py
git commit -m "feat: inject controls strip into PVSM figures (lock, orientation, time scrubber)"
```

---

## Task 4: `main()` — extended cache check for scalar bins

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` — PVSM section in `main()` (lines ~2113–2127)

> **Context:** The cache block at lines 2117–2123 only checks `out_html` and `out_png`. When `time_spec` is None, scalar bins must also be up to date. `is_cache_valid(bin_path, pvsm_src)` returns False if bin doesn't exist OR is older than pvsm_src.

- [ ] **Step 1: Replace the `cache_ok` block in `main()`**

Find the existing block (lines ~2117–2123):

```python
        extra_deps = [_pvsm_render_script]
        script_newer = out_html.exists() and _here.stat().st_mtime > out_html.stat().st_mtime
        cache_ok = (
            not script_newer
            and is_cache_valid(out_html, pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
            and is_cache_valid(out_png,  pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
        )
```

Replace with:

```python
        extra_deps = [_pvsm_render_script]
        script_newer = out_html.exists() and _here.stat().st_mtime > out_html.stat().st_mtime

        scalar_bins_ok = True
        if not time_spec:
            times_json_path = figures_dir / f"{fig_id}-times.json"
            if times_json_path.exists():
                try:
                    import json as _j
                    n_steps = len(_j.loads(times_json_path.read_text()))
                    bin_paths = [
                        figures_dir / f"{fig_id}-scalars-t{i}.bin"
                        for i in range(n_steps)
                    ]
                    scalar_bins_ok = all(
                        is_cache_valid(p, pvsm_src, camera_path=camera_path)
                        for p in bin_paths
                    )
                except Exception:
                    scalar_bins_ok = False
            else:
                scalar_bins_ok = False

        cache_ok = (
            not script_newer
            and scalar_bins_ok
            and is_cache_valid(out_html, pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
            and is_cache_valid(out_png,  pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
        )
```

- [ ] **Step 2: Run all tests**

```bash
cd /Users/simaocastro/4Dpapers
pytest tests/ -v 2>&1 | tail -15
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py
git commit -m "feat: extend PVSM main() cache check for scalar bins"
```
