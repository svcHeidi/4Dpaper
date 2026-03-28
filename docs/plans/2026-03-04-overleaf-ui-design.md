# Overleaf-Style UI Redesign

**Date**: 2026-03-04
**Status**: Approved

## Problem

The current dashboard has a specialized figure-browser sidebar that only shows .foam files and figure-insertion widgets. Users expect a familiar LaTeX/Overleaf-style interface where they can see their full project structure, open any file, and edit it — just like working in Overleaf or VS Code.

## Design

### Layout: Three-Panel (File Tree + Editor + Preview)

```
+---------------+---------------------------+------------------+
|  Project      |  Editor (report.qmd)      |  Paper Preview   |
|  Files        |  [Save] [Insert Figure]   |                  |
|               |                           |  [Rebuild HTML]  |
|  > data/      |  ---                      |  [Export PDF]    |
|  > state/     |  # My Paper               |                  |
|    report.qmd |  {{< 4d-image ... >}}     |  +------------+  |
|    refs.bib   |  ...                      |  | iframe     |  |
|    _quarto.yml|                           |  | preview    |  |
+---------------+---------------------------+------------------+
```

- **Left**: Full project file tree (replaces figure-browser sidebar)
- **Center**: Code editor — opens any clicked editable file
- **Right**: Paper preview iframe + Rebuild HTML / Export PDF (unchanged)
- **Toggle buttons** stay: "Files" (left), "Preview" (right)

### File Tree Sidebar

**Root**: Project root (where `_quarto.yml` lives)

**Hidden directories** (auto-filtered):
`.venv/`, `.git/`, `__pycache__/`, `_freeze/`, `.quarto/`, `node_modules/`, `.claude/`

**Editable files** (open in code editor on click):
`.qmd`, `.bib`, `.yaml`, `.yml`, `.css`, `.tex`, `.md`, `.txt`

**Preview files** (shown as preview pane, not source):
`.html` → iframe, `.png`/`.jpg` → image pane, `.pdf` → download link

**Non-openable**: everything else (greyed out, no click action)

### Editor Behavior

- Clicking a file in the tree switches the editor content to that file
- Editor title updates to show the current filename
- Language mode auto-detects: markdown (.qmd), yaml (.yaml), bibtex (.bib), css (.css)
- Unsaved changes: prompt before switching or auto-save
- Save button writes to the currently-open file path

### Figure Insertion

Moves from a permanent sidebar to a **modal/dialog** triggered by "Insert Figure" button in the editor toolbar. Contains the same widgets as today's `build_figure_browser()`:
- .foam file selector (browsing project `data/` directory)
- Field, fig-id, time, caption inputs
- Copy-case checkbox
- Shortcode preview + Insert button

### Files Affected

| File | Action |
|------|--------|
| `dashboard/app.py` | Major rewrite: replace figure-browser sidebar with file tree, add file-switching logic |
| `dashboard/figure_browser.py` | Refactor: extract figure-insertion form into a modal/dialog builder |
| New: `dashboard/file_tree.py` | New module: project file tree widget with filtering and click handlers |
| `dashboard/pages/paper_page.py` | Minor: no structural changes, stays as-is |

### Implementation Notes

- Use Panel's `FileSelector` or custom `Column` of clickable `Button`/`Markdown` rows for the tree
- File tree should refresh on demand (button or after Save)
- CodeEditor language param maps: `{"qmd": "markdown", "bib": "latex", "yaml": "yaml", "css": "css", "tex": "latex", "md": "markdown", "txt": "text"}`
- The figure-insertion modal can use `pn.Column` inside a `pn.widgets.Dialog` or a toggle-visible panel

### Team Split

- **Frontend developer**: File tree widget, modal dialog, editor file-switching, language detection, styling
- **Backend developer**: Camera sync bug fix (separate workstream), test coverage, Quarto integration
