# Activity Bar Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded 3-pane layout with a config-driven activity bar + single switchable main panel + preview pane.

**Architecture:** A `PANELS` list in `app.py` is the single source of truth — it drives Python widget assembly, the activity bar HTML, and `window.SPLIT_CONFIG` which `activity_bar.js` and `split_pane.js` both read. Switching is pure client-side JS (show/hide pre-rendered DOM nodes). `split_pane.js` is trimmed to 2-pane only.

**Tech Stack:** Python/Panel, vanilla JavaScript, CSS custom properties.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `dashboard/static/theme.css` | Modify | Add `.activity-bar`, `.activity-bar-btn`, `.main-panel`, `.panel-slot` styles |
| `dashboard/pages/settings_page.py` | Create | Settings panel content widget |
| `dashboard/static/activity_bar.js` | Create | Config-driven panel switching (reads `window.SPLIT_CONFIG`) |
| `dashboard/static/split_loader.js` | Modify | Inject both `split_pane.js` and `activity_bar.js` after DOM ready |
| `dashboard/app.py` | Modify | PANELS list, activity bar HTML builder, new layout assembly, emit SPLIT_CONFIG |
| `dashboard/static/split_pane.js` | Modify | Trim to 2-pane, read selectors from `window.SPLIT_CONFIG` |
| `tests/test_activity_bar_layout.py` | Create | Smoke tests for settings page and app assembly |

---

## Task 1: CSS — activity bar and panel slot styles

**Files:**
- Modify: `dashboard/static/theme.css`

- [ ] **Step 1: Append activity bar + panel slot styles to theme.css**

Open `dashboard/static/theme.css` and append at the end:

```css
/* ── Activity bar ─────────────────────────────────────────────── */
.activity-bar {
  flex: 0 0 42px !important;
  width: 42px !important;
  min-width: 42px !important;
  max-width: 42px !important;
  background: #1a1816 !important;
  border-right: 1px solid var(--border-subtle) !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  padding: 6px 0 !important;
  min-height: 0 !important;
  box-sizing: border-box !important;
  z-index: 10;
}

.activity-bar-top {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex: 1 1 auto;
}

.activity-bar-bottom {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.activity-bar-btn {
  width: 34px;
  height: 34px;
  background: transparent !important;
  border: none !important;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  cursor: pointer;
  opacity: 0.4;
  position: relative;
  transition: opacity 0.12s;
  outline: none !important;
  padding: 0;
  box-sizing: border-box;
}

.activity-bar-btn:hover {
  opacity: 0.75;
}

.activity-bar-btn.active {
  opacity: 1.0;
}

/* VSCode-style: 2px colored left-edge bar on the active item */
.activity-bar-btn.active::before {
  content: '';
  position: absolute;
  left: -5px;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 20px;
  background: var(--accent);
  border-radius: 0 2px 2px 0;
}

/* ── Main panel (wraps all switchable panel slots) ────────────── */
.main-panel {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  min-width: 0 !important;
  display: flex !important;
  flex-direction: column !important;
  overflow: hidden !important;
}

/* Individual panel slots — JS sets display:flex on active, display:none on rest */
.panel-slot {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  overflow: hidden !important;
}

/* Pane backgrounds via new class names */
.bk-column.main-panel > .bk-panel-models-layout-Column {
  min-height: 0 !important;
}
```

- [ ] **Step 2: Verify no existing rule conflicts**

Run: `grep -n "activity-bar\|panel-slot\|main-panel" dashboard/static/theme.css`

Expected: only the lines you just added appear.

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/theme.css
git commit -m "style: add activity-bar and panel-slot CSS"
```

---

## Task 2: settings_page.py

**Files:**
- Create: `dashboard/pages/settings_page.py`
- Create: `tests/test_activity_bar_layout.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_activity_bar_layout.py`:

```python
"""Smoke tests for activity-bar layout — settings page and app assembly."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import panel as pn


def test_settings_page_builds():
    from dashboard.pages.settings_page import build_settings_page
    widget = build_settings_page()
    assert widget is not None
    assert isinstance(widget, pn.viewable.Viewable)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_activity_bar_layout.py::test_settings_page_builds -v`

Expected: `ModuleNotFoundError` for `dashboard.pages.settings_page`.

- [ ] **Step 3: Create settings_page.py**

Create `dashboard/pages/settings_page.py`:

```python
"""Settings panel for the 4Dpapers dashboard."""
from __future__ import annotations

import panel as pn

from dashboard.theme import THEME


def build_settings_page() -> pn.viewable.Viewable:
    """Return a Panel widget for the settings panel."""
    heading = pn.pane.HTML(
        '<div style="font-size:11px;font-weight:600;letter-spacing:.08em;'
        'text-transform:uppercase;color:#d4eefc;padding:8px 8px 4px 8px;">'
        "Settings</div>",
        sizing_mode="stretch_width",
        margin=0,
    )
    note = pn.pane.HTML(
        '<div style="font-size:11px;color:#888;padding:4px 8px;">'
        "More settings coming soon.</div>",
        sizing_mode="stretch_width",
        margin=0,
    )
    return pn.Column(
        heading,
        note,
        sizing_mode="stretch_both",
        styles={"min-height": "0", "background": THEME["bg_sidebar"]},
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_activity_bar_layout.py::test_settings_page_builds -v`

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add dashboard/pages/settings_page.py tests/test_activity_bar_layout.py
git commit -m "feat: add settings panel page"
```

---

## Task 3: activity_bar.js

**Files:**
- Create: `dashboard/static/activity_bar.js`

- [ ] **Step 1: Create activity_bar.js**

Create `dashboard/static/activity_bar.js`:

```javascript
// activity_bar.js — config-driven panel switching for 4Dpapers dashboard
(function () {
  if (window.__4dpapersActivityBarDone) return;
  window.__4dpapersActivityBarDone = true;

  var LS_ACTIVE = "4dpapers.layout.activePanel";

  function deepQuerySelector(selector) {
    var found = null;
    function searchRoot(root) {
      if (!root || found) return;
      try {
        var hit = root.querySelector(selector);
        if (hit) { found = hit; return; }
      } catch (e) {}
      var all = root.querySelectorAll("*");
      for (var i = 0; i < all.length; i++) {
        if (all[i].shadowRoot) searchRoot(all[i].shadowRoot);
      }
    }
    searchRoot(document.documentElement);
    return found;
  }

  function switchPanel(panelId) {
    var config = window.SPLIT_CONFIG;
    if (!config || !config.panels) return;

    // Hide all panel slots
    config.panels.forEach(function (p) {
      var slot = deepQuerySelector(".panel-slot--" + p.id);
      if (slot) slot.style.setProperty("display", "none", "important");
    });

    // Show target slot
    var target = deepQuerySelector(".panel-slot--" + panelId);
    if (target) target.style.setProperty("display", "flex", "important");

    // Update active indicator on buttons
    var btns = document.querySelectorAll(".activity-bar-btn");
    btns.forEach(function (btn) {
      if (btn.dataset.panelId === panelId) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    localStorage.setItem(LS_ACTIVE, panelId);
  }

  // Expose for onclick handlers in Python-generated activity bar HTML
  window.__activityBarSwitch = switchPanel;

  function restoreActivePanel() {
    var config = window.SPLIT_CONFIG;
    if (!config || !config.panels) return;
    var saved = localStorage.getItem(LS_ACTIVE);
    var ids = config.panels.map(function (p) { return p.id; });
    var active = (saved && ids.indexOf(saved) !== -1) ? saved : config.defaultPanel;
    switchPanel(active);
  }

  function init() {
    var bar = document.getElementById("activity-bar");
    if (!bar) return false;
    // SPLIT_CONFIG must also be present before we restore state
    if (!window.SPLIT_CONFIG) return false;
    restoreActivePanel();
    return true;
  }

  if (init()) return;

  var pollN = 0;
  var poll = setInterval(function () {
    pollN++;
    if (init()) { clearInterval(poll); return; }
    if (pollN > 120) { clearInterval(poll); }
  }, 100);
})();
```

- [ ] **Step 2: Verify file created**

Run: `wc -l dashboard/static/activity_bar.js`

Expected: ~60 lines.

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/activity_bar.js
git commit -m "feat: add activity_bar.js config-driven panel switcher"
```

---

## Task 4: Update split_loader.js to inject activity_bar.js

**Files:**
- Modify: `dashboard/static/split_loader.js`

- [ ] **Step 1: Replace split_loader.js**

Overwrite `dashboard/static/split_loader.js` with the following (bumps version to 103, adds activity_bar.js injection):

```javascript
/**
 * Loads split_pane.js and activity_bar.js only after the Panel app shell
 * exists in the DOM. pn.extension js_files run from <head> before Bokeh
 * paints the toolbar, so scripts used to run too early.
 */
(function () {
  if (window.__4dpapersSplitLoaderDone) return;
  window.__4dpapersSplitLoaderDone = true;

  var SPLIT_SRC = "/assets/split_pane.js?v=103";
  var ACTIVITY_SRC = "/assets/activity_bar.js?v=103";

  function markFailed(msg) {
    var el =
      document.getElementById("split-status") ||
      document.querySelector(".split-status-target");
    if (el) el.textContent = msg;
  }

  function injectScript(src, attr) {
    if (document.querySelector('script[' + attr + ']')) return;
    var script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.setAttribute(attr, "1");
    script.onerror = function () { markFailed("failed to load " + src); };
    document.head.appendChild(script);
  }

  function inject() {
    injectScript(SPLIT_SRC, "data-4dpapers-split-pane");
    injectScript(ACTIVITY_SRC, "data-4dpapers-activity-bar");
  }

  function readyEnough() {
    return (
      document.body &&
      (document.querySelector(".app-shell") || document.querySelector(".body-row"))
    );
  }

  var tries = 0;
  var timer = setInterval(function () {
    tries++;
    if (readyEnough() || tries > 200) {
      clearInterval(timer);
      inject();
    }
  }, 50);
})();
```

- [ ] **Step 2: Verify the old single-script reference is gone**

Run: `grep "split_pane\|activity_bar" dashboard/static/split_loader.js`

Expected: both `split_pane.js?v=103` and `activity_bar.js?v=103` appear.

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/split_loader.js
git commit -m "feat: split_loader injects activity_bar.js alongside split_pane"
```

---

## Task 5: Rewrite split_pane.js to 2-pane

**Files:**
- Modify: `dashboard/static/split_pane.js`

- [ ] **Step 1: Overwrite split_pane.js with 2-pane version**

Overwrite `dashboard/static/split_pane.js`:

```javascript
// split_pane.js - v20: 2-pane layout, reads config from window.SPLIT_CONFIG
(function boot() {
  window.SPLIT_VERSION = 20;

  if (window.__splitDone) return;

  var LS_MAIN = "4dpapers.pane.mainWidth";
  var MIN_MAIN = 200;
  var MIN_PREVIEW = 320;
  var GUTTER_WIDTH = 8;

  function deepQuerySelector(selector) {
    var found = null;
    function searchRoot(root) {
      if (!root || found) return;
      try {
        var hit = root.querySelector(selector);
        if (hit) { found = hit; return; }
      } catch (e) {}
      var all = root.querySelectorAll("*");
      for (var i = 0; i < all.length; i++) {
        if (all[i].shadowRoot) searchRoot(all[i].shadowRoot);
      }
    }
    searchRoot(document.documentElement);
    return found;
  }

  function findStatusEl() {
    return (
      document.getElementById("split-status") ||
      document.querySelector(".split-status-target") ||
      deepQuerySelector("#split-status") ||
      deepQuerySelector(".split-status-target") ||
      deepQuerySelector("[data-split-status]")
    );
  }

  function setStatus(text) {
    function apply() {
      var el = findStatusEl();
      if (!el) return false;
      el.textContent = text;
      return true;
    }
    if (apply()) return;
    var tries = 0;
    var id = setInterval(function () {
      tries++;
      if (apply() || tries > 200) clearInterval(id);
    }, 50);
  }

  function applyWrap() {
    if (typeof ace === "undefined") return;
    document.querySelectorAll(".ace_editor").forEach(function (el) {
      try {
        var editor = ace.edit(el);
        editor.session.setUseWrapMode(true);
        editor.resize();
      } catch (e) {}
    });
  }

  function clamp(n, lo, hi) { return Math.max(lo, Math.min(hi, n)); }

  function setFixedWidth(el, px) {
    if (!el) return;
    el.style.setProperty("flex", "0 0 " + px + "px", "important");
    el.style.setProperty("width", px + "px", "important");
    el.style.setProperty("min-width", px + "px", "important");
    el.style.setProperty("max-width", px + "px", "important");
  }

  function clearFixedWidth(el) {
    if (!el) return;
    el.style.removeProperty("flex");
    el.style.removeProperty("width");
    el.style.removeProperty("min-width");
    el.style.removeProperty("max-width");
  }

  function reflow() {
    applyWrap();
    try { window.dispatchEvent(new Event("resize")); } catch (e) {}
  }

  function usableWidth(mainEl, previewEl) {
    var r1 = mainEl.getBoundingClientRect();
    var r2 = previewEl.getBoundingClientRect();
    return Math.max(0, (r2.right - r1.left) - GUTTER_WIDTH);
  }

  function getElements() {
    var cfg = window.SPLIT_CONFIG || {};
    var gutterSel = cfg.gutterSelector || "[class*='split-gutter--between-main-preview']";
    var mainSel   = cfg.mainPanelSelector  || ".main-panel";
    var previewSel = cfg.previewPanelSelector || ".pane-right";
    return {
      gutter:  deepQuerySelector(gutterSel),
      main:    deepQuerySelector(mainSel),
      preview: deepQuerySelector(previewSel),
    };
  }

  function layoutFromStorage(els) {
    var rowW = usableWidth(els.main, els.preview);
    if (!rowW) return;
    var saved = parseInt(localStorage.getItem(LS_MAIN) || "", 10);
    if (!Number.isFinite(saved)) return;
    var w = clamp(saved, MIN_MAIN, rowW - MIN_PREVIEW);
    clearFixedWidth(els.preview);
    setFixedWidth(els.main, w);
  }

  function init() {
    if (window.__splitDone) return true;

    var els = getElements();
    if (!els.gutter || !els.main || !els.preview) {
      setStatus("split: waiting layout");
      return false;
    }

    window.__splitDone = true;
    layoutFromStorage(els);
    setStatus("split: ready v20");

    var startX = 0;
    var startMainW = 0;

    els.gutter.addEventListener("mousedown", function (e) {
      startX = e.clientX;
      startMainW = els.main.getBoundingClientRect().width;
    }, { capture: true });

    els.gutter.addEventListener("mousedown", function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      els.gutter.classList.add("__split-dragging");
      document.body.style.cursor = "ew-resize";
      document.body.style.userSelect = "none";

      function onMove(ev) {
        var rowW = usableWidth(els.main, els.preview);
        var dx = ev.clientX - startX;
        setFixedWidth(els.main, clamp(startMainW + dx, MIN_MAIN, rowW - MIN_PREVIEW));
      }
      function onUp() {
        window.removeEventListener("mousemove", onMove, true);
        window.removeEventListener("mouseup", onUp, true);
        els.gutter.classList.remove("__split-dragging");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        localStorage.setItem(LS_MAIN, String(els.main.getBoundingClientRect().width | 0));
        reflow();
      }
      window.addEventListener("mousemove", onMove, true);
      window.addEventListener("mouseup", onUp, true);
    }, true);

    window.addEventListener("resize", reflow);
    reflow();
    return true;
  }

  setStatus("split: loading...");
  if (init()) return;

  var pollN = 0;
  var poll = setInterval(function () {
    pollN++;
    if (init()) { clearInterval(poll); return; }
    if (pollN % 10 === 0) setStatus("split: waiting DOM... (" + pollN + ")");
    if (pollN > 120) { clearInterval(poll); setStatus("split: failed"); }
  }, 100);

  if (typeof MutationObserver !== "undefined") {
    try {
      var mo = new MutationObserver(function () {
        if (window.__splitDone) return;
        if (init()) {
          try { clearInterval(poll); } catch (e) {}
          try { mo.disconnect(); } catch (e2) {}
        }
      });
      mo.observe(document.body, { childList: true, subtree: true });
    } catch (e) {}
  }
})();
```

- [ ] **Step 2: Verify 3-pane references removed**

Run: `grep -c "MIN_CENTER\|pane-left\|pane-center\|LS_LEFT\|LS_RIGHT\|leftCenter\|centerRight" dashboard/static/split_pane.js`

Expected: `0`

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/split_pane.js
git commit -m "refactor: trim split_pane.js to 2-pane, read config from SPLIT_CONFIG"
```

---

## Task 6: Rewrite app.py — PANELS loop and new layout

**Files:**
- Modify: `dashboard/app.py`
- Modify: `tests/test_activity_bar_layout.py`

- [ ] **Step 1: Add helper-function tests to test_activity_bar_layout.py**

Append to `tests/test_activity_bar_layout.py`:

```python
def test_split_config_script_contains_panels():
    """_build_split_config_script embeds all panel IDs and sets SPLIT_CONFIG."""
    from dashboard.app import _build_split_config_script
    panels = [
        {"id": "explorer", "icon": "📁", "label": "Files"},
        {"id": "editor",   "icon": "📝", "label": "Editor"},
    ]
    script = _build_split_config_script(panels, default_panel="explorer")
    assert "explorer" in script
    assert "editor" in script
    assert "SPLIT_CONFIG" in script
    assert "<script>" in script


def test_build_activity_bar_html_has_buttons():
    """_build_activity_bar_html returns one button per panel; bottom items in activity-bar-bottom."""
    from dashboard.app import _build_activity_bar_html
    panels = [
        {"id": "explorer", "icon": "📁", "label": "Files"},
        {"id": "settings", "icon": "⚙️", "label": "Settings", "bottom": True},
    ]
    html = _build_activity_bar_html(panels)
    assert 'data-panel-id="explorer"' in html
    assert 'data-panel-id="settings"' in html
    assert "activity-bar-bottom" in html
```

- [ ] **Step 2: Run to verify new tests fail**

Run: `.venv/bin/python -m pytest tests/test_activity_bar_layout.py -v`

Expected: `test_split_config_script_contains_panels` and `test_build_activity_bar_html_has_buttons` both fail with `ImportError` (`cannot import name '_build_split_config_script'`).

- [ ] **Step 3: Replace app.py**

Replace the full content of `dashboard/app.py` with:

```python
"""
4Dpaper Dashboard - main Panel app.

Launch with:
    panel serve dashboard/app.py --plugins dashboard.plugins \
        --static-dirs output=_output assets=dashboard/static state=state --show --port 5006
from the 4Dpapers repository root.
"""
from __future__ import annotations

import json
import threading
import sys
from pathlib import Path

_repo_root = Path(__file__).parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import panel as pn

from dashboard.file_tree import (
    EXPLORER_BUTTON_STYLESHEETS,
    EXPLORER_INNER_WIDTH,
    EXPLORER_LIST_BTN_STYLES,
    build_file_tree_sidebar,
)
from dashboard.figure_browser import build_figure_insert_form
from dashboard.pages.paper_page import build_paper_page
from dashboard.pages.settings_page import build_settings_page
from dashboard.theme import THEME
from dashboard.utils import load_config

_RAW_CSS = """
#header{display:none!important;height:0!important}
html,body{overflow-x:hidden!important;margin:0!important;padding:0!important;background:#000!important;height:100%!important}
.container-fluid{padding:0!important;max-width:100%!important;height:100%!important;min-height:0!important;display:flex!important;flex-direction:column!important}
#main{padding:0!important;flex:1 1 auto!important;min-height:0!important;display:flex!important;flex-direction:column!important}
div.ace_editor{overflow:hidden!important}
div.ace_editor div.ace_scroller{overflow-x:hidden!important}
div.ace_editor div.ace_scrollbar-h{display:none!important;height:0!important}
div.ace_editor div.ace_content{overflow-x:hidden!important}
.ace_editor .ace_cursor{border-left:2px solid #e6e6e6!important}
.ace_editor.ace_focus .ace_cursor{border-left:2px solid #ffffff!important}
.ace_editor .ace_hidden-cursors .ace_cursor{opacity:1!important}
#split-status{color:#8ab4ff;font-size:10px;font-family:monospace;opacity:0.9;margin-left:8px;}
.app-shell{height:100vh!important;min-height:0!important;display:flex!important;flex-direction:column!important;box-sizing:border-box!important}
.app-shell .body-row{flex:1 1 auto!important;min-height:0!important;width:100%!important;display:flex!important;flex-direction:row!important;align-items:stretch!important;position:relative!important;overflow:visible!important}
.app-shell .body-row > *:not(.split-gutter){min-height:0!important;min-width:0!important}
.split-gutter{
  flex:0 0 8px!important;min-width:8px!important;max-width:8px!important;width:8px!important;
  min-height:0!important;padding:0!important;margin:0!important;box-sizing:border-box!important;
  cursor:ew-resize!important;user-select:none!important;-webkit-user-select:none!important;
  background:rgba(55,65,80,0.55)!important;
  border-left:1px solid rgba(255,255,255,0.2)!important;border-right:1px solid rgba(0,0,0,0.35)!important;
}
.split-gutter:hover,.split-gutter.__split-dragging{background:rgba(13,110,253,0.45)!important}
.split-gutter .__split_handle{
  min-height:100%!important;height:100%!important;width:100%!important;
  pointer-events:auto!important;cursor:ew-resize!important;
}
"""

pn.extension(
    "codeeditor",
    sizing_mode="stretch_width",
    template="bootstrap",
    raw_css=[_RAW_CSS],
    css_files=["/assets/theme.css?v=103"],
    js_files={
        "insert_figure": "/assets/insert_figure_overlay.js?v=103",
        "split_loader": "/assets/split_loader.js?v=103",
    },
)


def _split_gutter(between: str) -> pn.Column:
    handle = pn.pane.HTML(
        '<div class="__split_handle" role="separator" aria-orientation="vertical" '
        'title="Drag to resize panes"></div>',
        sizing_mode="stretch_both",
        margin=0,
    )
    return pn.Column(
        handle,
        sizing_mode="stretch_height",
        width=8,
        margin=0,
        css_classes=["split-gutter", f"split-gutter--between-{between}"],
        styles={
            "flex": "0 0 8px",
            "min-width": "8px",
            "max-width": "8px",
            "width": "8px",
            "min-height": "0",
            "padding": "0",
            "background": "rgba(55,65,80,0.55)",
            "border-left": "1px solid rgba(255,255,255,0.2)",
            "border-right": "1px solid rgba(0,0,0,0.35)",
        },
    )


def _build_split_config_script(panels: list[dict], default_panel: str) -> str:
    """Return an inline <script> that sets window.SPLIT_CONFIG from PANELS."""
    panel_entries = [
        {
            "id": p["id"],
            "icon": p["icon"],
            "label": p["label"],
            "selector": f".panel-slot--{p['id']}",
            **({"bottom": True} if p.get("bottom") else {}),
        }
        for p in panels
    ]
    config = {
        "panels": panel_entries,
        "defaultPanel": default_panel,
        "mainPanelSelector": ".main-panel",
        "previewPanelSelector": ".pane-right",
        "gutterSelector": "[class*='split-gutter--between-main-preview']",
    }
    return f"<script>window.SPLIT_CONFIG = {json.dumps(config)};</script>"


def _build_activity_bar_html(panels: list[dict]) -> str:
    """Return HTML string for the activity bar (injected via pn.pane.HTML)."""
    def btn(p: dict) -> str:
        return (
            f'<button class="activity-bar-btn" data-panel-id="{p["id"]}" '
            f'title="{p["label"]}" '
            f'onclick="if(window.__activityBarSwitch)window.__activityBarSwitch(\'{p["id"]}\');">'
            f'{p["icon"]}'
            f"</button>"
        )

    top_items = [p for p in panels if not p.get("bottom")]
    bottom_items = [p for p in panels if p.get("bottom")]
    top_html = "".join(btn(p) for p in top_items)
    bottom_html = "".join(btn(p) for p in bottom_items)

    return (
        '<div class="activity-bar" id="activity-bar">'
        f'<div class="activity-bar-top">{top_html}</div>'
        f'<div class="activity-bar-bottom">{bottom_html}</div>'
        "</div>"
    )


def create_app():
    config = load_config()
    qmd_path = Path(config["quarto_paper_path"])

    qmd_content = qmd_path.read_text(encoding="utf-8") if qmd_path.exists() else (
        f"# File not found\n\n`{qmd_path}` does not exist.\n\n"
        "Update `quarto_paper_path` in `dashboard/config.yaml`."
    )
    editor = pn.widgets.CodeEditor(
        value=qmd_content,
        language="markdown",
        sizing_mode="stretch_both",
        min_height=400,
        theme="tomorrow_night",
    )

    current_file = {"path": str(qmd_path)}
    save_status = pn.pane.HTML(
        "",
        width=220,
        visible=False,
        styles={
            "font-size": "11px",
            "color": THEME["text_muted"],
            "white-space": "nowrap",
            "overflow": "hidden",
            "text-overflow": "ellipsis",
        },
    )
    _save_timer: list[threading.Timer] = []

    def _set_save_status(text: str) -> None:
        save_status.object = text
        save_status.visible = True
        for timer in _save_timer:
            timer.cancel()
        _save_timer.clear()
        doc = pn.state.curdoc

        def _hide():
            if doc is None:
                return
            try:
                doc.add_next_tick_callback(lambda: setattr(save_status, "visible", False))
            except Exception:
                pass

        timer = threading.Timer(3.0, _hide)
        timer.daemon = True
        timer.start()
        _save_timer.append(timer)

    def _write_editor_to_current_file() -> None:
        target = current_file["path"]
        if not target:
            return
        Path(target).write_text(editor.value, encoding="utf-8")

    def _on_file_click(file_path: str, language: str):
        if current_file["path"]:
            try:
                _write_editor_to_current_file()
            except Exception:
                pass
        current_file["path"] = file_path
        editor.value = Path(file_path).read_text(encoding="utf-8")
        editor.language = language

    save_btn = pn.widgets.Button(
        name="Save",
        button_type="default",
        width=88,
        height=26,
        margin=(0, 2),
        styles={"font-size": "11px"},
    )

    def _on_save(_event):
        try:
            _write_editor_to_current_file()
            _set_save_status(f"Saved {Path(current_file['path']).name}")
        except Exception as exc:
            _set_save_status(f"Save failed: {exc}")

    save_btn.on_click(_on_save)

    _ace_wrap = pn.widgets.Button(name="", width=1, height=1, margin=0, visible=False)
    _ace_wrap.jscallback(
        clicks="""
        (function(){
            function wrap(){
                document.querySelectorAll('.ace_editor').forEach(function(el){
                    try{
                        var ed=ace.edit(el);
                        ed.session.setUseWrapMode(true);
                        if(ed.renderer && ed.renderer.$scrollbarV)
                            ed.renderer.$scrollbarV.element.style.overflowX='hidden';
                        ed.resize();
                    }catch(e){}
                });
            }
            if(typeof ace==='undefined'){setTimeout(function(){wrap();},300);return;}
            wrap();
            setTimeout(wrap,600);
            setTimeout(wrap,1500);
        })();
        """,
    )
    pn.state.onload(lambda: setattr(_ace_wrap, "clicks", 1))

    # ── Build panel contents ───────────────────────────────────────────────
    insert_figure_btn = pn.widgets.Button(
        name="Insert figure",
        icon="photo",
        icon_size="11px",
        button_type="default",
        button_style="outline",
        width=EXPLORER_INNER_WIDTH,
        sizing_mode="fixed",
        margin=(0, 0, 2, 0),
        css_classes=["dash-explorer-item", "dash-explorer-refresh"],
        styles={**EXPLORER_LIST_BTN_STYLES, "color": "#9fd4f5", "font-size": "13px"},
        stylesheets=[EXPLORER_BUTTON_STYLESHEETS],
    )
    insert_figure_btn.js_on_click(
        code="if (window.showInsertFigureModal) window.showInsertFigureModal();",
    )

    explorer_view = build_file_tree_sidebar(
        project_root=qmd_path.parent,
        on_file_click=_on_file_click,
        insert_figure_button=insert_figure_btn,
    )
    explorer_view.sizing_mode = "stretch_both"
    explorer_view.styles = {**getattr(explorer_view, "styles", {}), "min-height": "0"}

    editor_view = pn.Column(
        editor,
        _ace_wrap,
        sizing_mode="stretch_both",
        styles={"min-height": "0", "background": THEME["bg_panel"]},
    )

    figure_browser_view = build_figure_insert_form(
        editor=editor,
        qmd_path=qmd_path,
        config=config,
    )
    figure_browser_view.sizing_mode = "stretch_both"
    figure_browser_view.styles = {
        **getattr(figure_browser_view, "styles", {}),
        "min-height": "0",
        "background": THEME["bg_sidebar"],
    }

    settings_view = build_settings_page()

    paper_content, paper_page = build_paper_page(config)

    # ── PANELS config (single source of truth for layout) ─────────────────
    DEFAULT_PANEL = "explorer"
    PANELS = [
        {"id": "explorer", "icon": "📁", "label": "Files",    "content": explorer_view},
        {"id": "editor",   "icon": "📝", "label": "Editor",   "content": editor_view},
        {"id": "figures",  "icon": "🖼️", "label": "Figures",  "content": figure_browser_view},
        {"id": "settings", "icon": "⚙️", "label": "Settings", "content": settings_view, "bottom": True},
    ]

    # ── Build panel slots (all rendered, hidden by default except DEFAULT) ─
    panel_slots = []
    for p in PANELS:
        initial_display = "flex" if p["id"] == DEFAULT_PANEL else "none"
        slot = pn.Column(
            p["content"],
            sizing_mode="stretch_both",
            styles={"min-height": "0", "display": initial_display},
            css_classes=["panel-slot", f"panel-slot--{p['id']}"],
        )
        panel_slots.append(slot)

    main_panel = pn.Column(
        *panel_slots,
        sizing_mode="stretch_both",
        min_width=200,
        styles={"min-height": "0", "flex": "1 1 auto"},
        css_classes=["main-panel"],
    )

    preview_container = pn.Column(
        paper_content,
        sizing_mode="stretch_both",
        min_width=320,
        styles={"min-height": "0", "flex": "1 1 auto"},
        css_classes=["pane-right", "preview-pane"],
    )

    # ── Emit SPLIT_CONFIG before JS runs ──────────────────────────────────
    split_config_pane = pn.pane.HTML(
        _build_split_config_script(PANELS, DEFAULT_PANEL),
        width=0,
        height=0,
        margin=0,
        styles={"display": "none"},
    )

    # ── Activity bar ──────────────────────────────────────────────────────
    activity_bar_pane = pn.pane.HTML(
        _build_activity_bar_html(PANELS),
        sizing_mode="stretch_height",
        width=42,
        margin=0,
        styles={"flex": "0 0 42px", "min-height": "0"},
    )

    # ── Toolbar ───────────────────────────────────────────────────────────
    toolbar = pn.Row(
        pn.pane.HTML(
            '<span class="dash-toolbar-title" '
            'style="font-size:12px;font-weight:600;color:#fff;">4Dpaper</span>',
            width=72,
            margin=(0, 6, 0, 2),
        ),
        pn.layout.HSpacer(),
        save_btn,
        save_status,
        paper_page.rebuild_btn,
        paper_page.export_btn,
        paper_page.pdf_link,
        pn.pane.HTML(
            f'<span style="color:{THEME["border_subtle"]};font-size:14px">|</span>',
            margin=(2, 4),
        ),
        pn.pane.HTML(
            '<span id="split-status" class="split-status-target" '
            'data-split-status="1">split: ...</span>',
        ),
        sizing_mode="stretch_width",
        height=32,
        margin=0,
        styles={
            "padding": "2px 8px",
            "background": THEME["toolbar_bg"],
            "border-bottom": f"1px solid {THEME['border_subtle']}",
            "align-items": "center",
        },
    )

    body = pn.Row(
        split_config_pane,
        activity_bar_pane,
        main_panel,
        _split_gutter("main-preview"),
        preview_container,
        sizing_mode="stretch_both",
        styles={"min-height": "0", "flex": "1 1 auto"},
        css_classes=["body-row"],
    )

    return pn.Column(
        toolbar,
        body,
        sizing_mode="stretch_both",
        css_classes=["app-shell"],
        styles={
            "border": f"1px solid {THEME['border_subtle']}",
            "background": THEME["bg_app"],
            "overflow": "hidden",
            "min-height": "0",
            "flex": "1 1 auto",
        },
    )


app = create_app()
app.servable()
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/python -m pytest tests/test_activity_bar_layout.py tests/test_pages.py -v`

Expected: all tests pass.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `.venv/bin/python -m pytest tests/ -v --ignore=tests/test_vtk_figure.py --ignore=tests/test_pvsm.py --ignore=tests/test_pvsm_figure.py -x`

Expected: all pass (vtk/pvsm tests require ParaView so excluded).

- [ ] **Step 6: Commit**

```bash
git add dashboard/app.py tests/test_activity_bar_layout.py
git commit -m "feat: config-driven activity bar layout — PANELS list replaces hardcoded 3-pane"
```

---

## Task 7: Manual verification

- [ ] **Step 1: Start the dashboard**

```bash
panel serve dashboard/app.py --plugins dashboard.plugins \
    --static-dirs output=_output assets=dashboard/static state=state --show --port 5006
```

- [ ] **Step 2: Check activity bar renders**

Open `http://localhost:5006`. Verify:
- Thin vertical strip on the far left (42px)
- Four icons: 📁 📝 🖼️ with ⚙️ pinned at bottom
- Active icon (📁 by default) shows the 2px teal left-edge bar, others are dimmed

- [ ] **Step 3: Check panel switching**

Click each icon and verify the main panel content changes:
- 📁 → File explorer (tree view)
- 📝 → Code editor (ACE)
- 🖼️ → Figure browser form
- ⚙️ → "Settings — More settings coming soon."

- [ ] **Step 4: Check panel persistence**

Click 📝, refresh the page. Verify the editor panel is still active (not the default explorer).

- [ ] **Step 5: Check split gutter**

Drag the gutter between main panel and preview. Verify it resizes correctly. Reload and verify width is restored from localStorage.

- [ ] **Step 6: Check ACE editor reflow**

Switch to editor, resize the gutter. Verify the ACE editor reflows (text wraps correctly, no frozen editor).

- [ ] **Step 7: Commit verification note**

```bash
git commit --allow-empty -m "chore: manual verification complete — activity bar layout working"
```
