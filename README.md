# 4DPaper

A paper authoring IDE for embedding interactive 3D figures and graphs into Quarto documents. Works across disciplines — CFD (OpenFOAM), FEA (Exodus/XDMF), geometry-heavy workflows (Blender `.obj`/`.ply`/`.stl`), and any other dataset readable by PyVista. Produces interactive HTML output and high-quality static figures for PDF.

## Quick Start

### Prerequisites
- Python 3.10+
- Quarto (`quarto --version` to check)
- Project virtual environment (`.venv/`)

### Run the Dashboard

```bash
python serve.py
```

Then visit: **http://localhost:5006/**

### Setting Up Data Shortcuts

To decouple your paper code from simulation data and enable portability:

**Step 1: Configure shortcuts**
```bash
cp _shortcuts.example.yml _shortcuts.yml
```

Edit `_shortcuts.yml` with your data paths:
```yaml
shortcuts:
  sim_main:
    path: "/path/to/simulation/results"
    description: "Primary simulation case"
  test_data:
    path: "./test_data"  # relative paths are portable
    description: "Test cases"
```

**Step 2: Use shortcuts in `.qmd` files**
```markdown
{{< 4d-image src="@sim_main/Niederer.foam" field="Vm" id="fig-vm" >}}
{{< 4d-graph src="@test_data/results.json" id="fig-graph" >}}
```

**Step 3: View shortcuts in dashboard**
- Open dashboard (http://localhost:5006/)
- Look for "Shortcuts" section in left explorer panel
- Click any shortcut to copy `@name/` reference

**Benefits**:
- ✅ No hardcoded absolute paths
- ✅ Portable across machines (use relative paths)
- ✅ Auto-updates when HPC reruns data (via symlinks)
- ✅ Clean separation of code (git-tracked) and data (external)

See `SCHEMA_CONTRACT.md` (Section 0) for detailed shortcut syntax and examples.

## Architecture

**Frontend:** Static HTML + TailwindCSS (`dashboard/static/index.html`)
- File tree explorer
- Code editor with syntax highlighting
- Live preview of compiled paper
- Split-pane resizable layout

**Backend:** Tornado API + Quarto (`serve.py` + `dashboard/`)
- `GET /api/files` — List project files
- `GET /api/file?path=X` — Read file content
- `POST /api/compile` — Quarto HTML render
- `POST /api/export` — Quarto PDF export

**Figures:** vtk.js interactive 3D + static PNG
- Camera sync via JSON state files
- Colormap & field switching
- Embedded in HTML (interactive) or PDF (static)

See `ARCHITECTURE.md` for detailed diagrams and data flows.

## Project Structure

```
4Dpapers/
├─ serve.py                      Main server entry point
├─ analysis_report.qmd           Your paper document
├─ _quarto.yml                   Quarto config
├─ API_CONTRACTS.md              API endpoint specs
├─ ARCHITECTURE.md               System design
├─ CODEBASE_AUDIT.md             Code organization
│
├─ dashboard/
│  ├─ static/
│  │  ├─ index.html              Frontend UI
│  │  └─ js/split-pane.js        Pane resizing
│  │
│  ├─ camera_plugin.py           API handlers
│  ├─ plugins.py                 Route aggregation
│  ├─ utils.py                   Quarto rendering
│  ├─ config.yaml                Settings
│  │
│  └─ (plugin modules for interactive figures)
│     ├─ color_plugin.py         Colormap switching
│     ├─ field_plugin.py         Field switching
│     ├─ upload_plugin.py        File uploads
│     └─ figure_state.py          State helpers
│
├─ _extensions/
│  └─ 4dpaper/
│     ├─ 4dpaper.py              Pre-render hook
│     └─ shortcodes.lua          Embed logic
│
├─ state/                        Runtime state
│  ├─ figures/                   Generated HTML/PNG
│  ├─ camera_*.json              Figure viewpoints
│  └─ preview_*.json             Preview state
│
└─ _output/                      Build output
   ├─ analysis_report.html       Compiled paper (interactive)
   └─ analysis_report.pdf        Exported paper (static)
```

## Writing Papers

### Document Format

```markdown
---
title: "Your Paper Title"
subtitle: "Optional subtitle"
author:
  - name: "Your Name"
    affiliation: "Your Institution"
date: today
---

{{< include sections/introduction.qmd >}}

{{< 4d-image id="fig1"
             fields="Voltage,CellState,Calcium" >}}
```

### Add Interactive Figures

Use the `{{< 4d-image >}}` shortcode:
- `id` (required) — Unique figure identifier
- `fields` (optional) — Comma-separated field names to embed
- `time` (optional) — Default time step

Figures are generated from Python/ParaView and saved as:
- `state/figures/<id>.html` — Interactive vtk.js (HTML)
- `state/figures/<id>.png` — Static render (PDF)

## Commands

### Compile to HTML
```javascript
// Browser: Click "Compile" button
// Or API call:
fetch('/api/compile', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ files: { ... } })
})
```

### Export to PDF
```javascript
// Browser: Click "Export" button
// Or API call:
fetch('/api/export', { method: 'POST' })
```

### List Files
```bash
curl http://localhost:5006/api/files
```

### Read File
```bash
curl 'http://localhost:5006/api/file?path=analysis_report.qmd'
```

## Configuration

Edit `dashboard/config.yaml`:
```yaml
quarto_paper_path: analysis_report.qmd  # Main document path
```

## Development

### Modify Frontend
Edit `dashboard/static/index.html` and refresh the browser.

### Modify API
Edit handlers in `dashboard/camera_plugin.py` and restart `serve.py`.

### Extend Plugins
See `dashboard/color_plugin.py` or `dashboard/field_plugin.py` for examples.

## Troubleshooting

### "Quarto not found"
Install Quarto: https://quarto.org/docs/get-started/

### "File not found" when compiling
- Check `quarto_paper_path` in `dashboard/config.yaml`
- Verify file exists in project root

### 3D figures not rendering
- Check `state/figures/<id>.html` exists
- Verify vtk.js library is loading (browser console)
- Check camera state: `state/camera_<id>.json`

### PDF export fails
- Check PDF permissions: `_output/` is writable
- Verify Quarto PDF template is installed
- Check logs in export modal

## Internals

### Build Pipeline
```
analysis_report.qmd
    ↓
Quarto pre-render hook (_extensions/4dpaper/4dpaper.py)
    ├─ Parse {{< 4d-image >}} shortcodes
    ├─ Generate state/figures/<id>.html (trame export)
    ├─ Generate state/figures/<id>.png (ParaView render)
    └─ Apply camera from state/camera_<id>.json
    ↓
Pandoc (markdown → HTML/PDF)
    ├─ Embed figures via _extensions/4dpaper/shortcodes.lua
    └─ Generate _output/analysis_report.{html,pdf}
```

### Camera Sync
1. User rotates figure in HTML → vtk.js fires `mouseup` event
2. JavaScript calls `POST /camera/<fig_id>` with camera state
3. State saved to `state/camera_<fig_id>.json`
4. On PDF export, ParaView reads JSON → applies camera → renders PNG
5. Quarto embeds PNG in PDF

### File Editing
1. Frontend loads file list: `GET /api/files`
2. User clicks file: `GET /api/file?path=X`
3. User edits: `POST /api/compile` (saves files + renders)
4. Preview updates with compiled HTML

## API Reference

See `API_CONTRACTS.md` for full endpoint specifications.

## License

(Add your license here)

## Support

- **Issues:** Create a GitHub issue
- **Docs:** See `ARCHITECTURE.md`, `CODEBASE_AUDIT.md`
- **API:** See `API_CONTRACTS.md`
