# 4Dpapers Agent Reference

This file contains technical guidance for AI agents working with 4Dpapers code and data.

## Files & Exposure

- **`CLAUDE.md`** — Detailed machine-readable reference for coding agents (file system only)
- **`AGENTS.md`** — This file; technical agent guidance and format support (file system only)
- **`agents.yaml`** — Curated agent personas exposed to frontend UI when `FOURD_EXPOSE_AGENTS=1`
- **`/api/agents` endpoint** — Serves agent metadata when enabled (frontend only; hidden from file browser)

The generic file browser and `/api/file` endpoint intentionally hide these files so internal guidance is not exposed accidentally to end users browsing papers.

---

## Supported Input Data Formats (Quick Reference)

4Dpapers accepts **27+ file formats** across scientific computing domains. Comprehensive format documentation is in **CLAUDE.md § 6**.

### Verification Status (v1)

- **Verified with local automated fixtures:** `.vtu`, `.vtp`, `.vtk`, `.pvd`, `.vtk.series` (synthetic/local mix), `.xdmf` + companion `.h5`, `.stl`, `.obj`, `.ply`, `.msh`, `.med`, `.hdf5`, Plotly `.json`
- **Externally or manually validated, but missing redistributable local fixtures:** `.foam`, `.openfoam`
- **Implemented, but not yet fixture-backed enough for a full v1 workflow claim:** `.exo`, `.e`, `.ex2`, `.case`, `.cgns`, real Abaqus `.inp`

Treat the first group as the strongest v1 evidence. Treat the second and third groups as narrower claims until local fixtures or repeatable manual checks are added.

### Quick Lookup by File Extension

**CFD/OpenFOAM:**
- `.foam`, `.openfoam` → OpenFOAM case (auto-merges parallel decomposed cases)
- `.case` → EnSight Gold post-processor format
- `.cgns` → Multi-discipline CFD/FEA interchange

**VTK (Most Common):**
- `.vtu` → VTK Unstructured Grid (single file or directory of timesteps)
- `.pvd` → ParaView collection (indexes multiple timesteps)
- `.vtp` → VTK PolyData (surface meshes)
- `.vtk` → VTK Legacy format
- `.vtk.series` → JSON index + individual VTK files (non-OpenFOAM time-series)

**FEA/Structural:**
- `.exo`, `.e`, `.ex2` → Exodus II (SEACAS standard)
- `.xdmf`, `.xmf` → XDMF (requires co-located `.h5` HDF5 file)

**Geometry/Static Meshes:**
- `.stl` → Stereolithography (CAD)
- `.obj` → Wavefront OBJ (3D models)
- `.ply` → Polygon File Format (ASCII, binary_LE, or `.ply.gz` gzip-compressed)

**Mesh Generation (meshio is bundled in the official image):**
- `.msh` → Gmsh mesh file
- `.med` → Salome MED format
- `.inp` → Abaqus mesh topology (not `.odb` results)
- `.hdf5` → Generic HDF5 (note: `.h5` reserved for FLUENT)

**Visualization:**
- `.json` → Plotly Figure Object (2D/3D charts via `4d-graph` shortcode)

### Input Rules by Domain

| Domain | Best Format | Supports Time-Series | Supports Fields | Notes |
|--------|-------------|----------------------|-----------------|-------|
| **CFD** | `.foam` or `.pvd` | YES | YES | OpenFOAM has external/manual validation; EnSight/CGNS fixture coverage is still pending |
| **FEA** | `.exo` or `.cgns` | YES | YES | Reader support is implemented, but real local fixture coverage is still pending |
| **Geometry Only** | `.stl`, `.obj`, `.ply` | NO | LIMITED | No animation; static CAD models |
| **Generic VTK** | `.vtu` or `.vtp` | MULTI | YES | Most flexible; widely supported |
| **Time Animation** | `.pvd` or `.vtk.series` | YES | YES | Explicit timestep indexing |
| **Charts/Graphs** | `.json` (Plotly) | CONDITIONAL | N/A | 2D/3D interactive plots only |

---

## Common Agent Tasks

### Data Architect
- **Format selection:** Advise users on which format best suits their simulation output
- **Import strategy:** Help convert non-native formats to VTK (via meshio, ParaView, etc.)
- **Pipeline design:** Multi-simulation comparison workflows using `4d-panel` and `4d-timeseries` shortcodes
- **Reference:** See CLAUDE.md § 6 for full format matrix

### Visualization Engineer
- **Mesh preparation:** Recommend decimation settings for large meshes
- **Colour mapping:** Guide on scalar field visualization (heatmaps, custom ranges)
- **Animation:** Advise on time-series rendering and play button usage
- **Interactive figures:** Optimize field-switching and camera state for publication-ready visualizations
- **Reference:** See CLAUDE.md § 3 (shortcode reference) for all rendering options

### Technical Writer
- **Figure captions:** Writing standards for scientific figures with scalar field labels
- **Data provenance:** Document source format, preprocessing, and any decimation applied
- **Reproducibility:** Noting camera positions, field ranges, and timestep selections
- **Reference:** See CLAUDE.md § 3.1 for caption and metadata attributes

### General Assistant
- **Format Q&A:** "What formats can I embed?" → See quick reference above
- **Upload troubleshooting:** "My file won't upload" → Check file size (max 5GB) and extension
- **Shortcode help:** "How do I embed a time-series?" → `4d-timeseries` shortcode (CLAUDE.md § 3.3)
- **Camera/fields:** "How do I switch scalar fields in the figure?" → Built-in field switcher in HTML figures

---

## Format Support Details by Use Case

### Case Study 1: OpenFOAM CFD Results
**Format:** `.foam` (reconstructed case)  
**Time-series:** YES — All timesteps at `postProcessing/` automatically detected  
**Scalar fields:** YES — U, p, T, etc. available for live field switching  
**Animation:** YES — Play button triggers timestep stepping  
**Decimation:** YES — Auto-applied if surface > 150k faces  
**Best practice:** Use reconstructed case (not decomposed processor* directories)

### Case Study 2: FEA Results from Abaqus
**Format:** `.exo` (export to Exodus II from Abaqus CAE)  
**Time-series:** YES — Solution timesteps exported  
**Scalar fields:** YES — Nodal stresses, strains, displacements  
**Animation:** YES — Deformation field over time  
**Limitation:** `.odb` output databases not supported; must export to `.exo` first  
**Best practice:** Use Exodus II; consider CGNS as alternative

### Case Study 3: Generic VTK Time-Series
**Format:** `.vtk.series` (JSON index) or `.pvd` (ParaView collection)  
**Files:** Multiple individual `.vtk` files + JSON metadata  
**Time-series:** YES — Files indexed by time value  
**Scalar fields:** YES — Per-file arrays preserved  
**Best practice:** `.pvd` is more portable; `.vtk.series` useful for non-standard solvers

### Case Study 4: Static Geometry
**Format:** `.stl`, `.obj`, or `.ply`  
**Time-series:** NO — Single static mesh  
**Scalar fields:** VERY LIMITED — No field animation  
**Use case:** CAD geometry, 3D models, reference meshes  
**Best practice:** Use `.ply` if geometry has vertex attributes; otherwise any format is fine

### Case Study 5: Interactive Plots
**Format:** `.json` (Plotly Figure Object)  
**Time-series:** CONDITIONAL — Only if Plotly figure contains frame/animation data  
**Scalar fields:** N/A — Chart format  
**Use case:** Time-series graphs, parameter studies, statistical plots  
**Best practice:** Export from Plotly as JSON; embed via `4d-graph` shortcode

---

## Known Limitations & Workarounds

| Issue | Formats Affected | Workaround |
|-------|------------------|-----------|
| Large mesh > 150k faces | All formats | Decimation auto-applied; configure with `decimate="0.5"` (keep 50%) |
| XDMF missing `.h5` file | `.xdmf`, `.xmf` | Ensure HDF5 companion file is co-located in same directory |
| Abaqus `.odb` not supported | `.odb` | Export to `.exo` (Exodus II) from Abaqus CAE first |
| Binary PLY big-endian | `.ply` (binary_be) | Unsupported; convert to ASCII or binary_little_endian first |
| `.h5` conflicts with FLUENT | `.h5` | Use `.hdf5` extension for generic HDF5; `.h5` reserved for FLUENT CFF |
| No STEP/IGES CAD support | `.step`, `.iges`, `.sat` | No native CAD kernel; workaround: convert to `.obj` or `.stl` in CAD tool |

---

## Environment Setup for Agent Tasks

Agents should verify the user's environment has:

```bash
# Core (always present)
pip install pyvista[jupyter]==0.47.3
pip install vtk==9.6.1
pip install plotly>=5.0.0

# Included by requirements.txt; install explicitly in custom Python environments
pip install meshio==5.3.5

# For PDF export (PNG rasterization)
pip install weasyprint>=60.0
```

If a format fails to load, check:
1. File extension matches documented format
2. Dependencies installed (the official image includes meshio for `.med`/`.msh`/`.inp`; custom environments may not)
3. File size < 5GB (dashboard upload limit)
4. XDMF files have co-located `.h5` companion

---

## Cross-Domain Format Mapping

**"I have data in Format X. How do I get it into 4Dpapers?"**

| Source Format | Recommended Target | Tools | Effort |
|---------------|-------------------|-------|--------|
| ANSYS Fluent (`.cas`, `.dat`) | `.case` (EnSight export) | ANSYS CAE | Low |
| ANSYS Mechanical (`.rst`) | `.exo` (Exodus export) | ANSYS CAE | Low |
| OpenVDB (VFX) | `.vtu` (OpenVDB→VTK) | ParaView | Medium |
| ASCII XYZ points | `.ply` or `.json` (custom script) | Python/NumPy | Medium |
| Salome (internal format) | `.med` (native export) | Salome CAE | Low |
| Gmsh native | `.msh` (native export) | Gmsh | Low |
| ParaView state (`.pvsm`) | `.pvd` or `.vtu` (batch export) | ParaView CLI | Medium |
| VisIt (`.silo`) | `.vtk` (VisIt export) | VisIt | Medium |
| STL/OBJ CAD | Use directly (`.stl`, `.obj`) | Any CAD tool | Low |

---

## API Contracts for Format Handling

For agents implementing format support or uploading data via API:

**POST /upload/finish** (format=figure, OpenFOAM-only dashboard flow)
- Input: `.foam` case folder (symlinked into `data/`)
- Output: Ready-to-use `{{< 4d-image >}}` shortcode
- Example: `{"status": "ok", "shortcode": "{{< 4d-image id=\"fig-1\" src=\"data/case\" field=\"U\" >}}"}`

**POST /upload/finish** (format=file)
- Input: Any supported file (`.stl`, `.vtu`, `.json`, etc.)
- Output: `{{< include ... >}}` shortcode reference
- Example: `{"status": "ok", "src": "data/model.stl"}`

**GET /api/shortcuts/resolve?src=@name/path**
- Resolves `@shortcut` syntax to absolute filesystem path
- Used by pre-render hook to locate remote data

---

## Shortcuts & Data Location Best Practices

**For agents helping users organize data:**

1. **Local data** → `data/` subdirectory (relative paths work in shortcodes)
2. **Remote HPC data** → Define in `_shortcuts.yml`:
   ```yaml
   shortcuts:
     hpc_data:
       path: /mnt/hpc/projects/myproject
       description: HPC cluster data
   ```
   Then use: `src="@hpc_data/simulation_run_123/case.foam"`

3. **External URLs** → Not supported directly; download and stage locally first

---

## Debugging Format Issues (Agent Troubleshooting)

**"File uploaded but figure doesn't render"**
- Check browser console for loader errors
- Verify field name in `field=""` attribute matches available fields
- Check `_output/` directory for compile log
- Try simpler format first (`.vtu` instead of custom `.case`)

**"Fields don't appear in field switcher"**
- Confirm `fields="U,p,T"` attribute is set
- Check scalar arrays are point data (not cell data); cell data auto-converted
- Verify field names match exactly (case-sensitive)

**"Mesh looks decimated/simplified**
- Expected behavior for > 150k face meshes
- Override with `decimate="none"` to disable (may cause performance issues)
- Or use `decimate="0.5"` to keep 50% of faces

**"Camera doesn't persist across renders"**
- Camera state saved to `state/camera_<id>.json`
- Delete this file to reset to default isometric view
- Check PNG export has correct camera in `state/figures/<id>.png`
