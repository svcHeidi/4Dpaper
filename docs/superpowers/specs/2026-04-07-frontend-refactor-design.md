# 4Dpapers Frontend Refactoring Design
**Date:** 2026-04-07
**Scope:** Frontend module separation, CSS consolidation, asset management
**Goal:** Make UI maintenance and feature addition straightforward and scalable

---

## Executive Summary

Current frontend has scattered asset paths (`/assets/` vs `/static/`), overlapping CSS files, and resizable panes broken due to misconfiguration. This design restructures the frontend into clear, independent modules:

- **Asset management centralized** in a single `assets.py` (no more path hunting)
- **CSS split by responsibility** (tokens → layout → components)
- **Static file serving explicit** via `serve.py`
- **Button factory** for easy feature addition
- **JavaScript organized** in `static/js/` subdirectory

**Result:** Adding a feature = add a button (1 line) + implement logic. UI styling is maintained in one place.

---

## Problem Statement

### Current Issues

1. **Broken Resizable Panes**
   - CSS/JS files at `dashboard/static/` but referenced as `/assets/`
   - `split_pane.js` never loads, so gutters aren't draggable
   - Version numbers scattered and mismatched

2. **No Centralized Asset Management**
   - Paths appear in `app.py` lines 31-38
   - Versions in `split_loader.js` lines 10-11
   - No single source of truth for versions or locations

3. **CSS Duplication & Confusion**
   - `theme.css` (518 lines) — comprehensive but monolithic
   - `custom.css` (131 lines) — newer, intended as "UI expert" entry point
   - Both loaded, both authoritative, no clear separation
   - Gutter styles missing (removed in refactor, broke layout)

4. **Scalability Problem**
   - Adding a new feature requires:
     - Python code (logic)
     - HTML button in Python (layout)
     - CSS selector hunting (where do I put this button's style?)
     - JS path hunting (do I need new assets?)
   - **Too many places to touch.**

### Success Criteria

✅ Resizable panes work on first load
✅ Adding a feature button = 1 line of Python
✅ All button styling in one file
✅ Asset versions managed centrally
✅ New developer can find any CSS/JS in < 1 minute
✅ No more `/assets/` vs `/static/` confusion

---

## Architecture & Module Organization

### Directory Structure

```
dashboard/
├── components/
│   ├── __init__.py
│   ├── buttons.py              ← Button factory (centralized styling)
│   └── [future: other components]
│
├── pages/
│   ├── __init__.py
│   ├── paper_page.py           ← UNCHANGED
│   └── [other page modules]
│
├── static/
│   ├── css/
│   │   ├── theme-tokens.css    ← Design tokens only (colors, spacing, fonts)
│   │   ├── layout.css          ← Grid, flexbox, panes, gutters, resizing
│   │   ├── components.css      ← Buttons, headers, tabs, inputs, overlays
│   │   ├── overrides.css       ← Panel/Bokeh shadow DOM fixes
│   │   └── [DELETED] theme.css, custom.css
│   │
│   ├── js/
│   │   ├── split-pane.js       ← Resizable panes (moved from root static/)
│   │   ├── camera-sync.js      ← Camera overlay (moved)
│   │   ├── activity-bar.js     ← (moved, optional)
│   │   └── [other JS modules]
│   │
│   ├── assets.py               ← NEW: Centralized asset management
│   └── [existing files remain]
│
├── app.py                       ← Refactored to use Assets
├── controller.py                ← UNCHANGED
├── file_tree.py                 ← UNCHANGED
├── editor_tabs.py               ← UNCHANGED
└── utils.py                     ← UNCHANGED

serve.py (root)                  ← NEW: Static file serving entry point
```

### What Changes, What Doesn't

| Component | Status | Reason |
|-----------|--------|--------|
| `paper_page.py` | ✅ No change | Already well-separated |
| `controller.py` | ✅ No change | Business logic untouched |
| `file_tree.py` | ✅ No change | File explorer independent |
| `app.py` | 🔄 Refactored | Use `Assets` class, simplify |
| `theme.py` | ✅ No change | Python-side theme tokens (separate concern) |
| Static files | 🔄 Reorganized | Move to `static/css/` and `static/js/` |

---

## Asset Management (assets.py)

**File:** `dashboard/static/assets.py`

```python
"""
Centralized asset path and versioning.
Single source of truth for all CSS/JS references.
"""

class AssetVersion:
    """Version numbers for cache-busting."""
    THEME_TOKENS = "1"
    LAYOUT = "1"
    COMPONENTS = "1"
    OVERRIDES = "1"
    SPLIT_PANE = "1"
    CAMERA_SYNC = "1"

class Assets:
    """All asset paths and versions."""

    # CSS files (order matters: tokens → layout → components → overrides)
    CSS = {
        "theme_tokens": f"/static/css/theme-tokens.css?v={AssetVersion.THEME_TOKENS}",
        "layout": f"/static/css/layout.css?v={AssetVersion.LAYOUT}",
        "components": f"/static/css/components.css?v={AssetVersion.COMPONENTS}",
        "overrides": f"/static/css/overrides.css?v={AssetVersion.OVERRIDES}",
    }

    # JavaScript files (async, order independent)
    JS = {
        "split_pane": f"/static/js/split-pane.js?v={AssetVersion.SPLIT_PANE}",
        "camera_sync": f"/static/js/camera-sync.js?v={AssetVersion.CAMERA_SYNC}",
    }

    @staticmethod
    def css_list() -> list[str]:
        """Returns ordered CSS files for pn.extension()."""
        return list(Assets.CSS.values())

    @staticmethod
    def js_dict() -> dict[str, str]:
        """Returns JS files for pn.extension()."""
        return Assets.JS
```

**Usage in `app.py`:**
```python
from dashboard.static.assets import Assets

pn.extension(
    "codeeditor",
    sizing_mode="stretch_width",
    template="bootstrap",
    css_files=Assets.css_list(),
    js_files=Assets.js_dict(),
)
```

**Why:**
- Change a version? Edit `AssetVersion`, one place
- Add a new CSS file? Add to `Assets.CSS`, one place
- No path hunting across files
- Versioning is explicit and organized

---

## CSS Organization & Consolidation

### Current State
- `theme.css` (518 lines) — all-in-one monolith
- `custom.css` (131 lines) — overlay, creates confusion
- **Total:** 649 lines, unclear responsibility boundaries

### New State: 4 Focused Files

#### 1. `theme-tokens.css` (~100 lines)
**Purpose:** Design tokens only. No layout, no component styling.

```css
:root {
  /* Colors */
  --primary-color: #138a7c;
  --bg-dark: #0f111a;
  --bg-panel: #161922;
  --text-primary: #ffffff;
  --text-muted: #888888;
  --border-color: rgba(255, 255, 255, 0.1);

  /* Spacing */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 12px;
  --spacing-lg: 16px;

  /* Typography */
  --font-family: 'Inter', sans-serif;
  --font-size-xs: 11px;
  --font-size-sm: 12px;
  --font-size-base: 14px;

  /* Shadows */
  --shadow-sm: 0 2px 4px rgba(0,0,0,0.1);
  --shadow-md: 0 10px 30px rgba(0,0,0,0.5);
}
```

**Who modifies:** Designer/UI expert, to change color scheme or spacing

#### 2. `layout.css` (~150 lines)
**Purpose:** Grid, flexbox, panes, gutters, resizing logic.

```css
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.body-row {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.explorer-sidebar-wrap {
  flex: 0 0 250px;
  background: var(--bg-panel);
  border-right: 1px solid var(--border-color);
  overflow-y: auto;
}

.split-gutter {
  flex: 0 0 8px;
  background: rgba(255,255,255,0.05);
  cursor: ew-resize;
  user-select: none;
}

.split-gutter:hover,
.split-gutter.__split-dragging {
  background: rgba(255,255,255,0.1);
}

.main-panel {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.pane-right {
  flex: 0 0 400px;
  background: var(--bg-panel);
  border-left: 1px solid var(--border-color);
  overflow: hidden;
}
```

**Who modifies:** When layout changes (e.g., add a new pane, change gutter width)

#### 3. `components.css` (~250 lines)
**Purpose:** All component styling (buttons, headers, tabs, inputs, overlays).

```css
/* Buttons */
.btn-primary { /* Button styles */ }
.btn-secondary { /* Button styles */ }
.btn-size-small { /* Button styles */ }

/* Headers */
.app-header { /* Header styles */ }

/* Tabs */
.editor-tab-bar { /* Tab bar styles */ }
.editor-tab { /* Tab styles */ }

/* Overlays */
.build-overlay { /* Overlay styles */ }

/* [etc. all component styles] */
```

**Who modifies:** When styling a component or adding a new component type

#### 4. `overrides.css` (~100 lines)
**Purpose:** Panel/Bokeh shadow DOM fixes and quirks.

```css
/* Panel button defaults */
.bk-btn { /* fixes */ }

/* Ace editor overrides */
.ace_editor { /* fixes */ }

/* [Panel-specific adjustments] */
```

**Who modifies:** Rarely, when upgrading Panel or fixing a compatibility issue

---

## Button Factory (components/buttons.py)

**Purpose:** Single place to define all button types and styling. Adding a feature = 1 line.

```python
from enum import Enum
import panel as pn

class ButtonVariant(Enum):
    PRIMARY = "btn-primary"
    SECONDARY = "btn-secondary"
    DANGER = "btn-danger"
    ICON = "btn-icon"

class ButtonSize(Enum):
    SMALL = "btn-size-small"
    MEDIUM = "btn-size-medium"
    LARGE = "btn-size-large"

def create_button(
    name: str,
    variant: ButtonVariant = ButtonVariant.SECONDARY,
    size: ButtonSize = ButtonSize.MEDIUM,
    icon: str | None = None,
    on_click=None,
    **kwargs
) -> pn.widgets.Button:
    """
    Factory for creating styled buttons.
    All styling centralized in components.css.
    """
    css_classes = [variant.value, size.value]
    btn = pn.widgets.Button(
        name=name,
        css_classes=css_classes,
        **kwargs
    )
    if on_click:
        btn.on_click(on_click)
    return btn
```

**Usage:**
```python
# When adding a new feature:
my_btn = create_button("My Feature", variant=ButtonVariant.PRIMARY, icon="plus")
# That's it. Styling comes from components.css.
```

---

## Static File Serving (serve.py)

**File:** Root directory `serve.py`

```python
"""
Entry point for serving the 4Dpapers dashboard.
Configures Panel static file directories explicitly.

Run with: python serve.py
"""

import panel as pn
from pathlib import Path
from dashboard.app import create_app

# Static files are in dashboard/static/
static_dir = Path(__file__).parent / "dashboard" / "static"

# Create app
app = create_app()

# Serve with explicit static directory
pn.serve(
    {'/': app},
    static_dirs={'': str(static_dir)},
    port=5006,
    show=False,
    title="4Dpapers Dashboard"
)
```

**Why separate file:**
- ✅ Explicit static directory configuration
- ✅ Clear where the app is served from
- ✅ Easy to add other serve options (auth, logging, etc.)

**Run with:**
```bash
python serve.py
# NOT: panel serve dashboard/app.py
```

---

## JavaScript Organization (static/js/)

**Current state:**
- `split_pane.js`, `camera_overlay.js`, `tab_align_probe.js` scattered in `static/`

**New state:**
```
static/js/
├── split-pane.js       ← Resizable panes (moved from static/split_pane.js)
├── camera-sync.js      ← Camera overlay (moved from static/camera_overlay.js)
├── activity-bar.js     ← (moved from static/activity_bar.js)
└── [future modules]
```

**Why:**
- ✅ Clear that these are JavaScript modules
- ✅ Easy to add new JS features (goes in `static/js/`)
- ✅ All paths in one file (`assets.py`)

**No logic changes to JS files**, just relocate.

---

## Integration: How It All Works Together

### Adding a New Feature (Example: "Sync to Server" button)

**Step 1: Add button to UI**
```python
# In app.py, build_paper_page() or wherever:
from dashboard.components.buttons import create_button, ButtonVariant

sync_btn = create_button(
    "Sync to Server",
    variant=ButtonVariant.PRIMARY,
    icon="cloud-upload"
)
```

**Step 2: Implement logic**
```python
# In controller.py:
def sync_to_server(self):
    # ... implementation
    pass

# Wire button:
sync_btn.on_click(lambda: controller.sync_to_server())
```

**That's it.** Button styling comes from `components.css`, versioning from `assets.py`, serving from `serve.py`.

---

## Data Flow & Dependencies

```
serve.py
  └─> dashboard/app.py
      ├─> dashboard/static/assets.py (imports Assets class)
      ├─> dashboard/components/buttons.py (ButtonFactory)
      ├─> dashboard/pages/paper_page.py
      ├─> dashboard/controller.py
      └─> static/css/ files (loaded via pn.extension)
      └─> static/js/ files (loaded via pn.extension)
```

**Clean dependencies:**
- `app.py` depends on `Assets` (for paths)
- `app.py` depends on `ButtonFactory` (for button creation)
- Nothing depends on hardcoded `/assets/` paths
- CSS/JS are independent, loaded by pn.extension

---

## Migration Path

### Phase 1: Reorganize Static Files
1. Create `static/css/` and `static/js/` subdirectories
2. Move CSS files: `theme.css` → consolidate into 4 files
3. Move JS files to `static/js/`

### Phase 2: Add Assets Management
1. Create `dashboard/static/assets.py`
2. Create `dashboard/components/buttons.py`
3. Update `app.py` to use Assets class

### Phase 3: Create serve.py
1. Create `serve.py` at root with static directory config
2. Update startup instructions

### Phase 4: Testing & Validation
1. Test resizable panes (should work now)
2. Test button styling
3. Test all JS modules load correctly

---

## Success Metrics

After implementation:

| Metric | Target |
|--------|--------|
| Asset path references | 1 place (assets.py) |
| Resizable panes working | ✅ Yes, on first load |
| Time to add a button | < 1 minute |
| CSS files | 4 (tokens, layout, components, overrides) |
| Button creation | 1 line of Python |
| CSS knowledge required to add button | None (factory handles it) |
| New developer onboarding time | < 10 minutes |

---

## Open Questions / Decisions

1. **CSS Preprocessor?** (SCSS/SASS for nesting, mixins)
   - **Decision:** Not needed yet. Plain CSS is clear. Add if complexity grows.

2. **Tailwind or Utility CSS?**
   - **Decision:** No. Button factory + theme tokens is simpler for this codebase.

3. **Component Library (Storybook)?**
   - **Decision:** Not needed yet. Button factory is lightweight. Add if team grows.

4. **Split pane library (split.js, gridstack)?**
   - **Decision:** Keep current custom implementation (it's simple). Refactor only if new features need it.

---

## Notes for Implementation

- **Backward compatibility:** No existing features break. Pure refactoring.
- **Rollback risk:** Low. Each phase is independent.
- **Testing:** Manual browser testing (resize panes, add buttons). No unit tests required.
- **Documentation:** Update startup instructions to use `serve.py` instead of `panel serve`.
