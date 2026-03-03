# Phase 3 — Quarto Extension + Iframe Paper Preview

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the `4dpaper` Quarto extension so users write `{{< 4d-image >}}` shortcodes in their own `.qmd`, see interactive 3D figures in HTML, and export a camera-locked PDF — with the dashboard Paper tab showing a live iframe of the rendered paper.

**Architecture:** A Quarto pre-render hook (`4dpaper.py`) scans the `.qmd` for `{{< 4d-image >}}` calls, generates self-contained vtk.js HTML widgets into `state/figures/`, and a thin Lua shim (`shortcodes.lua`) embeds them. HTML output → interactive vtk.js; PDF output → pvpython-rendered PNG. The dashboard Paper tab splits into "Rebuild HTML" (interactive figures) and "Export PDF" (locked-camera static), and embeds the result in an iframe served via Panel's `--static-dirs`.

**Tech Stack:** Quarto extensions (Lua shortcodes, pre-render hook), PyVista `Plotter.export_html()`, Panel iframe, Python subprocess + pathlib, pytest TDD.

---

## Project State at Start of This Plan

Phase 1 + 2 are complete. These files exist and work:

```
/Users/simaocastro/4Dpapers/
├── dashboard/
│   ├── app.py                    ← Panel app (needs --static-dirs note + import update)
│   ├── config.yaml               ← has paraview + state_dir blocks
│   ├── utils.py                  ← has save/load_camera_state, run_pvpython_render, run_quarto_render
│   └── pages/
│       └── paper_page.py         ← single rebuild button (needs iframe + two-button split)
├── scripts/
│   ├── data_loader.py            ← SimulationData class
│   └── interactive_viz.py        ← create_interactive_plot()
├── tests/
│   ├── test_utils.py             ← 11 passing tests
│   └── test_pages.py             ← 3 passing smoke tests
├── analysis_report.qmd           ← hardcoded demo paper (gets stripped to template in Task 6)
├── _quarto.yml                   ← needs pre-render: line added
└── state/
    └── .gitkeep
```

**Key reference paths:**
- pvpython: `/Applications/ParaView-6.0.1.app/Contents/bin/pvpython`
- Foam case: `/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam`
- PVSM: `/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/example_state.pvsm`
- venv Python: `/Users/simaocastro/4Dpapers/.venv/bin/python`

---

## What Gets Added

```
/Users/simaocastro/4Dpapers/
├── _extensions/
│   └── 4dpaper/
│       ├── _extension.yml        ← NEW: Quarto extension manifest
│       ├── shortcodes.lua        ← NEW: {{< 4d-image >}} Lua shim
│       └── 4dpaper.py            ← NEW: pre-render hook (parse + generate figures)
├── state/
│   └── figures/
│       └── .gitkeep              ← NEW: cache dir (actual files gitignored)
├── tests/
│   └── test_extension.py         ← NEW: TDD tests for 4dpaper.py helpers
├── _quarto.yml                   ← MODIFY: add pre-render line
├── .gitignore                    ← MODIFY: add state/figures/
├── dashboard/
│   ├── app.py                    ← MODIFY: add --static-dirs launch comment
│   └── pages/
│       └── paper_page.py         ← MODIFY: iframe + two buttons
└── analysis_report.qmd           ← MODIFY: strip to clean template
```

---

## Task 1 — Extension scaffold + gitignore + `_quarto.yml`

**Files:**
- Create: `_extensions/4dpaper/_extension.yml`
- Create: `_extensions/4dpaper/shortcodes.lua` (stub)
- Create: `_extensions/4dpaper/4dpaper.py` (stub)
- Create: `state/figures/.gitkeep`
- Modify: `.gitignore`
- Modify: `_quarto.yml`

### Step 1.1 — Create the extension directory and manifest

```bash
cd /Users/simaocastro/4Dpapers
mkdir -p _extensions/4dpaper
mkdir -p state/figures
touch state/figures/.gitkeep
```

Create `_extensions/4dpaper/_extension.yml` with this exact content:

```yaml
title: 4DPaper
author: 4DPaper
version: 1.0.0
contributes:
  shortcodes:
    - shortcodes.lua
```

### Step 1.2 — Create stub `shortcodes.lua`

Create `_extensions/4dpaper/shortcodes.lua`:

```lua
-- 4DPaper shortcode handler
-- Full implementation in Task 4. This stub prevents Quarto errors.

local function fourd_image(args, kwargs)
  local id = pandoc.utils.stringify(kwargs["id"] or pandoc.Str("unknown"))
  return pandoc.RawBlock("html",
    '<div style="border:1px dashed #888;padding:1rem;text-align:center">' ..
    '⚠ 4d-image stub — id: <code>' .. id .. '</code></div>')
end

return {
  ["4d-image"] = fourd_image,
}
```

### Step 1.3 — Create stub `4dpaper.py`

Create `_extensions/4dpaper/4dpaper.py`:

```python
#!/usr/bin/env python3
"""
4DPaper pre-render hook — run by Quarto before rendering.

Scans the .qmd for {{< 4d-image >}} shortcodes and generates
figure files in state/figures/ (HTML for web, PNG for PDF).

Full implementation added in Task 2 and Task 3.
"""
import sys
print("[4dpaper] pre-render hook: stub (no figures generated yet)", file=sys.stderr)
```

Make it executable:
```bash
chmod +x _extensions/4dpaper/4dpaper.py
```

### Step 1.4 — Update `.gitignore`

Append to `.gitignore`:
```
# Extension-generated figure cache
state/figures/*.html
state/figures/*.png
```

### Step 1.5 — Update `_quarto.yml`

Read the current file. Replace the `project:` block to add `pre-render`:

Find:
```yaml
project:
  title: "4D Paper — OpenFOAM Analysis"
  type: default
  output-dir: _output
```

Replace with:
```yaml
project:
  title: "4D Paper — OpenFOAM Analysis"
  type: default
  output-dir: _output
  pre-render: _extensions/4dpaper/4dpaper.py
```

### Step 1.6 — Verify Quarto structure is intact

```bash
cd /Users/simaocastro/4Dpapers
quarto render analysis_report.qmd --no-execute 2>&1 | tail -5
```

Expected: `Output created: _output/analysis_report.html` (stub hook prints one line to stderr, render succeeds).

### Step 1.7 — Commit

```bash
git add _extensions/ state/figures/.gitkeep .gitignore _quarto.yml
git commit -m "chore: add 4dpaper extension scaffold with stub shortcode and pre-render hook"
```

---

## Task 2 — `4dpaper.py`: shortcode parser + cache check (TDD)

**Files:**
- Create: `tests/test_extension.py`
- Modify: `_extensions/4dpaper/4dpaper.py`

### Step 2.1 — Write failing tests

Create `tests/test_extension.py`:

```python
"""Tests for _extensions/4dpaper/4dpaper.py helper functions."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

# Make the extension importable
sys.path.insert(0, str(Path(__file__).parent.parent / "_extensions" / "4dpaper"))
import importlib
import importlib.util


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestParseShortcodes:
    def test_finds_single_shortcode(self):
        mod = _load_4dpaper()
        text = '{{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}'
        result = mod.parse_shortcodes(text)
        assert len(result) == 1
        assert result[0]["id"] == "fig-vm"
        assert result[0]["src"] == "case.foam"
        assert result[0]["field"] == "Vm"

    def test_finds_multiple_shortcodes(self):
        mod = _load_4dpaper()
        text = (
            '{{< 4d-image src="a.foam" field="Vm" id="fig-a" >}}\n'
            'some prose\n'
            '{{< 4d-image src="b.foam" field="activationTime" id="fig-b" time="last" >}}'
        )
        result = mod.parse_shortcodes(text)
        assert len(result) == 2
        assert result[1]["time"] == "last"

    def test_returns_empty_for_no_shortcodes(self):
        mod = _load_4dpaper()
        result = mod.parse_shortcodes("# Just a heading\n\nSome prose.")
        assert result == []

    def test_skips_shortcode_missing_required_keys(self):
        mod = _load_4dpaper()
        # Missing 'id'
        text = '{{< 4d-image src="case.foam" field="Vm" >}}'
        result = mod.parse_shortcodes(text)
        assert result == []

    def test_defaults_time_to_mid(self):
        mod = _load_4dpaper()
        text = '{{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}'
        result = mod.parse_shortcodes(text)
        assert result[0].get("time", "mid") == "mid"


class TestIsCacheValid:
    def test_returns_false_when_fig_missing(self, tmp_path):
        mod = _load_4dpaper()
        src = tmp_path / "case.foam"
        src.write_text("")
        fig = tmp_path / "fig-vm.html"
        assert mod.is_cache_valid(fig, src) is False

    def test_returns_true_when_fig_newer_than_src(self, tmp_path):
        mod = _load_4dpaper()
        src = tmp_path / "case.foam"
        src.write_text("")
        time.sleep(0.05)
        fig = tmp_path / "fig-vm.html"
        fig.write_text("<html></html>")
        assert mod.is_cache_valid(fig, src) is True

    def test_returns_false_when_src_newer_than_fig(self, tmp_path):
        mod = _load_4dpaper()
        fig = tmp_path / "fig-vm.html"
        fig.write_text("<html></html>")
        time.sleep(0.05)
        src = tmp_path / "case.foam"
        src.write_text("")
        assert mod.is_cache_valid(fig, src) is False

    def test_returns_true_when_src_missing(self, tmp_path):
        mod = _load_4dpaper()
        fig = tmp_path / "fig-vm.html"
        fig.write_text("<html></html>")
        src = tmp_path / "no_such_file.foam"
        assert mod.is_cache_valid(fig, src) is True
```

### Step 2.2 — Run tests to verify they fail

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/python -m pytest tests/test_extension.py -v 2>&1 | tail -20
```

Expected: `AttributeError: module 'fourDpaper' has no attribute 'parse_shortcodes'`

### Step 2.3 — Implement `parse_shortcodes` and `is_cache_valid` in `4dpaper.py`

Replace the entire content of `_extensions/4dpaper/4dpaper.py` with:

```python
#!/usr/bin/env python3
"""
4DPaper pre-render hook — run by Quarto before rendering.

Scans the .qmd for {{< 4d-image >}} shortcodes and generates
figure files in state/figures/ (HTML for web, PNG for PDF).

Quarto calls this script before rendering. It reads QUARTO_DOCUMENT_PATH
and QUARTO_OUTPUT_FORMAT from the environment.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# ── Ensure venv Python is used ────────────────────────────────────────────────
_here = Path(__file__).resolve()
_project_root = _here.parent.parent.parent  # _extensions/4dpaper/ → project root
_venv_python = _project_root / ".venv" / "bin" / "python"
if _venv_python.exists() and Path(sys.executable).resolve() != _venv_python.resolve():
    os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

# Add project root to path for scripts/
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ── Shortcode parsing ─────────────────────────────────────────────────────────

def parse_shortcodes(text: str) -> list[dict]:
    """
    Parse {{< 4d-image key="value" ... >}} shortcodes from QMD text.

    Returns a list of dicts with at minimum 'id', 'src', 'field' keys.
    Shortcodes missing 'id' or 'src' are silently skipped.
    'time' defaults to 'mid' if not specified.
    """
    pattern = r'\{\{<\s*4d-image\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, text, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)="([^"]*)"', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("time", "mid")
        kwargs.setdefault("field", "")
        results.append(kwargs)
    return results


# ── Cache helpers ─────────────────────────────────────────────────────────────

def is_cache_valid(fig_path: Path, src_path: Path) -> bool:
    """
    Return True if fig_path exists and is newer than src_path.
    Returns True (assume valid) if src_path does not exist.
    """
    if not fig_path.exists():
        return False
    if not src_path.exists():
        return True
    return fig_path.stat().st_mtime > src_path.stat().st_mtime


# ── Figure generation (Task 3) ────────────────────────────────────────────────

def generate_html_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
) -> None:
    """Generate a self-contained vtk.js HTML figure using PyVista."""
    raise NotImplementedError("HTML figure generation: implemented in Task 3")


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> None:
    qmd_path = os.environ.get("QUARTO_DOCUMENT_PATH", "")
    output_format = os.environ.get("QUARTO_OUTPUT_FORMAT", "html")

    if not qmd_path or not Path(qmd_path).exists():
        print("[4dpaper] No QUARTO_DOCUMENT_PATH set — skipping.", file=sys.stderr)
        return

    text = Path(qmd_path).read_text()
    figures = parse_shortcodes(text)

    if not figures:
        print("[4dpaper] No 4d-image shortcodes found.", file=sys.stderr)
        return

    figures_dir = _project_root / "state" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    for fig in figures:
        fig_id = fig["id"]
        src = Path(fig["src"]) if Path(fig["src"]).is_absolute() else _project_root / fig["src"]
        field = fig["field"]
        time_spec = fig.get("time", "mid")

        if output_format in ("html", "html4", "html5"):
            out = figures_dir / f"{fig_id}.html"
            if is_cache_valid(out, src):
                print(f"[4dpaper] {fig_id}.html is up to date — skipping.", file=sys.stderr)
                continue
            print(f"[4dpaper] Generating {fig_id}.html …", file=sys.stderr)
            generate_html_figure(src, field, time_spec, out)

        elif output_format in ("pdf", "latex"):
            out = figures_dir / f"{fig_id}.png"
            if is_cache_valid(out, src):
                print(f"[4dpaper] {fig_id}.png is up to date — skipping.", file=sys.stderr)
                continue
            print(f"[4dpaper] PDF figures: run 'Export PDF' from the dashboard.", file=sys.stderr)


if __name__ == "__main__":
    main()
```

### Step 2.4 — Run tests to verify they pass

```bash
cd /Users/simaocastro/4Dpapers
.venv/bin/python -m pytest tests/test_extension.py -v 2>&1 | tail -20
```

Expected: **All 9 tests PASS**.

### Step 2.5 — Run all tests to check nothing broke

```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: **All 14 existing + 9 new = 23 tests PASS**.

### Step 2.6 — Commit

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_extension.py
git commit -m "feat: add shortcode parser and cache check to 4dpaper pre-render hook"
```

---

## Task 3 — `4dpaper.py`: HTML figure generation

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py`
- Modify: `tests/test_extension.py`

### Step 3.1 — Add smoke test for `generate_html_figure`

Append to `tests/test_extension.py`:

```python
class TestGenerateHtmlFigure:
    def test_creates_html_file(self, tmp_path):
        """Smoke test: verify generate_html_figure creates a non-empty .html file."""
        mod = _load_4dpaper()
        case_path = Path(
            "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam"
        )
        if not case_path.exists():
            pytest.skip("Niederer case not available")

        out = tmp_path / "fig-vm.html"
        mod.generate_html_figure(
            src_path=case_path,
            field="Vm",
            time_spec="mid",
            output_path=out,
        )
        assert out.exists(), "Output HTML file was not created"
        assert out.stat().st_size > 1000, "Output HTML is suspiciously small"
        content = out.read_text()
        assert "<html" in content.lower() or "<!DOCTYPE" in content.lower() or "vtk" in content.lower()
```

### Step 3.2 — Run to verify it fails

```bash
.venv/bin/python -m pytest tests/test_extension.py::TestGenerateHtmlFigure -v 2>&1 | tail -10
```

Expected: `NotImplementedError: HTML figure generation: implemented in Task 3`

### Step 3.3 — Implement `generate_html_figure` in `4dpaper.py`

Find the `generate_html_figure` function stub and replace it with:

```python
def generate_html_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
) -> None:
    """
    Generate a self-contained vtk.js HTML figure using PyVista.

    Uses PyVista's Plotter.export_html() which produces a standalone
    file powered by panel + trame — no server required to view.
    """
    import pyvista as pv
    from scripts.data_loader import SimulationData

    sim = SimulationData(str(src_path)).load()

    # Resolve time step index
    n = sim.n_steps
    if time_spec == "first":
        idx = 0
    elif time_spec == "last":
        idx = max(0, n - 1)
    else:  # "mid" or numeric string
        try:
            idx = int(time_spec)
        except ValueError:
            idx = n // 2

    mesh = sim.get_mesh(idx)
    if mesh is None:
        raise RuntimeError(f"[4dpaper] Could not load mesh at step {idx} from {src_path}")

    surface = mesh.extract_surface()

    pl = pv.Plotter(off_screen=True, window_size=(900, 600))
    pl.background_color = "#1a1a2e"

    if field and (field in surface.point_data or field in surface.cell_data):
        pl.add_mesh(
            surface,
            scalars=field,
            cmap="coolwarm",
            smooth_shading=True,
            scalar_bar_args={"title": field},
        )
    else:
        # Field not available — render geometry in grey
        pl.add_mesh(surface, color="#aaaaaa", opacity=0.9)
        print(
            f"[4dpaper] Warning: field '{field}' not found in mesh — rendering geometry only.",
            file=sys.stderr,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.export_html(str(output_path))
    print(f"[4dpaper] Generated: {output_path}", file=sys.stderr)
```

### Step 3.4 — Run smoke test

```bash
.venv/bin/python -m pytest tests/test_extension.py::TestGenerateHtmlFigure -v -s 2>&1 | tail -15
```

Expected: **PASS** — HTML file created, size > 1 KB.

If `export_html` fails due to missing display (headless), try:
```bash
.venv/bin/python -c "
import pyvista as pv
pv.global_theme.background = 'white'
pl = pv.Plotter(off_screen=True)
pl.add_mesh(pv.Sphere())
pl.export_html('/tmp/test_pv.html')
import os; print('size:', os.path.getsize('/tmp/test_pv.html'))
"
```
If this also fails, install `pythreejs`: `.venv/bin/pip install pythreejs` and retry.

### Step 3.5 — Run all tests

```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: **All tests PASS** (23 + 1 = 24 tests).

### Step 3.6 — Commit

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_extension.py
git commit -m "feat: implement HTML figure generation via PyVista export_html"
```

---

## Task 4 — Lua shortcode `shortcodes.lua`

**Files:**
- Modify: `_extensions/4dpaper/shortcodes.lua`

> **Note:** There is no automated test for Lua code. Verification is done by running `quarto render` and inspecting the output HTML.

### Step 4.1 — Replace the stub with the full implementation

Replace the entire content of `_extensions/4dpaper/shortcodes.lua`:

```lua
--[[
4DPaper shortcode handler.

Usage in .qmd:
  {{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}
  {{< 4d-image src="case.foam" field="activationTime" id="fig-at" time="last" caption="Activation time" >}}

HTML output: embeds state/figures/<id>.html as raw HTML block (interactive vtk.js)
PDF output:  embeds state/figures/<id>.png as a standard Markdown image
--]]

local function fourd_image(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-image: missing required attribute <code>id</code></div>')
  end

  -- ── HTML output: embed self-contained vtk.js widget ───────────────────────
  if quarto.doc.isFormat("html") then
    local fig_path = "state/figures/" .. id .. ".html"
    local f = io.open(fig_path, "r")
    if f then
      local content = f:read("*all")
      f:close()
      -- Wrap in a figure div for styling
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure">\n' ..
        content .. "\n" ..
        (caption ~= "" and ('<figcaption>' .. caption .. '</figcaption>\n') or "") ..
        '</figure>')
    else
      -- Placeholder shown when figure has not been generated yet
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;' ..
        'border-radius:4px;margin:1rem 0">' ..
        '<strong>⚠ 4D Figure not yet rendered</strong><br>' ..
        'Figure ID: <code>' .. id .. '</code><br>' ..
        '<small>Click <strong>Rebuild HTML</strong> in the dashboard to generate.</small>' ..
        '</div>')
    end

  -- ── PDF / LaTeX output: embed pre-rendered PNG ────────────────────────────
  else
    local fig_path = "state/figures/" .. id .. ".png"
    local f = io.open(fig_path, "r")
    if f then
      f:close()
      local img = pandoc.Image(caption, fig_path, id)
      return pandoc.Para({img})
    else
      return pandoc.Para({
        pandoc.Str("[Figure "),
        pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
  end
end

return {
  ["4d-image"] = fourd_image,
}
```

### Step 4.2 — Add a `{{< 4d-image >}}` shortcode to `analysis_report.qmd` for testing

Find the existing `## Pass 1: Volumetric Activation` section. Directly below the section heading and above the `check-render-output` Python cell, insert one line:

```markdown
{{< 4d-image src="/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam" field="Vm" id="fig-vm" caption="Transmembrane potential Vm at mid-activation" >}}
```

### Step 4.3 — Verify shortcode renders (no-execute to check Lua only)

```bash
cd /Users/simaocastro/4Dpapers
quarto render analysis_report.qmd --no-execute 2>&1 | tail -5
```

Expected: `Output created: _output/analysis_report.html`
The placeholder div (not-yet-rendered message) should appear where the shortcode is. No Lua errors.

```bash
grep -o "4D Figure not yet rendered\|fourd-figure" _output/analysis_report.html | head -3
```

Expected: `4D Figure not yet rendered` (placeholder shown since `state/figures/fig-vm.html` doesn't exist yet).

### Step 4.4 — Generate the figure and re-render to verify embed

```bash
# Manually invoke the pre-render hook for HTML
QUARTO_DOCUMENT_PATH=/Users/simaocastro/4Dpapers/analysis_report.qmd \
QUARTO_OUTPUT_FORMAT=html \
.venv/bin/python _extensions/4dpaper/4dpaper.py
```

Expected output on stderr:
```
[4dpaper] Generating fig-vm.html …
[4dpaper] Generated: .../state/figures/fig-vm.html
```

Then re-render:
```bash
quarto render analysis_report.qmd --no-execute 2>&1 | tail -3
grep -o "fourd-figure\|vtk\|4D Figure not yet" _output/analysis_report.html | head -3
```

Expected: `fourd-figure` found (the figure div is now embedded, not the placeholder).

### Step 4.5 — Commit

```bash
git add _extensions/4dpaper/shortcodes.lua analysis_report.qmd
git commit -m "feat: implement 4d-image Lua shortcode with HTML/PDF path"
```

---

## Task 5 — Update `dashboard/pages/paper_page.py` (iframe + two buttons)

**Files:**
- Modify: `dashboard/pages/paper_page.py`
- Modify: `dashboard/app.py`
- Modify: `tests/test_pages.py`

### Step 5.1 — Update FAKE_CONFIG in `tests/test_pages.py`

The existing `FAKE_CONFIG` is missing the new keys added in Phase 2. Update it:

Find:
```python
FAKE_CONFIG = {
    "cardiacfoam_root": "/fake/cf",
    "quarto_paper_path": "/fake/paper.qmd",
    "tutorials": {
```

Replace with:
```python
FAKE_CONFIG = {
    "cardiacfoam_root": "/fake/cf",
    "quarto_paper_path": "/fake/paper.qmd",
    "camera_state": "",
    "render_output": "",
    "paraview": {},
    "tutorials": {
```

### Step 5.2 — Run existing page tests to confirm they still pass

```bash
.venv/bin/python -m pytest tests/test_pages.py -v 2>&1 | tail -10
```

Expected: **3 PASS**.

### Step 5.3 — Rewrite `paper_page.py`

Replace the entire content of `dashboard/pages/paper_page.py` with:

```python
"""Paper tab: iframe preview + Rebuild HTML + Export PDF."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import panel as pn
import param

from dashboard.utils import run_pvpython_render, run_quarto_render


class PaperPage(param.Parameterized):
    is_building = param.Boolean(default=False)

    def __init__(self, config: dict[str, Any], **params):
        super().__init__(**params)
        self._config = config
        self._qmd_path = Path(config["quarto_paper_path"])
        self._log_lines: list[str] = []

        # ── Buttons ──────────────────────────────────────────────────────────
        self._rebuild_html_btn = pn.widgets.Button(
            name="⚙  Rebuild HTML",
            button_type="primary",
            width=180,
        )
        self._export_pdf_btn = pn.widgets.Button(
            name="📥  Export PDF",
            button_type="default",
            width=180,
        )

        # ── Status + log ─────────────────────────────────────────────────────
        self._status_badge = pn.pane.Alert(
            "No build yet. Click 'Rebuild HTML' to render the paper.",
            alert_type="info",
            sizing_mode="stretch_width",
        )
        self._log_pane = pn.pane.Str(
            "",
            styles={
                "font-family": "monospace", "font-size": "11px",
                "overflow-y": "auto", "max-height": "200px",
                "background": "#1e1e1e", "color": "#d4d4d4",
                "padding": "8px", "border-radius": "4px",
            },
            sizing_mode="stretch_width",
        )

        # ── Iframe ───────────────────────────────────────────────────────────
        self._iframe = pn.pane.HTML(
            '<div style="border:1px dashed #ccc;padding:2rem;text-align:center;color:#888">'
            'Paper preview will appear here after first build.</div>',
            min_height=750,
            sizing_mode="stretch_width",
        )

        # ── PDF download link ─────────────────────────────────────────────────
        self._pdf_link = pn.pane.HTML("", sizing_mode="stretch_width")

        self._rebuild_html_btn.on_click(self._on_rebuild_html)
        self._export_pdf_btn.on_click(self._on_export_pdf)

    # ── HTML rebuild ──────────────────────────────────────────────────────────

    def _on_rebuild_html(self, event) -> None:
        if self.is_building:
            return
        self.is_building = True
        self._rebuild_html_btn.disabled = True
        self._export_pdf_btn.disabled = True
        self._log_lines.clear()
        self._status_badge.object = "Building HTML paper…"
        self._status_badge.alert_type = "warning"
        self._pdf_link.object = ""

        def _run() -> None:
            self._log_lines.append("[INFO] Running quarto render --to html…")
            pn.state.execute(self._refresh_log)
            code = run_quarto_render(self._qmd_path, self._log_lines)
            pn.state.execute(lambda: self._finish_html(code))

        threading.Thread(target=_run, daemon=True).start()
        pn.state.add_periodic_callback(self._refresh_log, period=500, count=120)

    def _finish_html(self, exit_code: int) -> None:
        self.is_building = False
        self._rebuild_html_btn.disabled = False
        self._export_pdf_btn.disabled = False
        self._log_pane.object = "\n".join(self._log_lines)

        if exit_code == 0:
            self._status_badge.object = "✓ HTML paper built successfully!"
            self._status_badge.alert_type = "success"
            # Refresh iframe with cache-busting timestamp
            ts = int(time.time())
            self._iframe.object = (
                f'<iframe src="/output/analysis_report.html?t={ts}" '
                f'width="100%" height="750px" frameborder="0" '
                f'style="border:none;border-radius:4px;"></iframe>'
            )
        else:
            self._status_badge.object = f"✗ Build failed (exit code {exit_code}). See log."
            self._status_badge.alert_type = "danger"

    # ── PDF export ────────────────────────────────────────────────────────────

    def _on_export_pdf(self, event) -> None:
        if self.is_building:
            return
        self.is_building = True
        self._rebuild_html_btn.disabled = True
        self._export_pdf_btn.disabled = True
        self._log_lines.clear()
        self._status_badge.object = "Checking for camera state…"
        self._status_badge.alert_type = "warning"
        self._pdf_link.object = ""

        cfg = self._config
        camera_path = Path(cfg.get("camera_state", ""))
        pv_cfg = cfg.get("paraview", {})

        def _run() -> None:
            # Step 1: pvpython figure render (requires camera state)
            if camera_path and camera_path.exists() and pv_cfg:
                self._log_lines.append("[INFO] Camera state found — rendering PDF figures…")
                pn.state.execute(self._refresh_log)

                from pathlib import Path as _Path
                figures_dir = _Path(__file__).parent.parent.parent / "state" / "figures"
                figures_dir.mkdir(parents=True, exist_ok=True)

                # Re-use camera render for the main figure (fig-vm → render_output.png)
                render_output = _Path(cfg.get("render_output", str(figures_dir / "fig-vm.png")))
                exit_code = run_pvpython_render(
                    pvpython_path=pv_cfg.get("pvpython_path", "pvpython"),
                    pvsm_path=pv_cfg.get("pvsm_path", ""),
                    foam_path=pv_cfg.get("foam_path", ""),
                    camera_state_path=camera_path,
                    output_path=render_output,
                    resolution=pv_cfg.get("render_resolution", [1920, 1080]),
                    log_lines=self._log_lines,
                )
                # Copy render output to state/figures/fig-vm.png for shortcode lookup
                if exit_code == 0 and render_output != figures_dir / "fig-vm.png":
                    import shutil
                    shutil.copy2(render_output, figures_dir / "fig-vm.png")

                if exit_code != 0:
                    pn.state.execute(lambda: self._finish_pdf(exit_code, None))
                    return
                self._log_lines.append("[INFO] PDF figures rendered.")
            else:
                self._log_lines.append(
                    "[WARN] No camera state — PDF figures will show placeholder text."
                )

            # Step 2: quarto render --to pdf
            self._log_lines.append("[INFO] Running quarto render --to pdf…")
            pn.state.execute(self._refresh_log)
            exit_code = run_quarto_render(
                self._qmd_path, self._log_lines, output_format="pdf"
            )
            pdf_path = self._qmd_path.parent / "_output" / "analysis_report.pdf"
            pn.state.execute(lambda: self._finish_pdf(exit_code, pdf_path))

        threading.Thread(target=_run, daemon=True).start()
        pn.state.add_periodic_callback(self._refresh_log, period=500, count=120)

    def _finish_pdf(self, exit_code: int, pdf_path) -> None:
        self.is_building = False
        self._rebuild_html_btn.disabled = False
        self._export_pdf_btn.disabled = False
        self._log_pane.object = "\n".join(self._log_lines)

        if exit_code == 0 and pdf_path and Path(pdf_path).exists():
            self._status_badge.object = "✓ PDF exported successfully!"
            self._status_badge.alert_type = "success"
            self._pdf_link.object = (
                f'<a href="file://{pdf_path}" target="_blank" style="font-size:1rem;">'
                f'📄 Open analysis_report.pdf</a>'
            )
        else:
            self._status_badge.object = f"✗ PDF export failed (exit code {exit_code}). See log."
            self._status_badge.alert_type = "danger"

    # ── Shared ────────────────────────────────────────────────────────────────

    def _refresh_log(self) -> None:
        self._log_pane.object = "\n".join(self._log_lines)

    def layout(self) -> pn.Column:
        return pn.Column(
            pn.pane.Markdown("### 4D Paper"),
            pn.Row(self._rebuild_html_btn, self._export_pdf_btn),
            self._status_badge,
            self._iframe,
            self._pdf_link,
            pn.layout.Divider(),
            pn.widgets.Toggle(
                name="Show build log", value=False
            ),
            pn.bind(
                lambda show: self._log_pane if show else pn.pane.HTML(""),
                pn.widgets.Toggle(name="Show build log", value=False),
            ),
            self._log_pane,
            sizing_mode="stretch_width",
        )


def build_paper_page(config: dict[str, Any]) -> pn.Column:
    page = PaperPage(config=config)
    return page.layout()
```

### Step 5.4 — Add `output_format` parameter to `run_quarto_render` in `utils.py`

The PDF export needs `quarto render --to pdf`. Open `dashboard/utils.py` and update `run_quarto_render`:

Find:
```python
def run_quarto_render(qmd_path: Path, log_lines: list[str]) -> int:
```

Replace the signature and command list with:
```python
def run_quarto_render(qmd_path: Path, log_lines: list[str], output_format: str = "html") -> int:
    """
    Run `quarto render <qmd_path> --to <output_format>`.
    Streams output to *log_lines*. Returns the process exit code.
    """
    import os
    import subprocess
    import threading

    env = os.environ.copy()
    env["QUARTO_PYTHON"] = sys.executable
    # Prepend .venv/bin to PATH so the pre-render hook finds the right Python
    venv_bin = str(Path(__file__).parent.parent / ".venv" / "bin")
    env["PATH"] = venv_bin + ":" + env.get("PATH", "")

    proc = subprocess.Popen(
        ["quarto", "render", str(qmd_path), "--to", output_format],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(qmd_path.parent),
        env=env,
    )
```

Keep the rest of the function body identical (thread, wait, return).

### Step 5.5 — Add `--static-dirs` launch comment to `app.py`

Open `dashboard/app.py`. Find the module docstring:

```python
"""
4Dpaper Dashboard — main Panel app.

Launch with:
    panel serve dashboard/app.py --show --port 5006
from the 4Dpapers repository root.
"""
```

Replace with:
```python
"""
4Dpaper Dashboard — main Panel app.

Launch with:
    panel serve dashboard/app.py --plugins dashboard.camera_plugin --static-dirs output=_output --show --port 5006
from the 4Dpapers repository root.

The --static-dirs flag makes _output/ available at /output/ so the
paper iframe can embed the rendered HTML at /output/analysis_report.html.
"""
```

### Step 5.6 — Run page tests

```bash
.venv/bin/python -m pytest tests/test_pages.py -v 2>&1 | tail -10
```

Expected: **3 PASS**.

### Step 5.7 — Run all tests

```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: **All tests PASS**.

### Step 5.8 — Commit

```bash
git add dashboard/pages/paper_page.py dashboard/utils.py dashboard/app.py tests/test_pages.py
git commit -m "feat: add iframe preview and split Rebuild HTML / Export PDF buttons"
```

---

## Task 6 — Clean `analysis_report.qmd` + end-to-end verification

**Files:**
- Modify: `analysis_report.qmd`

### Step 6.1 — Strip `analysis_report.qmd` to a clean user template

The current QMD has ~700 lines of hardcoded cardiac EP theory. Replace the entire file with a clean template that demonstrates the extension:

```markdown
---
title: "Cardiac Electrophysiology Analysis"
subtitle: "Niederer et al. (2012) Benchmark"
author:
  - name: "Your Name"
    affiliation: "Your Institution"
date: today
abstract: |
  Replace this with your abstract. This paper uses the 4DPaper extension
  to embed interactive 3D simulation visualisations directly in the HTML
  output, and high-resolution static figures in the PDF export.
format:
  html:
    self-contained: true
    embed-resources: true
    code-fold: true
    toc: true
    toc-depth: 3
    theme:
      light: cosmo
      dark: darkly
  pdf:
    keep-tex: false
params:
  case_path: "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam"
  reports_dir: "/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/postProcessing"
jupyter: python3
---

# Introduction

Write your introduction here. Use standard Markdown and Quarto syntax.
You can include equations with LaTeX:

$$
\frac{\partial V_m}{\partial t} = \nabla \cdot (\mathbf{D} \nabla V_m) - \frac{I_{ion}}{C_m}
$$

# Simulation Setup

Describe your simulation setup here.

# Results

## Transmembrane Potential

The figure below shows the transmembrane potential $V_m$ at mid-activation.
In the HTML version this is a fully interactive 3D viewer — you can rotate,
zoom, and inspect the mesh. In the PDF version it is a high-resolution static
render from the camera angle you locked in the dashboard.

{{< 4d-image src="/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam" field="Vm" id="fig-vm" caption="Transmembrane potential $V_m$ at mid-activation" >}}

## Activation Time

{{< 4d-image src="/Users/simaocastro/cardiacFoamEP/tutorials/NiedererEtAl2012/Niederer.foam" field="activationTime" id="fig-at" time="last" caption="Activation time distribution" >}}

## Post-Processing Results

```{python}
#| label: load-postproc
#| echo: false
#| output: asis
import json
from pathlib import Path

try:
    reports_dir = Path(params["reports_dir"])
    manifest_path = reports_dir / "plots.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for artifact in manifest.get("artifacts", []):
            label = artifact.get("label", artifact["path"])
            path = reports_dir / artifact["path"]
            if path.suffix == ".html":
                from IPython.display import display, IFrame
                display(IFrame(str(path), width="100%", height="500px"))
            elif path.suffix in (".png", ".jpg"):
                from IPython.display import display, Image
                display(Image(str(path)))
    else:
        print("> No post-processing results found yet. Run scripts from the Run tab.")
except NameError:
    print("> params not available in this context.")
```

# Conclusion

Write your conclusions here.
```

### Step 6.2 — Verify QMD structure (no-execute)

```bash
cd /Users/simaocastro/4Dpapers
quarto render analysis_report.qmd --no-execute 2>&1 | tail -5
```

Expected: `Output created: _output/analysis_report.html`

### Step 6.3 — Run all tests

```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: **All tests PASS**.

### Step 6.4 — Smoke-test dashboard startup

```bash
.venv/bin/python -c "
from dashboard.app import create_app
app = create_app()
print('Dashboard startup: OK')
" 2>&1
```

Expected: `Dashboard startup: OK`

### Step 6.5 — Manually test the pre-render hook

```bash
cd /Users/simaocastro/4Dpapers
QUARTO_DOCUMENT_PATH=/Users/simaocastro/4Dpapers/analysis_report.qmd \
QUARTO_OUTPUT_FORMAT=html \
.venv/bin/python _extensions/4dpaper/4dpaper.py
```

Expected:
```
[4dpaper] Generating fig-vm.html …
[4dpaper] Generated: .../state/figures/fig-vm.html
[4dpaper] Generating fig-at.html …
[4dpaper] Generated: .../state/figures/fig-at.html
```

Then verify the figures exist:
```bash
ls -lh state/figures/
```

Expected: `fig-vm.html` and `fig-at.html`, each > 100 KB.

### Step 6.6 — Full render with figures

```bash
quarto render analysis_report.qmd 2>&1 | tail -5
```

Expected: `Output created: _output/analysis_report.html`

Open `_output/analysis_report.html` in a browser and confirm the interactive 3D figures appear in the Results section.

### Step 6.7 — Commit

```bash
git add analysis_report.qmd
git commit -m "feat: replace hardcoded demo with clean 4dpaper template using shortcodes"
```

### Step 6.8 — Final git log

```bash
git log --oneline -8
```

Expected:
```
feat: replace hardcoded demo with clean 4dpaper template using shortcodes
feat: add iframe preview and split Rebuild HTML / Export PDF buttons
feat: implement 4d-image Lua shortcode with HTML/PDF path
feat: implement HTML figure generation via PyVista export_html
feat: add shortcode parser and cache check to 4dpaper pre-render hook
chore: add 4dpaper extension scaffold with stub shortcode and pre-render hook
```

---

## Summary Table

| Task | Files changed | Key outcome |
|------|--------------|-------------|
| 1 | `_extensions/4dpaper/`, `_quarto.yml`, `.gitignore` | Extension scaffold; Quarto calls pre-render hook |
| 2 | `4dpaper.py`, `tests/test_extension.py` | Shortcode parser + cache check (TDD, 9 tests) |
| 3 | `4dpaper.py`, `tests/test_extension.py` | HTML figure generation via PyVista `export_html` |
| 4 | `shortcodes.lua`, `analysis_report.qmd` | Lua shim embeds HTML widget or PNG per output format |
| 5 | `paper_page.py`, `utils.py`, `app.py` | Iframe preview; Rebuild HTML + Export PDF buttons |
| 6 | `analysis_report.qmd` | Clean user template with `{{< 4d-image >}}` shortcodes |

---

## Troubleshooting

**`Plotter.export_html()` fails with `No module named 'pythreejs'`**
```bash
.venv/bin/pip install pythreejs
```

**`Plotter.export_html()` produces a blank/empty file**
PyVista `export_html` uses Panel's trame backend. Ensure `panel`, `trame`, `trame-vtk`, `trame-vuetify` are all installed:
```bash
.venv/bin/pip install panel trame trame-vtk trame-vuetify
```

**Iframe shows "refused to connect"**
The dashboard must be started with `--static-dirs output=_output`:
```bash
panel serve dashboard/app.py --plugins dashboard.camera_plugin --static-dirs output=_output --show --port 5006
```

**Pre-render hook not called by Quarto**
Verify `_quarto.yml` has the `pre-render:` line and the file is executable (`chmod +x`). Check with:
```bash
quarto render analysis_report.qmd 2>&1 | grep "4dpaper"
```

**`{{< 4d-image >}}` shows "missing required attribute id"**
All three attributes `src`, `field`, `id` must be quoted: `field="Vm"` not `field=Vm`.
