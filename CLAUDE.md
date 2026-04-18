# 4Dpapers — Agent Reference

Machine-readable reference for AI agents working with this codebase.
Last updated: 2026-04-18

---

## 1. Project Purpose

4Dpapers is a paper authoring IDE used by researchers across multiple disciplines. Authors write Quarto Markdown (`.qmd`) files containing custom shortcodes that embed interactive 3D figures and graphs. A pre-render hook generates figure assets before Quarto compiles the paper to HTML or PDF.

The system is intentionally format-agnostic. Current user communities include:
- **CFD engineers** using OpenFOAM case data
- **FEA analysts** using Exodus (`.exo`) and XDMF/HDF5 outputs
- **Geometry / design workflows** using Blender exports (`.obj`, `.ply`, `.stl`)

Any dataset readable by PyVista can be embedded as an interactive figure. Do not assume OpenFOAM or CFD context when working on this codebase.

---

## 2. Repository Layout

```
4Dpapers/
├── _extensions/4dpaper/       # Quarto extension (pre-render hook + Lua shortcodes)
│   ├── 4dpaper.py             # Pre-render hook — generates all figure assets
│   ├── shortcodes.lua         # Lua filter — embeds figures into Quarto output
│   ├── shortcut_resolver.py   # @shortcut_name path resolution
│   └── assets/
│       └── relay.js           # postMessage relay: figure iframes → backend
├── dashboard/                 # Tornado web server plugins
│   ├── plugins.py             # Route aggregator (imported by Panel serve)
│   ├── camera_plugin.py       # Camera position + lock state endpoints
│   ├── compile_plugin.py      # Compile, PDF export, health-check endpoints
│   ├── color_plugin.py        # Colour preview state endpoints
│   ├── field_plugin.py        # Field/timestep state endpoints
│   ├── file_plugin.py         # File tree listing + single-file read/write
│   ├── shortcuts_plugin.py    # Shortcut CRUD endpoints
│   ├── upload_plugin.py       # Case upload + shortcode generation
│   └── utils.py               # save_camera_state, load_camera_state, run_quarto_render
├── scripts/
│   └── data_loader.py         # SimulationData — multi-format loader
├── state/                     # Runtime state (created at serve time, not committed)
│   ├── camera_<id>.json       # Saved camera position per figure
│   ├── camera_<id>_lock.json  # Lock state per figure
│   ├── field_<id>.json        # Active field/timestep per figure
│   ├── preview/
│   │   └── color_<id>.json    # Colour preview state per figure
│   └── figures/               # Generated figure assets
│       ├── <id>.html          # Interactive vtk.js figure (web)
│       └── <id>.png           # Static screenshot (PDF export)
├── _output/                   # Quarto compiled HTML output
├── data/                      # User data (OpenFOAM cases, VTK files, etc.)
├── _shortcuts.yml             # @shortcut_name definitions
├── _4dpaper_styles.yml        # Named style templates
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Container definition
├── serve.py                   # Panel serve entry point
└── tests/                     # pytest test suite
```

---

## 3. Shortcode Reference

All shortcodes are written inside `.qmd` files. Attribute values are always quoted strings. Shortcodes inside fenced code blocks (` ``` `) are ignored by the parser.

### 3.1 `4d-image` — Single interactive 3D figure

```
{{< 4d-image id="<id>" src="<src>" field="<field>" [options] >}}
```

| Attribute  | Required | Default  | Description |
|------------|----------|----------|-------------|
| `id`       | yes      | —        | Unique figure identifier. Used for all state file names. Must match `[A-Za-z0-9_-]+`. |
| `src`      | yes      | —        | Path to data file. Supports `@shortcut/subpath` syntax. Accepted formats: `.foam`, `.vtu`, `.vtp`, `.vtk`, `.pvd`, `.stl`, `.obj`, `.ply`, `.case`, `.cgns`, `.exo`, `.xdmf`. |
| `field`    | no       | `""`     | Scalar field name to colour the mesh (e.g. `"U"`, `"p"`, `"Vm"`). |
| `fields`   | no       | `""`     | Comma-separated list of fields available in the live field switcher (e.g. `"U,p,T"`). |
| `time`     | no       | `"mid"`  | Timestep selector: `"first"`, `"last"`, `"mid"`, or integer index. |
| `style`    | no       | `""`     | Named style template from `_4dpaper_styles.yml`. |
| `decimate` | no       | `"auto"` | Mesh decimation: `"auto"` (reduce if >150k faces), `"none"` / `"off"` (disabled), or a float ratio `"0.75"` (remove 75% of faces). |
| `caption`  | no       | `""`     | Figure caption. |

**Examples:**
```
{{< 4d-image id="fig-aorta" src="@hpc/aorta/case.foam" field="U" fields="U,p" time="last" >}}
{{< 4d-image id="fig-wall" src="data/wall.vtu" field="WSS" decimate="0.8" >}}
{{< 4d-image id="fig-geo" src="data/geometry.stl" decimate="none" >}}
```

**Output:** `state/figures/<id>.html` (interactive) + `state/figures/<id>.png` (PDF).

---

### 3.2 `4d-panel` — Multi-figure grid

```
{{< 4d-panel id="<id>" layout="<COLSxROWS>" src1="..." id1="..." [src2="..." id2="..."] [options] >}}
```

| Attribute       | Required | Default        | Description |
|-----------------|----------|----------------|-------------|
| `id`            | yes      | —              | Panel identifier. |
| `layout`        | no       | `"1x1"`        | Grid dimensions: columns × rows (e.g. `"2x2"`, `"3x1"`). |
| `height`        | no       | `"800px"`      | CSS height of the panel container. |
| `camera`        | no       | `"independent"` | Camera sync mode: `"independent"` or `"sync"` (all sub-figures mirror one camera). |
| `caption`       | no       | `""`           | Panel caption. |
| `src<n>`        | yes×n    | —              | Data source for sub-figure n (1-indexed). |
| `id<n>`         | no       | `"panel-sub-n"` | Identifier for sub-figure n. |
| `field<n>`      | no       | `""`           | Active field for sub-figure n. |
| `fields<n>`     | no       | `""`           | Switchable fields for sub-figure n. |
| `time<n>`       | no       | `"mid"`        | Timestep for sub-figure n. |

**Example:**
```
{{< 4d-panel id="comparison" layout="2x1" height="600px" camera="sync"
    src1="data/case_a.foam" id1="fig-a" field1="U"
    src2="data/case_b.foam" id2="fig-b" field1="U" >}}
```

---

### 3.3 `4d-timeseries` — Synchronised timestep panel

Expands into a `4d-panel` with `camera="sync"` where each sub-figure shows one timestep of the same simulation.

```
{{< 4d-timeseries id="<id>" src="<src>" field="<field>" [options] >}}
```

| Attribute | Required | Default  | Description |
|-----------|----------|----------|-------------|
| `id`      | yes      | —        | Panel identifier. Sub-figures get ids `<id>-0`, `<id>-1`, etc. |
| `src`     | yes      | —        | Data source (must have multiple timesteps). |
| `field`   | no       | `""`     | Scalar field to display. |
| `steps`   | no       | `"4"`    | Number of evenly-spaced timesteps to show (minimum 2). |
| `times`   | no       | `""`     | Explicit timestep indices, comma-separated (overrides `steps`). Accepts integers, `"first"`, `"last"`. |
| `height`  | no       | `"400px"` | CSS height of each sub-figure. |
| `caption` | no       | `""`     | Caption. |

**Example:**
```
{{< 4d-timeseries id="ts-flow" src="@hpc/case.foam" field="U" steps="6" >}}
{{< 4d-timeseries id="ts-selected" src="data/run.foam" field="p" times="0,5,10,last" >}}
```

---

### 3.4 `4d-graph` — Interactive Plotly graph

```
{{< 4d-graph id="<id>" src="<src>" [caption="<caption>"] >}}
```

| Attribute | Required | Default | Description |
|-----------|----------|---------|-------------|
| `id`      | yes      | —       | Figure identifier. |
| `src`     | yes      | —       | Path to a Plotly JSON file (output of `plotly.io.to_json(fig)`). |
| `caption` | no       | `""`    | Figure caption. |

The pre-render hook applies RDP polyline simplification (ε = 0.1% of normalised range) to every trace's `x`/`y` arrays before rendering.

**Example:**
```
{{< 4d-graph id="pressure-curve" src="data/pressure.json" caption="Aortic pressure over time" >}}
```

---

### 3.5 `4d-video` — Animated figure (MP4)

```
{{< 4d-video id="<id>" src="<src>" field="<field>" [options] >}}
```

| Attribute | Required | Default  | Description |
|-----------|----------|----------|-------------|
| `id`      | yes      | —        | Figure identifier. |
| `src`     | yes      | —        | Data source path. |
| `field`   | no       | `""`     | Scalar field to animate. |
| `fps`     | no       | `"10"`   | Frames per second. |
| `time`    | no       | `"mid"`  | Starting timestep. |

---

## 4. Source Path Syntax

All `src` attributes support two forms:

| Form | Example | Resolution |
|------|---------|------------|
| Relative path | `"data/case.foam"` | Relative to project root |
| Shortcut | `"@hpc_data/aorta/case.foam"` | `@name` resolved via `_shortcuts.yml` |

**`_shortcuts.yml` format:**
```yaml
shortcuts:
  hpc_data:
    path: /mnt/hpc/projects/myproject
    description: HPC project data directory
```

Shortcuts are managed via the dashboard (`GET/POST /api/shortcuts`) or by editing `_shortcuts.yml` directly.

---

## 5. Supported Data Formats

Handled by `scripts/data_loader.py` (`SimulationData` class):

| Extension(s) | Format | Notes |
|---|---|---|
| `.foam`, `.openfoam` | OpenFOAM | Auto-detects reconstructed vs. decomposed (parallel) |
| `.vtu` | VTK Unstructured Grid | Single timestep or time-step directory |
| `.vtp` | VTK PolyData | Surface mesh |
| `.vtk` | VTK Legacy | |
| `.pvd` | VTK Collection | Time-series metadata |
| `.stl`, `.obj`, `.ply` | Surface meshes | Static geometry, no scalar data |
| `.case` | EnSight Gold | Time-series |
| `.cgns` | CGNS | Time-series |
| `.exo`, `.e`, `.ex2` | Exodus II | FEA time-series |
| `.xdmf`, `.xmf` | XDMF/HDF5 | Companion `.h5` required |

---

## 6. State Files

All runtime state lives in `state/`. These files are created by user interaction in the browser and read by the pre-render hook on next compile.

| File | Written by | Read by | Purpose |
|------|-----------|---------|---------|
| `state/camera_<id>.json` | `POST /camera/<id>` | Pre-render hook | Saved camera position/orientation for PNG export and HTML initial view |
| `state/camera_<id>_lock.json` | `POST /camera-lock/<id>` | Browser JS | Whether the figure interactor is locked |
| `state/field_<id>.json` | `POST /field/<id>` | Pre-render hook | Active field name and timestep index |
| `state/preview/color_<id>.json` | `POST /color/<id>` | Dashboard UI | Colour range preview state |
| `state/figures/<id>.html` | Pre-render hook | Quarto/Lua | Interactive vtk.js figure |
| `state/figures/<id>.png` | Pre-render hook | WeasyPrint | Static screenshot for PDF |

**`state/camera_<id>.json` schema:**
```json
{
  "position":    [x, y, z],
  "focal_point": [x, y, z],
  "view_up":     [x, y, z],
  "parallel_scale": 0.05
}
```

**`state/field_<id>.json` schema:**
```json
{
  "field": "U",
  "time": "3"
}
```

---

## 7. Cache Invalidation

The pre-render hook (`4dpaper.py`) uses mtime-based caching. A cached figure is regenerated if any of the following is newer than `state/figures/<id>.html`:

- The source data file
- `state/camera_<id>.json` (camera moved)
- `state/field_<id>.json` (field or timestep changed)
- `_4dpaper_styles.yml` (style template changed)
- `4dpaper.py` itself (template code updated)

To force a full regeneration: `touch <src_file>` or delete `state/figures/`.

---

## 8. Backend REST API

All endpoints are served by the Panel/Tornado process on port 5006.

### 8.1 Camera (`dashboard/camera_plugin.py`)

| Method | Path | Body / Params | Response |
|--------|------|---------------|----------|
| `POST` | `/camera/<fig_id>` | `{position, focal_point, view_up, parallel_scale?}` | `{status: "ok"}` |
| `GET`  | `/camera-lock/<fig_id>` | — | `{locked: bool}` |
| `POST` | `/camera-lock/<fig_id>` | `{locked: bool}` | `{status: "ok"}` |

`fig_id` must match `[A-Za-z0-9_-]+`.

### 8.2 Field state (`dashboard/field_plugin.py`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| `GET`  | `/field/<fig_id>` | — | `{field: str, time: str}` |
| `POST` | `/field/<fig_id>` | `{field?: str, time?: str}` | `{status: "ok"}` |

### 8.3 Colour preview (`dashboard/color_plugin.py`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| `GET`  | `/color/<fig_id>` | — | `{vmin: float, vmax: float, cmap: str}` |
| `POST` | `/color/<fig_id>` | `{vmin: float, vmax: float, cmap?: str}` | `{status: "ok"}` |

### 8.4 Compile & export (`dashboard/compile_plugin.py`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST` | `/api/compile` | `{files?: {path: content}, format?: "html"\|"pdf"}` | `{status, filename, log}` |
| `POST` | `/api/export`  | `{}` | PDF bytes (`Content-Type: application/pdf`) |
| `GET`  | `/api/health`  | — | `{status, backend_ready, project_root, main_qmd, output_dir, state_dir}` |

`/api/compile` with `format="pdf"` renders the paperview Quarto profile (static HTML with saved-camera PNGs) then converts via WeasyPrint. `/api/export` does the same and streams the PDF directly.

### 8.5 File tree (`dashboard/file_plugin.py`)

| Method | Path | Body / Params | Response |
|--------|------|---------------|----------|
| `GET`  | `/api/files` | — | `{files: [{path, is_dir, size, type}], count}` |
| `GET`  | `/api/file?path=<rel>` | — | File content as `text/plain` |
| `POST` | `/api/file` | `{path: str, content: str}` | `{status: "saved", path}` |

Hidden from file tree: `.venv`, `__pycache__`, `.git`, `dashboard`, `_extensions`, `_freeze`, `scripts`, `tests`, `state/*.json`, `*_files/` build artifact directories, root-level `.html` files.

### 8.6 Shortcuts (`dashboard/shortcuts_plugin.py`)

| Method | Path | Body / Params | Response |
|--------|------|---------------|----------|
| `GET`  | `/api/shortcuts` | — | `{shortcuts: [name], descriptions: {name: desc}, count}` |
| `POST` | `/api/shortcuts` | `{name, path, description?}` | `{status, name, path}` |
| `GET`  | `/api/shortcuts/resolve?src=@name/sub` | — | `{src, resolved, exists}` |

Shortcut names must match `[a-z0-9_]+`.

### 8.7 Upload (`dashboard/upload_plugin.py`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST` | `/upload/file` | multipart: `upload_id`, `rel_path`, `file` | `{status: "ok"}` |
| `POST` | `/upload/finish` | `{upload_id, mode: "figure"\|"file"}` | `{status, shortcode, src, fig_id, log}` |

`mode="figure"`: expects a `.foam` case folder, creates a symlink under `data/`, returns a ready `{{< 4d-image >}}` shortcode. `mode="file"`: copies arbitrary files to `data/`, returns an `{{< include >}}` shortcode.

### 8.8 Static files

| Path | Serves |
|------|--------|
| `/state/<path>` | `state/` directory (figures, PNGs) |
| `/output/<path>` | `_output/` directory (compiled HTML) |

---

## 9. postMessage Protocol (browser → backend)

Figures are embedded as `srcdoc` iframes. Communication from iframe to backend goes through `relay.js` in the parent page.

| Message type | Direction | Payload | Effect |
|---|---|---|---|
| `4dpaper-camera` | iframe → relay → backend | `{fig_id, camera: {position, focal_point, view_up, parallel_scale?}}` | `POST /camera/<fig_id>` |
| `4dpaper-lock-query` | iframe → relay → backend | `{fig_id}` | `GET /camera-lock/<fig_id>`, reply with `4dpaper-lock-state` |
| `4dpaper-lock-toggle` | iframe → relay → backend | `{fig_id, locked: bool}` | `POST /camera-lock/<fig_id>` |
| `4dpaper-lock-state` | relay → iframe | `{fig_id, locked: bool}` | Sets lock UI in figure |
| `4dpaper-lock-ack` | relay → iframe | `{fig_id, locked: bool}` | Confirms toggle |
| `4dpaper-lock-all` | panel → all iframes | `{locked: bool}` | Lock/unlock all sub-figures simultaneously |
| `4dpaper-field-update` | iframe → relay → backend | `{fig_id, field?, time?}` | `POST /field/<fig_id>` |

---

## 10. Key Python Functions

### `_extensions/4dpaper/4dpaper.py`

```python
def generate_html_figure(
    src_path: Path, field: str, time_spec: str, output_path: Path,
    fig_id: str | None, available_fields: list[str] | None,
    background: str, axis_color: str, cmap: str,
    show_colorbar: bool, show_lock_btn: bool, show_orientation: bool,
    decimate: str = "auto",
) -> None
```
Generates a self-contained vtk.js HTML figure. Applies mesh decimation, embeds field-switcher data and per-timestep scalar arrays. Injects controls strip (lock button, orientation widget, time slider).

```python
def generate_png_figure(
    src_path: Path, field: str, time_spec: str, output_path: Path,
    fig_id: str | None, background: str, axis_color: str, cmap: str,
    show_colorbar: bool, decimate: str = "auto",
) -> None
```
Generates a static PNG using PyVista off-screen rendering. Applies saved camera if available, otherwise isometric view.

```python
def _rdp_simplify_xy(xs: list, ys: list, epsilon_fraction: float = 0.001) -> tuple[list, list]
```
Ramer–Douglas–Peucker polyline simplification. Normalises both axes to [0,1] before computing perpendicular distances. Returns simplified `(xs, ys)`. Falls back to original data if arrays are non-numeric or fewer than 3 points.

```python
def _apply_decimation(surface, decimate_spec: str, label: str = "") -> pyvista.PolyData
```
Parses `decimate` shortcode attribute and applies `decimate_pro()`. `"auto"` decimates only when face count > 150 000. Returns original surface unchanged if spec is `"none"` / `"off"` / `"0"`.

```python
def is_cache_valid(
    fig_path: Path, src_path: Path,
    camera_path: Path | None, field_path: Path | None,
    extra_deps: list[Path] | None,
) -> bool
```
Returns `True` if `fig_path` exists and is newer than all provided dependency paths.

### `scripts/data_loader.py`

```python
class SimulationData:
    def __init__(self, case_path: str) -> None
    def load(self) -> SimulationData          # detects format, returns self
    def get_mesh(self, time_index: int) -> pyvista.DataSet | None
    @property
    def n_steps(self) -> int
    @property
    def time_steps(self) -> list[float]
    @property
    def available_fields(self) -> list[str]
```

### `dashboard/utils.py`

```python
def save_camera_state(
    position: list, focal_point: list, view_up: list,
    parallel_scale: float | None, output_path: Path,
) -> None

def load_camera_state(path: Path) -> dict | None

def run_quarto_render(
    qmd_path: Path, log_lines: list[str],
    output_format: str = "html",   # "html" | "paperview"
) -> int  # exit code
```

---

## 11. Style Templates (`_4dpaper_styles.yml`)

Named templates that set background colour, axis colour, and colourmap for a figure.

```yaml
styles:
  dark:
    background: "#1a1a2e"
    axis_color: "white"
    cmap: "coolwarm"
  light:
    background: "white"
    axis_color: "black"
    cmap: "coolwarm"
```

Applied via `style="dark"` in any `4d-image` shortcode.

---

## 12. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PROJECT_ROOT` | Parent of `dashboard/` | Root of the user's paper workspace. Must point to the mounted volume in Docker (`/workspace`). |
| `FOURD_PAPER_VIEW` | unset | Set to `"1"` by `run_quarto_render` when rendering the paperview (PDF) profile. |
| `FOURD_APP_MODE` | unset | Set to `"1"` during any Quarto render triggered by the dashboard. |
| `QUARTO_DOCUMENT_PATH` | unset | Set by Quarto — path to the QMD being rendered (used by pre-render hook). |
| `QUARTO_PROJECT_DIR` | unset | Set by Quarto — project root (fallback for `PROJECT_ROOT`). |

---

## 13. Docker

```dockerfile
# App code lives in /app; user workspace is mounted at /workspace
# PROJECT_ROOT=/workspace is set by the entrypoint
EXPOSE 5006
HEALTHCHECK CMD curl -f http://localhost:5006/api/health || exit 1
```

The container is built for `linux/arm64`. Data is mounted as a volume at `/workspace`. The `_extensions/`, `dashboard/`, and `scripts/` directories are baked into the image at `/app/`.

---

## 14. Compile Flow Summary

```
Author edits .qmd
    ↓
POST /api/compile  {"files": {...}, "format": "html"}
    ↓
CompileHandler saves any in-flight file edits, calls run_quarto_render()
    ↓
Quarto pre-render hook (4dpaper.py):
  for each shortcode in .qmd files:
    check is_cache_valid()  →  skip if fresh
    generate_html_figure()  →  state/figures/<id>.html
    generate_png_figure()   →  state/figures/<id>.png
    ↓
Quarto renders .qmd → _output/<stem>.html
    ↓
CompileHandler returns {status:"success", filename:"<stem>.html"}

For PDF export:
POST /api/export
    ↓
run_quarto_render(output_format="paperview")  →  _output/<stem>-paperview.html
    ↓
weasyprint.HTML(filename=paperview_html).write_pdf()
    ↓
Stream PDF bytes to client
```
