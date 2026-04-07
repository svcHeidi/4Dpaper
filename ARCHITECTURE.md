# 4DPaper Architecture

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          User Browser                              │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
                    http://localhost:5006
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    serve.py (Tornado + Panel)                       │
├─────────────────────────────────────────────────────────────────────┤
│  Root Handler (/)                                                   │
│  └─ Serves: dashboard/static/index.html                            │
│                                                                      │
│  Asset Handler (/assets/*)                                          │
│  └─ Serves: CSS, JS, images from dashboard/static/                 │
│                                                                      │
│  API Routes (from dashboard/plugins.py)                             │
│  ├─ GET  /api/files                    → FilesHandler              │
│  ├─ GET  /api/file?path=X             → FileHandler               │
│  ├─ POST /api/compile                 → CompileHandler            │
│  ├─ POST /api/export                  → ExportHandler             │
│  ├─ POST /camera/<fig_id>             → CameraHandler             │
│  ├─ GET/POST /camera-lock/<fig_id>    → CameraLockHandler         │
│  ├─ GET  /state/*                     → Static files (state/)     │
│  └─ GET  /output/*                    → Static files (_output/)   │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     Backend Handlers                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  FilesHandler (camera_plugin.py:101)                                │
│  └─ Lists: *.qmd, *.bib, *.yml, *.py files from project root      │
│                                                                      │
│  FileHandler (camera_plugin.py:127)                                 │
│  └─ Reads: Single file content (with path traversal protection)   │
│                                                                      │
│  CompileHandler (camera_plugin.py:169)                              │
│  ├─ Saves: Files from frontend                                     │
│  ├─ Runs: quarto render --to html                                  │
│  └─ Returns: Compiled HTML content                                 │
│                                                                      │
│  ExportHandler (camera_plugin.py:233)                               │
│  ├─ Runs: quarto render --to pdf                                   │
│  └─ Returns: PDF binary (application/pdf)                          │
│                                                                      │
│  CameraHandler, CameraLockHandler (camera_plugin.py:24, 61)        │
│  └─ Syncs: vtk.js figure camera positions (state/camera_*.json)   │
│                                                                      │
│  ColorPlugin, FieldPlugin, UploadPlugin                             │
│  └─ Extended functionality for interactive figures                 │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
        ┌──────────────────────┴──────────────────────┐
        ↓                                             ↓
┌──────────────────────────┐            ┌──────────────────────────┐
│   Quarto Renderer        │            │   File System            │
├──────────────────────────┤            ├──────────────────────────┤
│ quarto render            │            │ _output/                 │
│  --to html               │            │ ├─ analysis_report.html  │
│  --to pdf                │            │ └─ analysis_report.pdf   │
│                          │            │                          │
│ Uses: dashboard/utils.py │            │ state/                   │
│       run_quarto_render()│            │ ├─ camera_*.json         │
│                          │            │ └─ camera_*_lock.json    │
└──────────────────────────┘            └──────────────────────────┘
```

## Frontend Flow

```
dashboard/static/index.html
│
├─ Script: Tailwind CSS (CDN)
├─ Script: Phosphor Icons (CDN)
├─ Script: split-pane.js (local)
│  └─ Handles: Left/right pane resizing
│
└─ JavaScript API Calls
   │
   ├─ On page load:
   │  └─ GET /api/files → Load file tree
   │
   ├─ On file click:
   │  └─ GET /api/file?path=X → Load file content
   │
   ├─ On Compile button:
   │  └─ POST /api/compile (with files) → Get HTML → Show in preview
   │
   └─ On Export button:
      └─ POST /api/export → Get PDF → Trigger download
```

## File Organization

### ✅ Keep (Core System)
```
dashboard/
├─ __init__.py                    (package marker)
├─ camera_plugin.py               (API endpoints)
├─ plugins.py                      (route aggregation)
├─ utils.py                        (Quarto rendering)
├─ color_plugin.py                 (figure colors)
├─ field_plugin.py                 (field switching)
├─ upload_plugin.py                (file upload)
├─ config.yaml                     (settings)
└─ static/
   ├─ index.html                   (frontend UI)
   ├─ js/
   │  └─ split-pane.js             (pane resizing)
   └─ assets.py                    (optional)

serve.py                           (server entry)
```

### ❌ Delete (Old Panel UI)
```
dashboard/
├─ app.py                          (old Panel UI app)
├─ theme.py                        (Panel colors)
├─ editor_tabs.py                  (Panel tab logic)
├─ file_tree.py                    (Panel file tree)
├─ color_sidebar.py                (Panel color picker)
├─ controller.py                   (Panel controller)
├─ figure_state.py                 (Panel state - check usage)
├─ components/                     (Panel components)
├─ pages/                          (Panel pages)
│  ├─ paper_page.py                (Panel compile UI)
│  └─ settings_page.py             (Panel settings UI)
└─ static/assets.py                (Panel asset loader)

api_plugin.py                      (duplicate?)
```

### 🗑️ Delete (Old Worktrees)
```
.worktrees/
├─ frontend-refactor/              (previous attempt)
├─ panel-ide-3pane/                (previous Panel UI)
└─ feature/                         (experimental)
```

---

## Data Flow: Compile Button

```
1. User clicks "Compile" button in HTML
   │
   └─ JavaScript collects editor content:
      {
        "files": {
          "analysis_report.qmd": "---\ntitle: ...",
          "other.qmd": "..."
        }
      }

2. POST /api/compile with JSON body
   │
   └─ CompileHandler (camera_plugin.py:169)
      ├─ Saves files to disk (analysis_report.qmd, etc.)
      ├─ Calls: run_quarto_render(main_qmd, log_lines, output_format="html")
      │  └─ Subprocess: quarto render analysis_report.qmd --to html
      │     └─ Runs: _extensions/4dpaper/4dpaper.py (pre-render hook)
      │        └─ Generates: state/figures/*, _output/analysis_report.html
      ├─ Reads: _output/analysis_report.html
      └─ Returns: { "status": "success", "html": "..." }

3. HTML Preview pane updated
   └─ Shows: Compiled paper with embedded 3D figures
```

## Data Flow: Export to PDF

```
1. User clicks "Export" button in HTML
   │
   └─ POST /api/export (no body)

2. ExportHandler (camera_plugin.py:233)
   ├─ Calls: run_quarto_render(main_qmd, log_lines, output_format="pdf")
   │  └─ Subprocess: quarto render analysis_report.qmd --to pdf
   │     └─ Runs: _extensions/4dpaper/4dpaper.py (pre-render hook)
   │        └─ Reads: state/camera_*.json (for figure viewpoints)
   │        └─ Generates: state/figures/*.png (static renders)
   │        └─ Creates: _output/analysis_report.pdf (with embedded PNGs)
   ├─ Reads: _output/analysis_report.pdf (bytes)
   └─ Returns: PDF binary (application/pdf)

3. Browser downloads PDF
   └─ Filename: analysis_report.pdf
```

---

## API Contract Reference

See `API_CONTRACTS.md` for detailed request/response formats.

Quick summary:
```
GET /api/files
  ↓
  ├─ Success: 200, {"files": ["file1.qmd", ...]}
  └─ Error: 500, {"error": "..."}

GET /api/file?path=X
  ↓
  ├─ Success: 200, text/plain (file content)
  ├─ Error 400: {"error": "path parameter required"}
  ├─ Error 403: {"error": "Access denied"}
  ├─ Error 404: {"error": "File not found"}
  └─ Error 500: {"error": "..."}

POST /api/compile
  ↓
  ├─ Success: 200, {"status": "success", "html": "..."}
  └─ Error: 500, {"error": "Compilation failed", "log": "..."}

POST /api/export
  ↓
  ├─ Success: 200, application/pdf (binary)
  └─ Error: 500, {"error": "PDF export failed", "log": "..."}
```

---

## Performance Notes

- **HTML Frontend:** 100% client-side, no server rendering
- **API Calls:** Async, non-blocking JavaScript
- **Quarto Render:** Runs in subprocess, logs streamed to frontend (future)
- **File Operations:** Read/write via Python, sanitized paths
- **Camera Sync:** Light JSON files (< 1KB each)

---

## Future Optimizations

1. **Streaming Logs:** WebSocket for real-time compile progress
2. **File Watching:** Auto-rebuild on save
3. **Diff Viewer:** Show changes between versions
4. **Multi-tab Editing:** Full workspace management
5. **Theme Switcher:** Light/dark mode toggle
