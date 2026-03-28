# Panel IDE 3‑Pane Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current DOM overlay resizer + sidebar toggles with a robust, IDE-like 3‑pane layout in Panel (tabs + min widths) while preserving existing editor/preview/figure/camera logic.

**Architecture:** Keep a single `pn.widgets.CodeEditor` and a single `PaperPage` instance. Wrap the existing sidebar/editor/preview panes inside `pn.Tabs` for “IDE shell” structure. Replace `dashboard/static/split_pane.js` with a simpler, deterministic splitter script that only targets known pane markers and enforces min widths; remove dimension/shadow-root heuristics.

**Tech Stack:** Panel (Bokeh), Python, small custom JS/CSS in `dashboard/static/`.

---

## File Map (what we will touch)

**Modify**
- `dashboard/app.py` — restructure layout into tabbed panes; move “Insert Figure” into a left-pane tab; remove old sidebar/preview toggles if superseded; add stable CSS hooks for split.
- `dashboard/static/split_pane.js` — rewrite splitter to target the new layout deterministically; enforce min widths; persist widths (optional).
- `dashboard/file_tree.py` — (minimal) export a variant that returns the *contents* without fixed width, or accept a `width` parameter so it can live inside tabs cleanly.
- `dashboard/figure_browser.py` — add a “root selector” (Project vs Cases) that updates `FileSelector.directory`; ensure widths follow container sizing.

**No changes expected**
- `dashboard/pages/paper_page.py` — preserve rebuild/export logic and overlay behavior.
- `dashboard/static/camera_overlay.js` — preserve postMessage + `/camera/<id>` behavior.
- `dashboard/plugins.py` — preserve routes.

**Docs**
- `docs/superpowers/specs/2026-03-25-panel-ide-3pane-layout-design.md` — already approved.

## Task 1: Establish stable pane structure + tabs in `dashboard/app.py`

**Files:**
- Modify: `dashboard/app.py`

- [ ] **Step 0: Sizing prerequisites (do this before tabs/splitters)**
  - Ensure `body` and each pane container uses `sizing_mode="stretch_both"` (or appropriate stretch) and intermediate containers have styles like `{"min-height": "0"}` so children can shrink/grow inside flex layouts.
  - Add `overflow: hidden` where needed to avoid horizontal scrollbars in the main shell.

- [ ] **Step 1: Add stable CSS hooks and IDs**
  - Add explicit `css_classes`/markers for each pane: left, center, right.
  - Ensure there is a deterministic “pane container” element per pane so splitter JS never needs heuristics.

- [ ] **Step 2: Convert panes into tabs (IDE shell)**
  - Left: `pn.Tabs(("Files", files_view), ("Insert Figure", insert_figure_view), dynamic=False, sizing_mode="stretch_both")`
  - Center: `pn.Tabs(("Editor", editor_view), dynamic=False, sizing_mode="stretch_both")` (single tab initially)
  - Right: `pn.Tabs(("Preview", preview_view), dynamic=False, sizing_mode="stretch_both")` (optional “Build log” later)
  - Acceptance check: switching tabs must **not** destroy/recreate the editor DOM; editor focus/selection should remain stable.

- [ ] **Step 3: Preserve single instances (no recreation)**
  - Confirm `CodeEditor` is created once and passed to:
    - `_on_file_click` handler
    - `build_figure_insert_form(editor, ...)`
  - Confirm `PaperPage` object (from `build_paper_page`) is created once and its `rebuild_btn/export_btn/pdf_link` are used in the toolbar as today.

- [ ] **Step 4: Remove/adjust old toggles**
  - Remove `stog`/`ptog` (or repurpose to switch tabs) so visibility toggling doesn’t collapse panes unpredictably.
  - Acceptance target: left pane never collapses below min width.

- [ ] **Step 5: Quick manual verification**
  - Run the app and verify:
    - file clicks still save + load
    - Insert Figure still appends into editor
    - Preview rebuild/export still works

## Task 2: Make Insert Figure feel like “local folders” (root selector)

**Files:**
- Modify: `dashboard/figure_browser.py`

- [ ] **Step 1: Add a root selector UI**
  - Add a `pn.widgets.RadioButtonGroup` (or `Select`) with options:
    - `Project` → `directory = str(qmd_path.parent)`
    - `Cases` → `directory = config.get("cardiacfoam_root", str(Path.home()))`

- [ ] **Step 2: Wire selector to FileSelector**
  - On change, set `file_selector.directory = chosen_root`
  - Keep `file_pattern="*.foam"` and existing timestep detection logic.

- [ ] **Step 3: Verify behavior**
  - Selecting Project root shows local folders under the repo/project
  - Selecting Cases root restores current behavior
  - Shortcode generation + copy-to-data still work

## Task 3: Replace splitter JS with deterministic resizer (min widths)

**Files:**
- Modify: `dashboard/static/split_pane.js`
- Modify: `dashboard/app.py` (if CSS class hooks need adjustment)

- [ ] **Step 0: Decision gate**
  - Preferred: use a Panel/Bokeh-supported splitter or model-based sizing if it exists in this codebase/environment.
  - Fallback: DOM-based splitter JS is acceptable, but it must be deterministic and must trigger a reliable reflow after drag end (so widgets recompute sizes without requiring a window resize).

- [ ] **Step 1: Remove deep/shadow-root search + dimension fallback**
  - Replace `findElement()` recursion with direct `document.querySelector()` calls for known hooks (e.g., `.body-row`, `.pane-left`, `.pane-center`, `.pane-right`).

- [ ] **Step 2: Implement two resize handles**
  - Handle 1 between left and center
  - Handle 2 between center and right
  - Set widths via inline styles on the pane containers:
    - left: `flex: 0 0 <px>` with `min-width` enforced
    - center: flex grow/shrink, with optional explicit width when dragging handle 2
  - Enforce minimum widths:
    - left >= 240px
    - center >= 360px
    - right >= 360px

- [ ] **Step 3: Persist widths (optional, but recommended)**
  - Store left width + right width in `localStorage` keyed by project/app (e.g., `4dpapers.pane.leftWidth`, `4dpapers.pane.rightWidth`)
  - On boot, apply saved widths if present.

- [ ] **Step 4: Ensure editor wrap + resize still work**
  - Keep the existing Ace wrap helper (`setUseWrapMode(true)` + `resize()`) but call it:
    - after drag end
    - after tab switches (if needed, add a small timeout)
  - Add a reflow trigger after drag end (e.g., dispatch a window `resize` event or equivalent) and verify the preview iframe/editor reflow without manual window resizing.

- [ ] **Step 5: Manual verification**
  - Drag both handles and confirm:
    - panes resize smoothly
    - panes never go below minimum widths
    - CodeEditor and preview iframe remain usable and fill height

## Task 4: Sidebar + tab sizing cleanup (overflow/height)

**Files:**
- Modify: `dashboard/app.py`
- Modify: `dashboard/file_tree.py` (if needed)
- Possibly modify: `dashboard/pages/paper_page.py` (only if necessary for sizing, not logic)

- [ ] **Step 1: Ensure intermediate containers allow shrinking**
  - For any `pn.Column`/`pn.Row` that contains editor/iframe, ensure:
    - `sizing_mode="stretch_both"`
    - styles include `min-height: 0` where necessary
    - avoid accidental fixed heights that prevent flex resizing

- [ ] **Step 2: Make left pane scroll correctly**
  - Ensure the left pane tab contents scroll vertically without horizontal overflow.
  - If needed, adjust sidebar widgets to use `sizing_mode="stretch_width"` rather than fixed widths.

- [ ] **Step 3: Manual verification**
  - Switch tabs in left pane; editor and preview remain stable and sized.

## Task 5: Regression checklist (must-pass)

- [ ] **Step 1: File switching**
  - Click editable file A, edit, click file B
  - Expected: file A is saved to disk; editor shows file B

- [ ] **Step 2: Insert Figure**
  - Go to Insert Figure tab, pick .foam, click insert
  - Expected: shortcode appended to current editor buffer

- [ ] **Step 3: Preview rebuild/export**
  - Click HTML rebuild
  - Expected: build overlay shows progress, iframe updates on success
  - Click PDF export
  - Expected: PDF link appears if export succeeds

- [ ] **Step 4: Camera overlay**
  - In preview, trigger the camera overlay workflow
  - Expected: postMessage handling still works; `/camera/<id>` receives updates; ack is forwarded

## Commands (how to run)

- Run app (as in `dashboard/app.py` docstring):

```bash
panel serve dashboard/app.py --plugins dashboard.plugins \
  --static-dirs output=_output assets=dashboard/static state=state \
  --show --port 5006
```

---

## Plan Review Loop

After writing this plan, dispatch a plan-document-reviewer subagent with:
- Plan: `docs/superpowers/plans/2026-03-25-panel-ide-3pane-layout.md`
- Spec: `docs/superpowers/specs/2026-03-25-panel-ide-3pane-layout-design.md`

