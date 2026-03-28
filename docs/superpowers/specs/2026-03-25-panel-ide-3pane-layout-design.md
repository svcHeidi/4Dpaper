# Panel IDE 3‑Pane Layout (Design Spec)

Date: 2026-03-25  
Project: 4Dpapers dashboard (`dashboard/`)

## Goal

Upgrade the app’s UI/UX to a professional, IDE-like **3‑pane resizable layout** while **not breaking** existing backend logic and core behaviors (file save/load, Quarto build/export, figure insertion, camera sync).

User-selected direction: **Approach A (Panel-native shell)** — do **not** introduce React; implement the “IDE shell” within Panel/Bokeh using robust split sizing, borders, scroll behavior, and tabs.

## Current Architecture (Audited)

The “frontend” is a **Panel app**:

- **App entry**: `dashboard/app.py` builds a `pn.Column(toolbar, body)` where `body` is `pn.Row(sidebar, editor_panel, paper_panel)` with `css_classes=["body-row"]`.
- **Left pane**: `build_file_tree_sidebar(project_root, on_file_click)` renders a file tree. Clicking an editable file calls `on_file_click(file_path, language)`.
- **Editor**: `pn.widgets.CodeEditor` holds the current buffer. `_on_file_click` persists the old file to disk (`Path(current).write_text(editor.value)`) then loads the new file into the editor.
- **Preview**: `dashboard/pages/paper_page.py` (`PaperPage`) owns rebuild/export buttons and preview iframe HTML. Build status is rendered as an overlay in the preview container.
- **Insert Figure**: `dashboard/figure_browser.py` implements `build_figure_insert_form(editor, qmd_path, config)` using `pn.widgets.FileSelector` (default directory = `config["cardiacfoam_root"]`, fallback: home) and appends a shortcode to `editor.value`.
- **Resizing (today)**: `dashboard/static/split_pane.js` injects draggable overlays after DOM load; it searches for `.body-row` and sets pane widths by forcing CSS flex values.

### Critical data flow (must not break)

- **File navigation → editor**: file tree clicks call `_on_file_click`, which (a) saves current editor buffer to disk, (b) loads new file contents into the same `CodeEditor`, (c) updates `editor.language`.
- **Insert Figure → editor**: figure form appends shortcode to the same `CodeEditor` instance.
- **Build/export → preview**: `PaperPage` rebuild/export updates the preview iframe HTML and overlay state.
- **Camera overlay (JS)**: `dashboard/static/camera_overlay.js` listens for `postMessage` events and calls `/camera/<figId>`; this should remain functional after layout changes.

## Target UX (What “IDE-like” means here)

- **Three horizontal panes** with draggable resize handles:
  - **Left**: project navigation + insertion tools
  - **Center**: editor
  - **Right**: preview/build tools
- **Minimum widths** enforced (left pane never collapses to zero; a handle/sliver always remains).
- **Tabs inside panes** for clear information architecture:
  - Left: `Files` and `Insert Figure`
  - Center: `Editor` (placeholder for future “Search/Problems”)
  - Right: `Preview` and optional `Build Log` (can be added later; not required for first iteration)
- **Professional shell styling**:
  - consistent borders/dividers
  - scroll areas that don’t cause horizontal overflow
  - fixed top toolbar
  - dark theme consistent with current editor theme

## Proposed Layout Structure

### Component tree (conceptual)

- `create_app()` (still the entry point)
  - `toolbar` (existing row with buttons/toggles)
  - `body_shell`
    - `left_pane_tabs`
      - `FilesTab`: existing `build_file_tree_sidebar(...)` content
      - `InsertFigureTab`: existing `build_figure_insert_form(...)` content
    - `center_pane_tabs`
      - `EditorTab`: existing `CodeEditor` instance
    - `right_pane_tabs`
      - `PreviewTab`: existing `paper_content` (from `build_paper_page`)

### State ownership / “lifting”

No core logic is rewritten. Instead, we ensure the same stateful objects are **created once** and passed into the shell:

- Single `CodeEditor` instance shared by:
  - `_on_file_click` (load/save)
  - `build_figure_insert_form(editor, ...)` (insert shortcode)
- Single `PaperPage` instance (already returned by `build_paper_page`) used for:
  - toolbar buttons
  - preview pane content

### Resizing implementation (Panel-native)

Replace `split_pane.js` “overlay drags” with a Panel-native or supported splitter approach:

- **Preferred**: use a dedicated split layout component supported by Panel/Bokeh (or a small, well-scoped custom JS splitter) that:
  - sets widths by updating Bokeh model sizing rather than DOM-only hacks
  - persists sizes in browser localStorage (optional)
  - enforces min widths (e.g., left >= 240px, center >= 360px, right >= 360px)

The first iteration can keep the current DOM approach but should be rewritten to:
- rely on explicit markers (already present: `.body-row`, `.split-marker`) rather than “dimension fallback”
- enforce min widths and avoid resizing when a pane is invisible
- avoid any “deep piercing search” through shadow roots (use known CSS hooks only)

## Insert Figure UX Requirement

User requirement: left panel needs a control saying **Insert Figure**, and the insert figure should “open the local folders” similar to other apps.

Interpretation in Panel terms:

- Promote figure insertion into a **left-pane tab** labeled “Insert Figure”.
- Configure the file picker experience to be “local folder browsing” (in-app folder browser, not necessarily an OS-native dialog):
  - Add a root selector: **Project** (project root) vs **Cases** (`cardiacfoam_root`)
  - Changing default root from today’s `cardiacfoam_root` is an intentional UX change

This is a UX change only; the shortcode generation and insertion logic remains unchanged.

## Non-goals

- Porting the app to React, Next.js, Vite, or shadcn/ui
- Rewriting Quarto build/export logic
- Changing camera sync routes or postMessage protocol
- Major refactors of file tree or figure browser logic (only presentation/wrapping changes)

## Risks & Mitigations

- **Risk**: resizing implementation affects Bokeh layout calculations.
  - **Mitigation**: prefer Panel/Bokeh-native sizing updates; keep min widths; test with wide/narrow windows.
- **Risk**: tabs introduce scroll/height issues (editor or iframe not filling space).
  - **Mitigation**: ensure `sizing_mode="stretch_both"` and `min_height=0` where needed; verify iframe/editor fills available height.
- **Risk**: focus/keyboard shortcuts in `CodeEditor` break inside tabs.
  - **Mitigation**: verify editor is rendered/visible on initial load; ensure tabs don’t detach/recreate editor widget.

## Acceptance Criteria

- Three panes are resizable with visible handles and **min widths**.
- Left pane provides **Files** and **Insert Figure** as tabs (or equivalent).
- Switching files always writes the previous buffer to disk before loading the new file.
- Figure insertion appends into the same editor instance even if the “Insert Figure” tab is active (no widget recreation).
- Editor continues to:
  - save current buffer when switching files
  - load selected file content
  - accept figure insertion appended to buffer
- Preview continues to:
  - rebuild HTML and update iframe
  - export PDF
  - show build status (overlay can remain initially)
- Editor and preview iframe fill available height after pane resizing and after tab switches (no blank space / scroll-jank).
- No regressions in camera overlay messaging and `/camera/<id>` updates.

