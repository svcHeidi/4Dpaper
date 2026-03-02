# 4DPaper Extension + App Redesign

**Date:** 2026-03-02
**Status:** Approved

---

## Problem

The current `analysis_report.qmd` is a hardcoded demo paper full of pre-written cardiac EP theory and hardwired paths. The dashboard Paper tab has only a rebuild button — no live preview. There is no way for a user to write their own paper and drop in 4D interactive figures.

---

## Goal

A plugin/extension model where:

1. The user writes their paper externally (VS Code, any editor) as a `.qmd` file — just like LaTeX.
2. Wherever they want a live 3D figure, they write a single shortcode: `{{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}`
3. In HTML output (shared 4D paper): the figure is a fully interactive vtk.js 3D viewer.
4. In PDF output (print/download): the figure is a high-res static PNG baked from the camera angle the user locked.
5. The dashboard Paper tab shows an iframe of the live HTML — the user sees interactive figures immediately. PDF export is a separate action.

---

## Two-Tier Model

### Tier 1 — Extension only (no dashboard required)

```bash
quarto add 4dpaper/4dpaper     # one-time install
quarto preview paper.qmd       # live interactive HTML, 3D figures active
quarto render paper.qmd        # builds self-contained interactive HTML
```

User shares the `.html` file — recipient gets the full interactive 4D paper in any browser.

### Tier 2 — Full app (adds Panel dashboard)

```bash
panel serve dashboard/app.py --show
```

Adds: live iframe preview, Rebuild HTML button, Export PDF button with camera-locked render.

---

## Architecture

```
User writes paper.qmd
  └─ {{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}

quarto render / quarto preview
  └─ Pre-render hook: _extensions/4dpaper/4dpaper.py (runs before Quarto)
       ├─ HTML output → state/figures/fig-vm.html  (self-contained vtk.js)
       └─ PDF output  → state/figures/fig-vm.png   (pvpython + saved camera)

Lua shortcode (~15 lines)
  ├─ HTML: reads state/figures/fig-vm.html → embeds as raw HTML block
  └─ PDF:  reads state/figures/fig-vm.png  → embeds as standard Markdown image

Dashboard Paper tab
  ├─ iframe → _output/analysis_report.html (auto-refreshes after rebuild)
  ├─ [Rebuild HTML] → 4dpaper.py (HTML figures) + quarto render --to html
  └─ [Export PDF]   → pvpython pre-render (camera) + quarto render --to pdf
```

---

## Shortcode API

```
{{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}
{{< 4d-image src="case.foam" field="activationTime" id="fig-at" time="last" >}}
{{< 4d-graph src="postProcessing/plots.json" id="fig-lines" >}}
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `src` | yes | Path to simulation file (`.foam`, `.vtu`, `.pvd`, directory) |
| `field` | yes | Scalar field name (`Vm`, `activationTime`, etc.) |
| `id` | yes | Unique figure ID — used as cache filename in `state/figures/` |
| `time` | no | Time step: `"mid"` (default), `"first"`, `"last"`, or index |
| `caption` | no | Figure caption text |
| `width` | no | Display width (default `100%`) |

---

## Files

### New files

```
_extensions/4dpaper/
  ├── _extension.yml       ← name: 4dpaper, contributes: shortcodes
  ├── shortcodes.lua       ← handles {{< 4d-image >}} and {{< 4d-graph >}}
  └── 4dpaper.py           ← pre-render hook: scans .qmd, generates figures

state/figures/             ← gitignored cache of generated figure files
  ├── fig-vm.html          ← self-contained vtk.js interactive widget
  └── fig-vm.png           ← high-res PNG for PDF (from pvpython)
```

### Modified files

| File | Change |
|------|--------|
| `_quarto.yml` | Add `execute-before: _extensions/4dpaper/4dpaper.py` |
| `analysis_report.qmd` | Strip hardcoded theory → clean user template with shortcodes |
| `dashboard/pages/paper_page.py` | Add iframe; split rebuild button into "Rebuild HTML" + "Export PDF" |
| `.gitignore` | Add `state/figures/` |

### Unchanged files

- `dashboard/paraview_render.py` — reused as-is for PDF figures
- `dashboard/utils.py` — camera helpers reused as-is
- `dashboard/pages/run_page.py`, `outputs_page.py`
- `scripts/data_loader.py`, `scripts/interactive_viz.py`
- `dashboard/config.yaml` structure

---

## Pre-render Hook (`4dpaper.py`) Logic

```
1. Parse .qmd for all {{< 4d-image id="X" src="Y" field="Z" ... >}} calls
2. Determine output format (html or pdf) from Quarto env vars
3. For each figure:
   a. Check if state/figures/X.{html,png} exists and is newer than src file
   b. If stale or missing:
      - HTML: load mesh via SimulationData → PyVista offscreen → export_html()
      - PDF:  check state/camera_state.json exists → run_pvpython_render()
4. Exit 0 (Quarto proceeds) or exit 1 with message (Quarto aborts with error)
```

---

## Shortcodes Lua Logic

```lua
-- HTML output
if quarto.doc.isFormat("html") then
  local fig_file = "state/figures/" .. id .. ".html"
  -- embed as raw HTML block
end

-- PDF / LaTeX output
if quarto.doc.isFormat("pdf") or quarto.doc.isFormat("latex") then
  local fig_file = "state/figures/" .. id .. ".png"
  -- emit as ![caption](fig_file)
end
```

---

## Dashboard Paper Tab Layout

```
┌─────────────────────────────────────────────────────┐
│  📄 Paper                                           │
│                                                     │
│  [⚙ Rebuild HTML]  [📥 Export PDF]                 │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │   iframe: _output/analysis_report.html      │   │
│  │   (interactive 3D figures live here)        │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ▼ Build log (collapsible)                         │
└─────────────────────────────────────────────────────┘
```

- **Rebuild HTML**: runs `4dpaper.py` (HTML figures) → `quarto render --to html` → iframe refreshes
- **Export PDF**: checks camera state → pvpython pre-render → `quarto render --to pdf` → download link

---

## What the User Experiences

1. Installs extension: `quarto add 4dpaper/4dpaper`
2. Writes their paper in any editor, drops `{{< 4d-image >}}` where figures go
3. Runs `quarto preview` — sees fully interactive 3D figures in the browser
4. Rotates to desired angle → clicks "Save Camera" in the live preview
5. In dashboard → "Export PDF" → gets high-res static PDF with locked-camera figures
6. Shares either the `.html` (interactive 4D paper) or the `.pdf` (static)
