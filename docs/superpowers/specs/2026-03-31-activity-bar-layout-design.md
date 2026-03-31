# Activity Bar Layout — Design Spec
**Date:** 2026-03-31
**Status:** Approved

## Goal

Replace the current 3-pane hardcoded layout (file tree | editor | preview) with a config-driven 2-pane layout: a fixed-width activity bar on the far left, a single switchable main panel, and the paper preview pane on the right. Panel switching is client-side only — all panels are pre-rendered at load, JS shows/hides them.

## Current Problems

- `app.py` assembles left + center + right containers and gutters manually with hardcoded class names
- `split_pane.js` has hardcoded `MIN_LEFT`, `MIN_CENTER`, `MIN_RIGHT` constants and hardcoded CSS selectors
- Adding a new view requires touching `app.py`, `split_pane.js`, and CSS simultaneously
- Left pane (file tree) and center pane (editor) are always both visible, wasting space

## Proposed Architecture

### Single source of truth: `PANELS` list in `app.py`

```python
PANELS = [
    {"id": "explorer", "icon": "📁", "label": "Files",    "content": explorer_view},
    {"id": "editor",   "icon": "📝", "label": "Editor",   "content": editor_view},
    {"id": "figures",  "icon": "🖼️", "label": "Figures",  "content": figure_browser_view},
    {"id": "settings", "icon": "⚙️", "label": "Settings", "content": settings_view, "bottom": True},
]
```

`app.py` iterates `PANELS` to:
1. Render each panel's content into a `div.panel-slot[data-panel-id=<id>]` container (hidden by default)
2. Emit `window.SPLIT_CONFIG = { panels: [...], defaultPanel: "explorer" }` as an inline `<script>` block before loading JS

### DOM structure

```
app-shell
├── toolbar
└── body-row
    ├── activity-bar (42px fixed, outside split)
    ├── main-panel   (flex, resizable via single gutter)
    │   ├── panel-slot[data-panel-id="explorer"]  (visible)
    │   ├── panel-slot[data-panel-id="editor"]    (hidden)
    │   ├── panel-slot[data-panel-id="figures"]   (hidden)
    │   └── panel-slot[data-panel-id="settings"]  (hidden)
    ├── split-gutter (single, between main and preview)
    └── preview-pane (paper preview, always visible)
```

### Activity bar visual style

VSCode-style: no background fill on icons. Active icon has a 2px colored left-edge bar (`border-left: 2px solid #007acc`). Inactive icons at 40% opacity. Settings pinned to bottom via `margin-top: auto`. Tooltips on hover showing the label.

### `activity_bar.js` (new, ~80 lines)

Responsibilities:
- Read `window.SPLIT_CONFIG.panels` on load
- Render activity bar icon buttons from config (no hardcoded HTML)
- On icon click: set `display:none` on all `.panel-slot`, set `display:block` on target, update active indicator
- Persist active panel ID to `localStorage` key `4dpapers.layout.activePanel`
- Restore from localStorage on load; fall back to `defaultPanel`

### `split_pane.js` (trimmed)

- Remove all 3-pane logic (`MIN_CENTER`, center width storage, 2-gutter drag handlers)
- Read pane selectors from `window.SPLIT_CONFIG` instead of hardcoded strings
- Single gutter between `.main-panel` and `.pane-right`
- Store only one width: `4dpapers.pane.mainWidth` in localStorage
- Reflow (ACE editor resize) unchanged

### `settings_page.py` (new)

Returns a Panel widget with basic settings: theme toggle (light/dark), gutter width, default panel. Content can be expanded later. For now a static form is sufficient.

## Files Changed

| File | Change |
|------|--------|
| `dashboard/app.py` | Replace 3-pane manual assembly with `PANELS` loop; emit `SPLIT_CONFIG` |
| `dashboard/static/split_pane.js` | Trim to 2-pane; read config from `window.SPLIT_CONFIG` |
| `dashboard/static/activity_bar.js` | New — config-driven icon rendering + panel switching |
| `dashboard/pages/settings_page.py` | New — settings panel content widget |
| `dashboard/static/split_loader.js` | Add `activity_bar.js` to deferred load sequence |
| `dashboard/theme.css` | Add `.panel-slot`, `.activity-bar`, `.active-indicator` styles |

**Unchanged:** `file_tree.py`, `figure_browser.py`, `paper_page.py`, `camera_plugin.py`, `color_plugin.py`

## Key Constraints

- All panels must be rendered into the DOM at startup (client-side switching requires this)
- Activity bar is outside the resizable split — it has fixed width and is never a drag target
- `split_pane.js` must still trigger ACE editor reflow on resize
- `deepQuerySelector` shadow-DOM search must be preserved for Panel widget compatibility
- localStorage keys change: migrate `4dpapers.pane.leftWidth` / `rightWidth` → `4dpapers.pane.mainWidth`

## Out of Scope

- Collapsing the main panel (clicking active icon does nothing)
- Drag-reordering of activity bar icons
- Per-panel settings or persistence beyond active panel ID
- More than one gutter / N-pane generalization
