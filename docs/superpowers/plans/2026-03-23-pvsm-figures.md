# PVSM Figure Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `{{< 4d-pvsm src="fig.pvsm" id="fig-vm" >}}` shortcode that replays a ParaView state file to produce an interactive vtk.js HTML figure and a high-quality PDF screenshot.

**Architecture:** pvpython loads the PVSM, exports the filtered geometry as `.vtu` and a screenshot as `.png` in one subprocess call. PyVista reads the `.vtu` and exports a vtk.js HTML figure. The existing camera-sync overlay, relay script, and `/camera/<id>` endpoint are reused without modification.

**Tech Stack:** ParaView pvpython 6.0.1 (`paraview.simple`), PyVista, `xml.etree.ElementTree`, `matplotlib.colors`, existing `4dpaper.py` / `shortcodes.lua` infrastructure.

---

## Project State

These files already exist and must not be re-implemented:
- `_extensions/4dpaper/4dpaper.py` — pre-render hook; add to, don't replace
- `_extensions/4dpaper/shortcodes.lua` — Lua shortcode handlers; add to, don't replace
- `tests/test_extension.py` — existing tests; run them to check nothing breaks
- `state/figures/` — runtime output dir (gitignored)
- pvpython: `/Applications/ParaView-6.0.1.app/Contents/bin/pvpython`
- Example PVSM: `/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/example_state.pvsm`

Run tests with: `source .venv/bin/activate && pytest tests/ -v`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `_extensions/4dpaper/pvsm_render.py` | **Create** | pvpython script: load PVSM → export `.vtu` + `.png` |
| `_extensions/4dpaper/4dpaper.py` | **Modify** | Add `parse_pvsm_shortcodes()`, extend `is_cache_valid()`, add `parse_pvsm_color_info()`, `generate_html_from_vtu()`, `generate_pvsm_figure()`, wire into `main()` |
| `_extensions/4dpaper/shortcodes.lua` | **Modify** | Add `fourd_pvsm()` handler, register `"4d-pvsm"` |
| `tests/test_pvsm.py` | **Create** | Tests for PVSM parsing, CLI, cache, HTML export |

---

## Task 1: `pvsm_render.py` — pvpython script

**Files:**
- Create: `_extensions/4dpaper/pvsm_render.py`
- Test: `tests/test_pvsm.py` (CLI argument parsing only — no pvpython needed)

- [ ] **Step 1: Write the failing CLI-parsing test**

```python
# tests/test_pvsm.py
"""Tests for PVSM figure support."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest

PVSM_RENDER = Path(__file__).parent.parent / "_extensions" / "4dpaper" / "pvsm_render.py"
EXAMPLE_PVSM = Path("/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/example_state.pvsm")
PVPYTHON = Path("/Applications/ParaView-6.0.1.app/Contents/bin/pvpython")

def pvpython_available():
    return PVPYTHON.exists() and EXAMPLE_PVSM.exists()


class TestPvsmRenderCLI:
    def test_missing_required_args_exits_nonzero(self):
        """Running pvsm_render.py without --pvsm should exit non-zero."""
        result = subprocess.run(
            [sys.executable, str(PVSM_RENDER), "--out-vtu", "/tmp/x.vtu", "--out-png", "/tmp/x.png"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_missing_pvsm_file_exits_nonzero(self, tmp_path):
        """Running with a non-existent PVSM file should exit non-zero."""
        result = subprocess.run(
            [sys.executable, str(PVSM_RENDER),
             "--pvsm", str(tmp_path / "nonexistent.pvsm"),
             "--out-vtu", str(tmp_path / "out.vtu"),
             "--out-png", str(tmp_path / "out.png")],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate && pytest tests/test_pvsm.py::TestPvsmRenderCLI -v
```

Expected: `ERRORS` or `FAILED` because `pvsm_render.py` does not exist yet.

- [ ] **Step 3: Create `_extensions/4dpaper/pvsm_render.py`**

```python
#!/usr/bin/env python3
"""
pvpython script: load a ParaView state file, export pipeline geometry and screenshot.

Run with pvpython (NOT regular python):
    pvpython pvsm_render.py --pvsm FILE --out-vtu FILE --out-png FILE [options]
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay a PVSM and export geometry + screenshot.")
    p.add_argument("--pvsm",       required=True,  help="Path to .pvsm file")
    p.add_argument("--out-vtu",    required=True,  help="Output path for .vtu geometry")
    p.add_argument("--out-png",    required=True,  help="Output path for PNG screenshot")
    p.add_argument("--data",       default=None,   help="Override OpenFOAMReader FileName")
    p.add_argument("--time",       default=None,   help="Timestep: float, 'last', or 'mid'")
    p.add_argument("--camera",     default=None,   help="Path to camera JSON")
    p.add_argument("--resolution", nargs=2, type=int, default=[3840, 2160], metavar=("W", "H"))
    return p.parse_args()


def _die(msg: str) -> None:
    print(f"[pvsm_render] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    args = _parse_args()

    pvsm_path = Path(args.pvsm)
    if not pvsm_path.exists():
        _die(f"PVSM file not found: {pvsm_path}")

    out_vtu = Path(args.out_vtu)
    out_png = Path(args.out_png)
    out_vtu.parent.mkdir(parents=True, exist_ok=True)
    out_png.parent.mkdir(parents=True, exist_ok=True)

    # Import paraview here so the script can be imported (for CLI tests) without pvpython.
    try:
        from paraview.simple import (
            LoadState, GetSources, GetAnimationScene,
            GetActiveViewOrCreate, SaveData, SaveScreenshot, Render,
        )
        import paraview.servermanager as sm
    except ImportError:
        _die("paraview.simple not available — run with pvpython, not python.")

    # 1. Load PVSM
    print(f"[pvsm_render] Loading {pvsm_path}", file=sys.stderr)
    LoadState(str(pvsm_path))

    # 2. Patch OpenFOAMReader path if --data given
    if args.data:
        data_path = str(Path(args.data).resolve())
        sources = GetSources()
        patched = False
        for (name, sid), proxy in sources.items():
            if proxy.GetXMLName() == "OpenFOAMReader":
                proxy.FileName = data_path
                proxy.UpdatePipeline()
                print(f"[pvsm_render] Patched OpenFOAMReader '{name}' → {data_path}", file=sys.stderr)
                if patched:
                    print(f"[pvsm_render] WARNING: multiple OpenFOAMReader proxies found; patched first only.", file=sys.stderr)
                patched = True
                break
        if not patched:
            print("[pvsm_render] WARNING: --data given but no OpenFOAMReader found in PVSM.", file=sys.stderr)

    # 3. Set animation time if --time given
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

    # 4. Find last visible filter (leaf source in visible pipeline)
    view = GetActiveViewOrCreate("RenderView")
    reps = list(view.Representations)
    visible_reps = [r for r in reps if getattr(r, "Visibility", 0) == 1]
    if not visible_reps:
        _die("No visible representations found in PVSM render view.")

    # Map rep → its source proxy
    visible_sources = {}
    for rep in visible_reps:
        try:
            src = rep.Input[0]
            if src is not None:
                visible_sources[id(src)] = src
        except (IndexError, AttributeError):
            pass

    if not visible_sources:
        _die("Could not determine source proxies for visible representations.")

    # Find leaf: a visible source whose proxy id is not the Input of any other visible source
    all_input_ids = set()
    for src in visible_sources.values():
        try:
            inp = src.Input[0]
            if inp is not None:
                all_input_ids.add(id(inp))
        except (IndexError, AttributeError):
            pass

    leaves = [s for key, s in visible_sources.items() if key not in all_input_ids]
    if not leaves:
        # Fallback: take the first visible source
        leaves = list(visible_sources.values())

    last_source = leaves[-1]  # deepest leaf if multiple
    print(f"[pvsm_render] Using source: {last_source.GetXMLName()}", file=sys.stderr)

    # 5. Export geometry as .vtu
    print(f"[pvsm_render] Saving geometry → {out_vtu}", file=sys.stderr)
    SaveData(str(out_vtu), proxy=last_source)

    # Verify the file has geometry
    vtu_text = out_vtu.read_text(errors="replace") if out_vtu.exists() else ""
    if 'NumberOfPoints="0"' in vtu_text or not out_vtu.exists():
        _die(f"SaveData produced an empty mesh (0 points): {out_vtu}")

    # 6. Apply camera override if --camera given
    if args.camera:
        cam_path = Path(args.camera)
        if cam_path.exists():
            try:
                cam = json.loads(cam_path.read_text())
                view.CameraPosition  = cam["position"]
                view.CameraFocalPoint = cam["focal_point"]
                view.CameraViewUp    = cam["view_up"]
                Render()
                print(f"[pvsm_render] Applied camera from {cam_path}", file=sys.stderr)
            except Exception as e:
                print(f"[pvsm_render] WARNING: could not apply camera JSON: {e}", file=sys.stderr)
        else:
            print(f"[pvsm_render] WARNING: camera file not found: {cam_path}", file=sys.stderr)

    # 7. Screenshot
    print(f"[pvsm_render] Saving screenshot → {out_png}", file=sys.stderr)
    SaveScreenshot(str(out_png), view, ImageResolution=args.resolution)
    print("[pvsm_render] Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run CLI tests**

```bash
source .venv/bin/activate && pytest tests/test_pvsm.py::TestPvsmRenderCLI -v
```

Expected: both tests PASS (the script exists, imports work with regular python, exits correctly on bad args).

- [ ] **Step 5: Commit**

```bash
git add _extensions/4dpaper/pvsm_render.py tests/test_pvsm.py
git commit -m "feat: add pvsm_render.py pvpython script + CLI tests"
```

---

## Task 2: PVSM XML parsing — color info extraction

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (add `parse_pvsm_color_info()`)
- Modify: `tests/test_pvsm.py` (add `TestPvsmColorParsing`)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pvsm.py`:

```python
import importlib.util

def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPvsmColorParsing:
    def test_scalar_name_at_element_4(self):
        mod = _load_4dpaper()
        info = mod.parse_pvsm_color_info(EXAMPLE_PVSM)
        # The example PVSM colors by "Vm"
        assert info["scalar_name"] == "Vm"

    def test_field_association_is_point_or_cell(self):
        mod = _load_4dpaper()
        info = mod.parse_pvsm_color_info(EXAMPLE_PVSM)
        assert info["field_association"] in ("point", "cell")

    def test_vmin_less_than_vmax(self):
        mod = _load_4dpaper()
        info = mod.parse_pvsm_color_info(EXAMPLE_PVSM)
        assert info["vmin"] < info["vmax"]

    def test_cmap_returned(self):
        mod = _load_4dpaper()
        info = mod.parse_pvsm_color_info(EXAMPLE_PVSM)
        # cmap is either a string name or a matplotlib colormap object
        assert info["cmap"] is not None

    def test_fallback_on_missing_file(self):
        mod = _load_4dpaper()
        info = mod.parse_pvsm_color_info(Path("/nonexistent/file.pvsm"))
        # Should return safe defaults, not raise
        assert info["scalar_name"] == ""
        assert info["cmap"] == "coolwarm"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate && pytest tests/test_pvsm.py::TestPvsmColorParsing -v
```

Expected: `FAILED` — `parse_pvsm_color_info` does not exist yet.

- [ ] **Step 3: Add `parse_pvsm_color_info()` to `4dpaper.py`**

Add after the existing `parse_panel_shortcodes()` function (around line 137), before `is_cache_valid()`:

```python
# ── PVSM parsing ──────────────────────────────────────────────────────────────

def parse_pvsm_color_info(pvsm_path: Path) -> dict:
    """
    Extract color/scalar info from a ParaView state (.pvsm) XML file.

    Returns a dict with keys:
      scalar_name      : str   — active array name (empty string if not found)
      field_association: str   — 'point' or 'cell'
      vmin             : float — scalar range minimum
      vmax             : float — scalar range maximum
      cmap             : str or matplotlib colormap — color map for PyVista
    """
    import xml.etree.ElementTree as ET
    from matplotlib.colors import LinearSegmentedColormap

    _PRESET_MAP = {
        "Cool to Warm":         "coolwarm",
        "Cool to Warm (Extended)": "coolwarm",
        "Viridis (matplotlib)": "viridis",
        "Plasma (matplotlib)":  "plasma",
        "Inferno (matplotlib)": "inferno",
        "Magma (matplotlib)":   "magma",
        "Rainbow Desaturated":  "rainbow",
        "Blue to Red Rainbow":  "jet",
        "erdc_iceFire_H":       "coolwarm",
    }

    _FALLBACK = {
        "scalar_name": "",
        "field_association": "point",
        "vmin": 0.0,
        "vmax": 1.0,
        "cmap": "coolwarm",
    }

    if not pvsm_path.exists():
        return _FALLBACK.copy()

    try:
        tree = ET.parse(str(pvsm_path))
        root = tree.getroot()
        sms = root.find("ServerManagerState")
        if sms is None:
            return _FALLBACK.copy()

        # ── Find the leaf (terminal) visible source proxy id ──────────────────
        # Walk all representation proxies; find the one deepest in the pipeline.
        # The leaf is the GeometryRepresentation whose Input is not the Input of
        # any other GeometryRepresentation.
        rep_inputs: dict[str, str] = {}   # rep_id → source_id
        for proxy in sms.findall("Proxy[@group='representations'][@type='GeometryRepresentation']"):
            rep_id = proxy.get("id", "")
            inp_prop = proxy.find("Property[@name='Input']")
            if inp_prop is not None:
                inp_proxy = inp_prop.find("Proxy")
                if inp_proxy is not None:
                    rep_inputs[rep_id] = inp_proxy.get("value", "")

        # source ids that feed some other source (non-leaf)
        all_source_ids = set(rep_inputs.values())
        # Find the leaf: a source id that is not itself a reader/filter consumed
        # by another representation. In a simple pipeline (reader → clip), the
        # clip's id will not appear as input to any other representation.
        leaf_source_id = ""
        leaf_rep_proxy = None
        for proxy in sms.findall("Proxy[@group='representations'][@type='GeometryRepresentation']"):
            rep_id = proxy.get("id", "")
            source_id = rep_inputs.get(rep_id, "")
            if not source_id:
                continue
            # Check if this source is itself fed into another rep (non-leaf)
            # A source is a leaf if it does not appear as the Input of any OTHER source proxy
            # We approximate: prefer the last found (deepest in XML order) with a valid source
            leaf_source_id = source_id
            leaf_rep_proxy = proxy

        if leaf_rep_proxy is None:
            return _FALLBACK.copy()

        # ── Extract ColorArrayName ────────────────────────────────────────────
        scalar_name = ""
        field_association = "point"
        color_prop = leaf_rep_proxy.find("Property[@name='ColorArrayName']")
        if color_prop is not None:
            elems = color_prop.findall("Element")
            if len(elems) >= 5:
                assoc_val = elems[3].get("value", "1")
                field_association = "point" if assoc_val == "1" else "cell"
                scalar_name = elems[4].get("value", "")

        # ── Find LookupTable proxy id ─────────────────────────────────────────
        lut_id = ""
        lut_prop = leaf_rep_proxy.find("Property[@name='LookupTable']")
        if lut_prop is not None:
            lut_proxy_elem = lut_prop.find("Proxy")
            if lut_proxy_elem is not None:
                lut_id = lut_proxy_elem.get("value", "")

        # ── Extract scalar range + color map from LookupTable ─────────────────
        vmin, vmax = 0.0, 1.0
        cmap: str | object = "coolwarm"

        if lut_id:
            lut_proxy = sms.find(f"Proxy[@id='{lut_id}']")
            if lut_proxy is not None:
                # RGBPoints: flat list [scalar, R, G, B, ...]
                rgb_prop = lut_proxy.find("Property[@name='RGBPoints']")
                if rgb_prop is not None:
                    vals = [float(e.get("value", 0)) for e in rgb_prop.findall("Element")]
                    if len(vals) >= 8:  # at least 2 control points
                        # Groups of 4: [scalar, R, G, B]
                        groups = [vals[i:i+4] for i in range(0, len(vals), 4)]
                        vmin = groups[0][0]
                        vmax = groups[-1][0]

                        # Try named preset first
                        preset_prop = lut_proxy.find("Property[@name='NameOfLastPresetApplied']")
                        preset_name = ""
                        if preset_prop is not None:
                            elem = preset_prop.find("Element")
                            if elem is not None:
                                preset_name = elem.get("value", "")

                        if preset_name and preset_name in _PRESET_MAP:
                            cmap = _PRESET_MAP[preset_name]
                        else:
                            # Build colormap from RGBPoints control points
                            span = vmax - vmin if vmax != vmin else 1.0
                            norm_colors = [
                                ((g[0] - vmin) / span, (g[1], g[2], g[3]))
                                for g in groups
                            ]
                            cmap = LinearSegmentedColormap.from_list(
                                "pvsm",
                                [(t, c) for t, c in norm_colors],
                            )

        return {
            "scalar_name": scalar_name,
            "field_association": field_association,
            "vmin": vmin,
            "vmax": vmax,
            "cmap": cmap,
        }

    except Exception as exc:
        print(f"[4dpaper] WARNING: PVSM color parsing failed ({exc}); using defaults.", file=sys.stderr)
        return _FALLBACK.copy()
```

- [ ] **Step 4: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_pvsm.py::TestPvsmColorParsing -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Make sure existing tests still pass**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all existing tests PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_pvsm.py
git commit -m "feat: add parse_pvsm_color_info() with RGBPoints colormap fallback"
```

---

## Task 3: Extend `is_cache_valid()` + add `parse_pvsm_shortcodes()`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py`
- Modify: `tests/test_pvsm.py` (add `TestPvsmCacheAndParsing`)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_pvsm.py`:

```python
class TestPvsmCacheAndParsing:
    def test_parse_pvsm_shortcodes_finds_basic(self):
        mod = _load_4dpaper()
        text = '{{< 4d-pvsm src="fig-vm.pvsm" id="fig-vm" >}}'
        result = mod.parse_pvsm_shortcodes(text)
        assert len(result) == 1
        assert result[0]["id"] == "fig-vm"
        assert result[0]["src"] == "fig-vm.pvsm"

    def test_parse_pvsm_shortcodes_optional_params(self):
        mod = _load_4dpaper()
        text = '{{< 4d-pvsm src="fig.pvsm" id="fig-a" data="case.foam" time="last" caption="Hi" >}}'
        result = mod.parse_pvsm_shortcodes(text)
        assert result[0]["data"] == "case.foam"
        assert result[0]["time"] == "last"
        assert result[0]["caption"] == "Hi"

    def test_parse_pvsm_shortcodes_defaults(self):
        mod = _load_4dpaper()
        text = '{{< 4d-pvsm src="fig.pvsm" id="fig-a" >}}'
        result = mod.parse_pvsm_shortcodes(text)
        assert result[0]["data"] == ""
        assert result[0]["time"] == ""
        assert result[0]["caption"] == ""

    def test_parse_pvsm_shortcodes_skips_missing_id(self):
        mod = _load_4dpaper()
        text = '{{< 4d-pvsm src="fig.pvsm" >}}'
        result = mod.parse_pvsm_shortcodes(text)
        assert result == []

    def test_parse_pvsm_shortcodes_skips_missing_src(self):
        mod = _load_4dpaper()
        text = '{{< 4d-pvsm id="fig-a" >}}'
        result = mod.parse_pvsm_shortcodes(text)
        assert result == []

    def test_is_cache_valid_extra_deps_triggers_regen(self, tmp_path):
        import time
        mod = _load_4dpaper()
        output = tmp_path / "out.html"
        src = tmp_path / "src.foam"
        extra = tmp_path / "script.py"

        src.write_text("x")
        output.write_text("y")
        time.sleep(0.02)
        extra.write_text("z")  # extra_dep is newer than output

        assert not mod.is_cache_valid(output, src, extra_deps=[extra])

    def test_is_cache_valid_extra_deps_no_regen_when_older(self, tmp_path):
        import time
        mod = _load_4dpaper()
        extra = tmp_path / "script.py"
        extra.write_text("z")
        time.sleep(0.02)
        src = tmp_path / "src.foam"
        src.write_text("x")
        time.sleep(0.02)
        output = tmp_path / "out.html"
        output.write_text("y")  # output is newest

        assert mod.is_cache_valid(output, src, extra_deps=[extra])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_pvsm.py::TestPvsmCacheAndParsing -v
```

Expected: FAILED — functions don't exist yet.

- [ ] **Step 3: Add `parse_pvsm_shortcodes()` to `4dpaper.py`**

Add after `parse_panel_shortcodes()` (after line ~136):

```python
def parse_pvsm_shortcodes(text: str) -> list[dict]:
    """
    Parse {{< 4d-pvsm key="value" ... >}} shortcodes from QMD text.

    Required: id, src. Optional: data, time, caption.
    Shortcodes missing 'id' or 'src' are silently skipped.
    """
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-pvsm\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)=["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("data", "")
        kwargs.setdefault("time", "")
        kwargs.setdefault("caption", "")
        results.append(kwargs)
    return results
```

- [ ] **Step 4: Extend `is_cache_valid()` with `extra_deps` parameter**

Modify the existing `is_cache_valid()` function signature and body:

```python
def is_cache_valid(
    fig_path: Path,
    src_path: Path,
    camera_path: Path | None = None,
    field_path: Path | None = None,
    extra_deps: list[Path] | None = None,
) -> bool:
    """
    Return True if fig_path exists, is newer than src_path, camera_path,
    field_path, and all extra_deps (if given and present).

    Returns True (assume valid) if src_path does not exist.
    """
    if not fig_path.exists():
        return False
    fig_mtime = fig_path.stat().st_mtime
    if src_path.exists() and fig_mtime <= src_path.stat().st_mtime:
        return False
    if camera_path is not None and camera_path.exists():
        if fig_mtime <= camera_path.stat().st_mtime:
            return False
    if field_path is not None and field_path.exists():
        if fig_mtime <= field_path.stat().st_mtime:
            return False
    for dep in (extra_deps or []):
        if dep.exists() and fig_mtime <= dep.stat().st_mtime:
            return False
    return True
```

- [ ] **Step 5: Run all tests**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all tests PASS including the 7 new ones.

- [ ] **Step 6: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_pvsm.py
git commit -m "feat: add parse_pvsm_shortcodes() and extend is_cache_valid() with extra_deps"
```

---

## Task 4: `generate_html_from_vtu()` — PyVista HTML export

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (add `generate_html_from_vtu()`)
- Modify: `tests/test_pvsm.py` (add `TestGenerateHtmlFromVtu`)

This test requires the `.vtu` file from the pvpython smoke test (Task 5). Write a simpler unit test here using a synthetic PyVista mesh instead.

- [ ] **Step 1: Write failing test with a synthetic mesh**

Add to `tests/test_pvsm.py`:

```python
class TestGenerateHtmlFromVtu:
    def test_generates_html_from_vtu(self, tmp_path):
        """generate_html_from_vtu produces a vtk.js HTML file from a .vtu mesh."""
        import pyvista as pv
        mod = _load_4dpaper()

        # Create a synthetic mesh and save as .vtu
        mesh = pv.Sphere()
        mesh.point_data["Vm"] = mesh.points[:, 2]  # z-coordinate as scalar
        vtu_path = tmp_path / "test.vtu"
        mesh.save(str(vtu_path))

        out_html = tmp_path / "test.html"
        mod.generate_html_from_vtu(
            vtu_path=vtu_path,
            out_html=out_html,
            fig_id="test-fig",
            scalar_name="Vm",
            clim=[-1.0, 1.0],
            cmap="coolwarm",
            field_association="point",
            preview=True,  # skip camera JSON lookup
        )

        assert out_html.exists()
        content = out_html.read_text()
        assert "renderWindow" in content or "vtkRenderWindow" in content or len(content) > 1000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate && pytest tests/test_pvsm.py::TestGenerateHtmlFromVtu -v
```

Expected: FAILED — function doesn't exist yet.

- [ ] **Step 3: Add `generate_html_from_vtu()` to `4dpaper.py`**

Add after `generate_html_figure()` (around line 785):

```python
def generate_html_from_vtu(
    vtu_path: Path,
    out_html: Path,
    fig_id: str,
    scalar_name: str,
    clim: list[float],
    cmap,
    field_association: str,
    preview: bool = False,
) -> None:
    """
    Export a PyVista HTML figure from a .vtu geometry file.

    Uses off_screen=False so that export_html() initialises the WebGL exporter
    correctly — same pattern as generate_html_figure().
    """
    import pyvista as pv

    mesh = pv.read(str(vtu_path))

    pl = pv.Plotter(off_screen=False)
    pl.background_color = "#1a1a2e"

    add_kwargs: dict = dict(cmap=cmap, preference=field_association)
    if scalar_name and scalar_name in {**mesh.point_data, **mesh.cell_data}:
        add_kwargs["scalars"] = scalar_name
        add_kwargs["clim"] = clim

    pl.add_mesh(mesh, **add_kwargs)

    if not preview:
        camera_path = _project_root / "state" / f"camera_{fig_id}.json"
        if camera_path.exists():
            try:
                cam = json.loads(camera_path.read_text())
                _apply_camera_from_dict(pl, fig_id, cam)
            except Exception as exc:
                print(f"[4dpaper] WARNING: could not apply camera for {fig_id}: {exc}", file=sys.stderr)
        else:
            pl.isometric_view()
    else:
        pl.isometric_view()

    pl.export_html(str(out_html))
    pl.close()
```

- [ ] **Step 4: Run tests**

```bash
source .venv/bin/activate && pytest tests/test_pvsm.py::TestGenerateHtmlFromVtu -v
```

Expected: PASS.

- [ ] **Step 5: Run all tests**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_pvsm.py
git commit -m "feat: add generate_html_from_vtu() for vtk.js export from PVSM pipeline"
```

---

## Task 5: `generate_pvsm_figure()` + pvpython smoke test

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (add `generate_pvsm_figure()`)
- Modify: `tests/test_pvsm.py` (add `TestPvsmSmoke`)

- [ ] **Step 1: Write the smoke test (pvpython-gated)**

Add to `tests/test_pvsm.py`:

```python
class TestPvsmSmoke:
    @pytest.mark.skipif(not pvpython_available(), reason="requires pvpython + example PVSM")
    def test_generate_pvsm_figure_end_to_end(self, tmp_path):
        """Full pipeline: PVSM → .vtu + .png + .html."""
        mod = _load_4dpaper()

        out_vtu     = tmp_path / "fig-vm-pipeline.vtu"
        out_png     = tmp_path / "fig-vm.png"
        out_html    = tmp_path / "fig-vm.html"
        out_preview = tmp_path / "fig-vm-preview.html"

        mod.generate_pvsm_figure(
            pvsm_path=EXAMPLE_PVSM,
            fig_id="fig-vm",
            figures_dir=tmp_path,
            data_path=None,
            time_spec=None,
            pvpython_path=PVPYTHON,
        )

        # geometry produced and non-empty
        import pyvista as pv
        assert out_vtu.exists(), "VTU not produced"
        mesh = pv.read(str(out_vtu))
        assert mesh.n_points > 0, "VTU has 0 points"

        # screenshot produced and large enough
        assert out_png.exists(), "PNG not produced"
        assert out_png.stat().st_size > 50_000, "PNG suspiciously small"

        # HTML figures produced and contain vtk.js marker
        for html_out in (out_html, out_preview):
            assert html_out.exists(), f"{html_out.name} not produced"
            content = html_out.read_text()
            assert len(content) > 5000, f"{html_out.name} suspiciously small"
```

- [ ] **Step 2: Run smoke test to verify it fails**

```bash
source .venv/bin/activate && pytest tests/test_pvsm.py::TestPvsmSmoke -v
```

Expected: FAILED — `generate_pvsm_figure` doesn't exist yet.

- [ ] **Step 3: Add `generate_pvsm_figure()` to `4dpaper.py`**

Add after `generate_html_from_vtu()`:

```python
def generate_pvsm_figure(
    pvsm_path: Path,
    fig_id: str,
    figures_dir: Path,
    data_path: Path | None = None,
    time_spec: str | None = None,
    pvpython_path: Path | None = None,
) -> None:
    """
    Generate HTML + PNG figures from a ParaView state file.

    Step 1: pvpython subprocess → {fig_id}-pipeline.vtu + {fig_id}.png
    Step 2: PyVista in-process → {fig_id}.html + {fig_id}-preview.html
    """
    import subprocess

    if pvpython_path is None:
        pvpython_path = Path("/Applications/ParaView-6.0.1.app/Contents/bin/pvpython")
    if not pvpython_path.exists():
        raise RuntimeError(
            f"pvpython not found at {pvpython_path}. "
            "Set the correct path in config or install ParaView."
        )

    pvsm_render_script = _here.parent / "pvsm_render.py"
    out_vtu     = figures_dir / f"{fig_id}-pipeline.vtu"
    out_png     = figures_dir / f"{fig_id}.png"
    out_html    = figures_dir / f"{fig_id}.html"
    out_preview = figures_dir / f"{fig_id}-preview.html"
    camera_path = _project_root / "state" / f"camera_{fig_id}.json"

    # ── Step 1: pvpython subprocess ───────────────────────────────────────────
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

    print(f"[4dpaper] Running pvpython for {fig_id} …", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="", file=sys.stderr)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"pvpython failed for {fig_id} (exit {result.returncode}). "
            "See output above."
        )

    if not out_vtu.exists():
        raise RuntimeError(f"pvpython did not produce {out_vtu}")

    # ── Step 2: PyVista HTML export ───────────────────────────────────────────
    color_info = parse_pvsm_color_info(pvsm_path)

    print(f"[4dpaper] Generating {fig_id}.html from VTU …", file=sys.stderr)
    generate_html_from_vtu(
        vtu_path=out_vtu,
        out_html=out_html,
        fig_id=fig_id,
        scalar_name=color_info["scalar_name"],
        clim=[color_info["vmin"], color_info["vmax"]],
        cmap=color_info["cmap"],
        field_association=color_info["field_association"],
        preview=False,
    )

    print(f"[4dpaper] Generating {fig_id}-preview.html …", file=sys.stderr)
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

- [ ] **Step 4: Run smoke test**

```bash
source .venv/bin/activate && pytest tests/test_pvsm.py::TestPvsmSmoke -v -s
```

Expected: PASS — `.vtu`, `.png`, `.html`, `-preview.html` all produced with correct content.

- [ ] **Step 5: Run all tests**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_pvsm.py
git commit -m "feat: add generate_pvsm_figure() — pvpython + PyVista pipeline"
```

---

## Task 6: Wire `4d-pvsm` into `main()` in `4dpaper.py`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (update `main()`)

- [ ] **Step 1: Locate `main()` and identify the insertion point**

In `4dpaper.py`, find the `main()` function. Currently it collects `figures`, `videos`, `panels`. Add `pvsm_figs` alongside them.

Find these lines (around line 1211–1218):
```python
figures = []
videos = []
panels = []
for qmd in qmd_files:
    text = qmd.read_text()
    figures.extend(parse_shortcodes(text))
    videos.extend(parse_video_shortcodes(text))
    panels.extend(parse_panel_shortcodes(text))
```

- [ ] **Step 2: Add PVSM parsing and processing to `main()`**

Replace that block with:

```python
figures = []
videos = []
panels = []
pvsm_figs = []
for qmd in qmd_files:
    text = qmd.read_text()
    figures.extend(parse_shortcodes(text))
    videos.extend(parse_video_shortcodes(text))
    panels.extend(parse_panel_shortcodes(text))
    pvsm_figs.extend(parse_pvsm_shortcodes(text))
```

And update the "nothing found" guard (around line 1220):
```python
if not figures and not videos and not panels and not pvsm_figs:
    print("[4dpaper] No 4d-image, 4d-video, 4d-panel, or 4d-pvsm shortcodes found.", file=sys.stderr)
    return
```

Then add the PVSM processing loop after the existing panel loop (at the end of `main()`, before the closing `if __name__` block). Insert after the `for panel in panels:` loop:

```python
    # ── PVSM shortcode processing ───────────────────────────────────────────
    _pvsm_render_script = _here.parent / "pvsm_render.py"
    _pvpython_path = Path("/Applications/ParaView-6.0.1.app/Contents/bin/pvpython")

    for pvsm_fig in pvsm_figs:
        fig_id   = pvsm_fig["id"]
        pvsm_src = Path(pvsm_fig["src"]) if Path(pvsm_fig["src"]).is_absolute() \
                   else _project_root / pvsm_fig["src"]
        data_str = pvsm_fig.get("data", "").strip()
        data_path = Path(data_str) if data_str else None
        time_spec = pvsm_fig.get("time", "").strip() or None

        out_html    = figures_dir / f"{fig_id}.html"
        out_png     = figures_dir / f"{fig_id}.png"
        out_preview = figures_dir / f"{fig_id}-preview.html"
        out_vtu     = figures_dir / f"{fig_id}-pipeline.vtu"
        camera_path = _project_root / "state" / f"camera_{fig_id}.json"

        extra_deps = [_pvsm_render_script]
        script_newer = out_html.exists() and _here.stat().st_mtime > out_html.stat().st_mtime
        cache_ok = (
            not script_newer
            and is_cache_valid(out_html, pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
            and is_cache_valid(out_png,  pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
        )

        if cache_ok:
            print(f"[4dpaper] {fig_id} PVSM outputs are up to date — skipping.", file=sys.stderr)
            continue

        print(f"[4dpaper] Generating PVSM figure for {fig_id} …", file=sys.stderr)
        try:
            generate_pvsm_figure(
                pvsm_path=pvsm_src,
                fig_id=fig_id,
                figures_dir=figures_dir,
                data_path=data_path,
                time_spec=time_spec,
                pvpython_path=_pvpython_path,
            )
        except Exception as exc:
            print(f"[4dpaper] ERROR generating PVSM figure {fig_id}: {exc}", file=sys.stderr)
            sys.exit(1)
```

- [ ] **Step 3: Run existing tests to confirm no regressions**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py
git commit -m "feat: wire 4d-pvsm shortcodes into 4dpaper.py main() processing loop"
```

---

## Task 7: `fourd_pvsm()` Lua shortcode handler

**Files:**
- Modify: `_extensions/4dpaper/shortcodes.lua`

- [ ] **Step 1: Add `fourd_pvsm()` before the `return` table**

In `shortcodes.lua`, add the following function before the `return {` block (after `fourd_panel`, around line 403):

```lua
local function fourd_pvsm(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">&#9888; 4d-pvsm: missing required attribute <code>id</code></div>')
  end

  -- ── HTML output ─────────────────────────────────────────────────────────
  if quarto.doc.isFormat("html") then
    local html_path = "state/figures/" .. id .. ".html"
    local exists = io.open(html_path, "r")
    if exists then exists:close() end

    if not exists then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;' ..
        'border-radius:4px;margin:1rem 0">' ..
        '<strong>&#9888; 4D PVSM figure not yet rendered</strong><br>' ..
        'Figure ID: <code>' .. id .. '</code><br>' ..
        '<small>Click <strong>Rebuild HTML</strong> in the dashboard to generate.</small>' ..
        '</div>')
    end

    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end

    local cap_html = caption ~= "" and
      '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
      or ""

    local body
    if _app_mode then
      -- Camera button at paper level (same as fourd_video) to avoid compositor issues.
      local cam_onclick =
        "(function(){" ..
        "var o=document.getElementById('fourd-cam-overlay');" ..
        "var lb=document.getElementById('fourd-cam-figid');" ..
        "var f=document.getElementById('fourd-cam-iframe');" ..
        "var ss=document.getElementById('fourd-cam-sttxt');" ..
        "if(lb)lb.textContent='fig id: " .. id .. "';" ..
        "if(f)f.src='/state/figures/" .. id .. "-preview.html?t='+Date.now();" ..
        "if(ss){ss.textContent='Rotate - saves automatically';ss.style.color='#0a8';}" ..
        "if(o)o.style.display='flex';" ..
        "})()"
      local iframe_id = 'fourd-pvsm-' .. id
      body = '<div style="position:relative;display:inline-block;width:100%;">' ..
             '<iframe id="' .. iframe_id .. '" src="" width="100%" height="600px" ' ..
             'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>' ..
             '<script>(function(){' ..
             'var f=document.getElementById("' .. iframe_id .. '");' ..
             'if(f)f.src="/state/figures/' .. id .. '.html?t="+Date.now();' ..
             '})();</script>' ..
             '<button onclick="' .. cam_onclick .. '" ' ..
             'style="position:absolute;top:8px;right:8px;z-index:10;' ..
             'background:rgba(0,0,0,0.65);color:#fff;border:none;border-radius:4px;' ..
             'padding:4px 10px;font-size:12px;cursor:pointer;">&#128247; Camera View</button>' ..
             '</div>'
    else
      -- Export mode: inline as srcdoc for self-contained HTML
      local f = io.open(html_path, "r")
      local content = f:read("*all")
      f:close()
      local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")
      body = '<iframe srcdoc="' .. escaped .. '" width="100%" height="600px" ' ..
             'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>'
    end

    return pandoc.RawBlock("html",
      '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
      body .. '\n' .. cap_html ..
      '</figure>\n' ..
      relay_script)

  -- ── PDF / LaTeX output ───────────────────────────────────────────────────
  else
    local fig_path = "state/figures/" .. id .. ".png"
    local f = io.open(fig_path, "r")
    if f then
      f:close()
      local img = pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" }))
      return pandoc.Para({ img })
    else
      return pandoc.Para({
        pandoc.Str("[PVSM figure "),
        pandoc.Code(id),
        pandoc.Str(" — run 'Rebuild HTML' from the dashboard to generate this figure]"),
      })
    end
  end
end
```

- [ ] **Step 2: Register the handler**

Replace the `return` table at the bottom of `shortcodes.lua`:

```lua
return {
  ["4d-image"] = fourd_image,
  ["4d-video"] = fourd_video,
  ["4d-panel"] = fourd_panel,
  ["4d-pvsm"]  = fourd_pvsm,
}
```

- [ ] **Step 3: Add a `{{< 4d-pvsm >}}` shortcode to `analysis_report.qmd` for testing**

Open `analysis_report.qmd` and add a new section after the existing figures:

```markdown
## PVSM Figure Test

{{< 4d-pvsm src="/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/example_state.pvsm" id="fig-pvsm-vm" caption="Transmembrane voltage — ParaView pipeline" >}}
```

- [ ] **Step 4: Touch figures so cache is not invalidated by script mtime, then rebuild HTML**

```bash
touch state/figures/*.html state/figures/*.png state/figures/*.vtu 2>/dev/null || true
source .venv/bin/activate && FOURD_APP_MODE=1 quarto render analysis_report.qmd --to html --profile apphtml 2>&1 | tail -20
```

Expected:
- `[4dpaper] Generating PVSM figure for fig-pvsm-vm …` appears in output
- `Output created: _output/analysis_report.html`
- No ERROR lines

- [ ] **Step 5: Verify the PVSM figure appears in the output HTML**

```bash
grep -c "fourd-pvsm-fig-pvsm-vm" _output/analysis_report.html
```

Expected: `1` (the cache-busting iframe wrapper is present).

- [ ] **Step 6: Run all tests**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add _extensions/4dpaper/shortcodes.lua analysis_report.qmd _output/analysis_report.html
git commit -m "feat: add fourd_pvsm() Lua handler and register 4d-pvsm shortcode"
```

---

## Task 8: Cache invalidation test + final integration check

**Files:**
- Modify: `tests/test_pvsm.py` (add `TestPvsmCacheInvalidation`)

- [ ] **Step 1: Write cache invalidation integration tests**

Add to `tests/test_pvsm.py`:

```python
class TestPvsmCacheInvalidation:
    def test_pvsm_render_script_mtime_triggers_regen(self, tmp_path):
        """Touching pvsm_render.py should make is_cache_valid return False."""
        import time
        mod = _load_4dpaper()

        script = tmp_path / "pvsm_render.py"
        pvsm   = tmp_path / "fig.pvsm"
        output = tmp_path / "fig.html"

        pvsm.write_text("<ParaView/>")
        script.write_text("# script")
        time.sleep(0.02)
        output.write_text("<html/>")  # output is newest
        time.sleep(0.02)
        script.touch()               # now script is newest

        result = mod.is_cache_valid(output, pvsm, extra_deps=[script])
        assert result is False

    def test_pvsm_change_triggers_regen(self, tmp_path):
        """Touching the PVSM file should invalidate the cache."""
        import time
        mod = _load_4dpaper()

        pvsm   = tmp_path / "fig.pvsm"
        output = tmp_path / "fig.html"

        pvsm.write_text("<ParaView/>")
        time.sleep(0.02)
        output.write_text("<html/>")
        time.sleep(0.02)
        pvsm.touch()  # PVSM newer than output

        result = mod.is_cache_valid(output, pvsm)
        assert result is False

    def test_unrelated_file_does_not_trigger_regen(self, tmp_path):
        """Touching an unrelated file should not invalidate the cache."""
        import time
        mod = _load_4dpaper()

        pvsm    = tmp_path / "fig.pvsm"
        output  = tmp_path / "fig.html"
        unrelated = tmp_path / "other.txt"

        pvsm.write_text("<ParaView/>")
        unrelated.write_text("x")
        time.sleep(0.02)
        output.write_text("<html/>")
        time.sleep(0.02)
        unrelated.touch()  # only unrelated file is newer

        result = mod.is_cache_valid(output, pvsm)
        assert result is True
```

- [ ] **Step 2: Run the cache tests**

```bash
source .venv/bin/activate && pytest tests/test_pvsm.py::TestPvsmCacheInvalidation -v
```

Expected: all 3 PASS.

- [ ] **Step 3: Run full test suite**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all tests PASS, no regressions in `test_extension.py` or `test_field_plugin.py`.

- [ ] **Step 4: Final end-to-end rebuild with dashboard**

Start the dashboard and click **Rebuild HTML**. Verify:
- The log shows `[4dpaper] Generating PVSM figure for fig-pvsm-vm …`
- The paper preview shows the PVSM figure with the Camera View button
- Clicking Camera View opens the overlay and shows the interactive vtk.js preview

- [ ] **Step 5: Final commit**

```bash
git add tests/test_pvsm.py
git commit -m "test: add PVSM cache invalidation tests"
```
