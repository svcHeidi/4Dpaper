# Frontend Final Audit: File Explorer + Insert Pattern

**Architecture Philosophy:**
- **File Explorer** = Shows all user content (whatever they put in the folder)
- **Insert Figure/Insert File** = Modals for adding new data (symlink approach)
- **Generated Data Access** = `state/figures/` visible for users to access decimated meshes, PNGs, etc.

---

## Part 1: File Explorer Architecture (Security-First)

**Philosophy:** Show user-facing content only. Hide all backend code.

### Backend Approach: Whitelist User Content (Security)

```python
class FilesHandler(tornado.web.RequestHandler):
    """List user-facing files and folders only. Hide backend/system code."""

    def get(self) -> None:
        """Return file/folder tree for user-facing content only."""
        files = []

        # HIDE: System/backend code directories (security)
        HIDDEN_DIRS = {
            ".venv", "__pycache__", ".worktrees", ".git", ".github",
            ".quarto", ".pytest_cache", ".cursor", ".superpowers",
            "dashboard", "_extensions", "_freeze", "scripts", "tests",
            "Library"  # macOS
        }

        def should_include(path):
            # Skip hidden system directories
            if any(skip in path.parts for skip in HIDDEN_DIRS):
                return False
            # Skip dotfiles
            if path.name.startswith('.'):
                return False
            # Hide state JSON files (camera_*.json, field_*.json)
            # but keep state/figures/ folder visible
            if path.parent.name == "state" and path.is_file():
                if path.suffix == ".json":
                    return False
            return True

        # Get all files recursively, with filtering
        for path in _PROJECT_ROOT.rglob("*"):
            if not should_include(path):
                continue

            rel_path = str(path.relative_to(_PROJECT_ROOT))
            files.append({
                "path": rel_path,
                "is_dir": path.is_dir(),
                "size": path.stat().st_size if path.is_file() else None,
                "type": "directory" if path.is_dir() else path.suffix
            })

        files = sorted(files, key=lambda x: (not x["is_dir"], x["path"]))
        self.write({"files": files, "count": len(files)})
```

**Key Security Points:**
- ✓ Backend code (`dashboard/`, `_extensions/`) - HIDDEN
- ✓ System files (`.venv`, `.git`, `.github`) - HIDDEN
- ✓ Build artifacts (`_freeze`) - HIDDEN
- ✓ Tests, scripts - HIDDEN
- ✓ State metadata (`state/*.json`) - HIDDEN (internal files)
- ✓ User documents (`.qmd`, `.bib`) - VISIBLE
- ✓ Generated data (`state/figures/`) - VISIBLE
- ✓ User data folders (`data/`, `media/`) - VISIBLE

### Frontend: Display as Hierarchical Tree

Update `renderFileTree()` in `dashboard/static/index.html`:

```javascript
function renderFileTree(files) {
    const container = document.getElementById('fileTreeContent');
    container.innerHTML = '';

    // Build folder structure
    const tree = {};

    files.forEach(item => {
        const parts = item.path.split('/');
        let current = tree;

        for (let i = 0; i < parts.length; i++) {
            const part = parts[i];
            if (!current[part]) {
                current[part] = { isDir: true, children: {}, path: parts.slice(0, i + 1).join('/') };
            }
            if (i === parts.length - 1 && !item.is_dir) {
                current[part] = {
                    isDir: false,
                    path: item.path,
                    size: item.size,
                    type: item.type
                };
            } else {
                current = current[part].children = current[part].children || {};
            }
        }
    });

    // Render tree
    function renderNode(node, name, depth = 0) {
        const isDir = node.isDir;
        const item = document.createElement('div');
        item.style.paddingLeft = (depth * 16) + 'px';
        item.className = `file-tree-item ${isDir ? 'folder' : 'file'} ${isDir ? '' : node.type}`;

        if (isDir) {
            item.innerHTML = `<i class="ph ph-folder" style="margin-right:6px;"></i>${name}`;
            item.style.cursor = 'pointer';
            item.addEventListener('click', () => toggleFolder(item));

            const children = document.createElement('div');
            children.className = 'file-tree-children';
            Object.keys(node.children).forEach(childName => {
                renderNode(node.children[childName], childName, depth + 1);
                children.appendChild(document.querySelector(`[data-path="${node.children[childName].path}"]`));
            });
        } else {
            item.innerHTML = `<i class="ph ph-file" style="margin-right:6px;"></i>${name}`;
            item.addEventListener('click', () => openFile(node.path));
        }

        item.setAttribute('data-path', node.path);
        container.appendChild(item);
    }

    // Render root
    Object.keys(tree).forEach(name => {
        renderNode(tree[name], name);
    });
}

function toggleFolder(element) {
    const childrenDiv = element.nextElementSibling;
    if (childrenDiv && childrenDiv.classList.contains('file-tree-children')) {
        childrenDiv.style.display = childrenDiv.style.display === 'none' ? 'block' : 'none';
        element.classList.toggle('collapsed');
    }
}
```

### What Users See When They Open the Project

**User-Facing Explorer (VISIBLE):**
```
📄 analysis_report.qmd
📄 references.bib
📄 _shortcuts.yml
📄 _quarto.yml
📂 sections/
   ├── 📄 01_introduction.qmd
   ├── 📄 02_simulation.qmd
   └── 📄 03_results.qmd
📂 data/                        ← User adds via Insert Figure/Insert File
   └── sim_case/
📂 state/                       ← Generated data (visible, managed by app)
   ├── 📂 figures/
   │   ├── fig-at.html          ← Interactive vtk.js
   │   ├── fig-at.png           ← PNG for PDF export
   │   ├── fig-pvsm-vm-pipeline.vtu     ← Decimated surface mesh
   │   └── fig-pvsm-vm-scalars-t0.bin   ← Binary field data
   ├── 📄 camera_fig-at.json
   └── 📄 field_fig-vm.json
📂 media/
   └── (images, etc.)
```

**Backend Code (HIDDEN - for security):**
```
❌ dashboard/          (app UI infrastructure)
❌ _extensions/        (quarto plugins)
❌ scripts/            (utility scripts)
❌ tests/              (test suite)
❌ .github/            (CI/CD workflows)
❌ _freeze/            (build cache)
❌ .venv/              (Python environment)
```

**Key:** Users see their content AND generated pipeline data. Backend code remains hidden (security).

---

## Part 2: Insert Figure Modal (Existing Pattern)

**What it does:**
- User drags an OpenFOAM case folder
- OR clicks to open system file picker → select folder
- Files uploaded to `state/upload_tmp/`
- Backend finds .foam file
- **Creates symlink** to `data/` (not copy)
- Returns shortcode

**Button in file tree:**
```html
<button onclick="showInsertFigureModal()" class="insert-btn">
    <i class="ph ph-chart-line"></i> Insert Figure
</button>
```

Already works via `insert-figure-overlay.js`.

---

## Part 3: Insert File Modal (New)

Similar pattern, but for arbitrary files (`.bib`, `.tex`, `.csv`, etc.):

```javascript
// In insert-file-overlay.js (same pattern as insert-figure)
async function uploadFiles(files) {
    var uploadId = "file_" + Date.now();

    // Upload files to staging
    for (var f of files) {
        var fd = new FormData();
        fd.append("upload_id", uploadId);
        fd.append("rel_path", f.name);
        fd.append("file", f);
        await fetch("/upload/file", { method: "POST", body: fd });
    }

    // Finish: symlink/copy to data/ (reuse existing logic)
    var result = await fetch("/upload/finish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ upload_id: uploadId, mode: "file" })
    });

    // Backend creates symlink, returns shortcode
    var data = await result.json();
    insertShortcode(data.shortcode);  // Insert into .qmd
}
```

**Button in file tree:**
```html
<button onclick="showInsertFileModal()" class="insert-btn">
    <i class="ph ph-file-plus"></i> Insert File
</button>
```

---

## Part 4: Backend: Make state/figures/ Accessible

### Issue: `state/figures/` should NOT be filtered out

Currently, the file listing might exclude `state/`. **Fix:**

```python
# In FilesHandler.get() - ensure state/ is included
skip_dirs = [".venv", "__pycache__", ".worktrees", ".git", ".quarto", ".pytest_cache"]

for path in _PROJECT_ROOT.rglob("*"):
    if any(skip in path.parts for skip in skip_dirs):
        continue
    # state/ IS included now ✓
    rel_path = str(path.relative_to(_PROJECT_ROOT))
    files.append({...})
```

### Expose state/figures/ for Download/Browse

Add endpoint to serve files from `state/figures/` (already in plugins.py):

```python
# In plugins.py - already registered:
(r"/state/(.*)", tornado.web.StaticFileHandler, {"path": str(_PROJECT_ROOT / "state")}),
```

Users can:
- **View files** in explorer (see .vtu, .bin, .png files)
- **Download files** by clicking
- **View PNG images** inline (browser preview)

---

## Part 5: What the User Gets

### Frontend Explorer Shows:
✓ All `.qmd` files (editable)
✓ All `.bib` files (editable)
✓ All `.yml` config files (editable)
✓ All folders (`sections/`, `data/`, `media/`, etc.)
✓ **`state/figures/` with generated data** (viewable/downloadable)
  - `.html` interactive figures
  - `.png` static images for PDF
  - `.vtu` decimated mesh data
  - `.bin` binary field data
✓ Camera/field state JSON files

### User Workflow:

1. **Start app** → Explorer shows everything in project folder
2. **Edit content** → Click `.qmd`/`.bib` files to edit
3. **Add figures** → Button "Insert Figure" → drag OpenFOAM case → symlinked to `data/`
4. **Add files** → Button "Insert File" → drag `.bib`/`.tex`/`.csv` → symlinked to `data/`
5. **Compile** → Backend generates figures → stores in `state/figures/`
6. **Access generated data** → Explorer shows `state/figures/` → user can view/download PNGs, meshes, etc.

---

## Part 6: File Organization

```
Project Root (what user sees in explorer):
├── analysis_report.qmd          ← Main document
├── references.bib               ← Bibliography
├── _quarto.yml                  ← Config
├── sections/                    ← Document sections (user creates/edits)
├── data/                        ← User inputs (via Insert Figure/Insert File)
│   └── foam_cases/
├── state/                       ← Generated data (visible, managed by app)
│   ├── figures/
│   │   ├── fig-at.html          ← Interactive vtk.js
│   │   ├── fig-at.png           ← PNG for PDF
│   │   ├── fig-at-pipeline.vtu  ← Decimated surface mesh
│   │   └── fig-at-scalars-t0.bin ← Field data (binary)
│   ├── camera_fig-at.json       ← Saved camera position
│   └── field_fig-at.json        ← Saved field/timestep
├── media/                       ← Figures, images
└── _output/                     ← Compiled HTML/PDF (read-only)
```

---

## Part 7: Configuration (Optional, Future)

If user wants to customize what's visible, add optional config:

```yaml
# project.yml (optional)
explorer:
  show:
    - "*.qmd"
    - "*.bib"
    - "sections/"
    - "state/figures/"      # ← Important: expose generated data
    - "data/"
  hide:
    - "dashboard/"
    - ".github/"
    - "_extensions/"
```

Backend reads this config (if present) to filter display. **But by default: show everything.**

---

## Implementation Checklist

### Phase 1: Backend (15 min)
- [ ] Update `FilesHandler.get()` to return ALL files (not filtered)
- [ ] Ensure `state/` and `state/figures/` are included
- [ ] Test: `/api/files` returns complete project structure

### Phase 2: Frontend Tree (30 min)
- [ ] Update `renderFileTree()` to build hierarchical tree
- [ ] Add folder expand/collapse UI
- [ ] Add icons for folders vs files
- [ ] Test: Explorer shows full structure including `state/figures/`

### Phase 3: Insert Buttons (10 min)
- [ ] Add "Insert Figure" button to file tree toolbar
- [ ] Add "Insert File" button to file tree toolbar
- [ ] Hook to existing modals (already exist)

### Phase 4: Ensure state/figures/ is Downloadable (5 min)
- [ ] Verify `/state/(.*)` route is registered (already is)
- [ ] Test: Can view/download files from `state/figures/` via browser

### Phase 5: Optional - Config File (future)
- [ ] Add `project.yml` parser (if user wants to customize visibility)
- [ ] Backend reads config and filters display

---

## Summary

| Component | Current | Updated |
|-----------|---------|---------|
| **Explorer** | Filtered (only .qmd/.bib/.yml) | Shows user content + generated data (hides backend code) |
| **Backend** | Returns `.py` files (shown as filtered on frontend) | Returns ONLY user content (filters backend code for security) |
| **Backend Code** | Returned by API, hidden by frontend filter | **NOT returned by API** (never exposed) |
| **state/figures/** | Hidden from user | **VISIBLE** - user can browse/download generated data |
| **Insert Figure** | Works via modal | ✓ Keep existing (uses symlink approach) |
| **Insert File** | N/A | New modal (same symlink pattern) |
| **Configuration** | Hardcoded | Optional config file (future) |

**Key Changes:**
1. Backend filtering (security-first): Exclude `dashboard/`, `_extensions/`, `scripts/`, `tests/`, etc.
2. Frontend display: Show what backend returns (no additional filtering needed)
3. Generated data transparency: `state/figures/` visible for user access to decimated meshes, PNGs, field data
4. Both Insert modals use symlink approach (avoid data duplication)

**Philosophy:** Show user-facing content + generated data. Hide backend code (security). Generated pipeline data is transparent and accessible.
