# Vector PDF Export + Paper-View Auto-Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace rasterized PNG figures in PDF export with vector PDF, unify HTML/PNG aspect ratios, and add a dashboard Paper View tab that auto-rebuilds a static paper-like HTML every 30 s.

**Architecture:** PyVista's `save_graphic` already generates per-figure `.pdf` files alongside every `.png`; Lua shortcodes are updated to embed these for PDF output and emit LaTeX minipage grids for panels. A new `--profile paperview` Quarto build (triggered from the dashboard's new Paper View tab) uses `FOURD_PAPER_VIEW=1` to swap iframes for `<img>` tags, giving a fast static preview. The dashboard rebuilds this profile every 30 s while the tab is active.

**Tech Stack:** Python 3, PyVista, Quarto, Lua (Pandoc filter), Panel (Bokeh/Tornado), pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `_extensions/4dpaper/4dpaper.py` | Modify | Fix `window_size` to `(900,600)` in `generate_png_figure` and video frame render |
| `_quarto-paperview.yml` | Create | Quarto profile: paper-like HTML, no iframes, fast build |
| `_extensions/4dpaper/paperview.css` | Create | Single-column print-like CSS for paper-view |
| `dashboard/utils.py` | Modify | Add `paperview` output_format branch to `run_quarto_render` |
| `_extensions/4dpaper/shortcodes.lua` | Modify | (1) `FOURD_PAPER_VIEW` mode: embed `<img>` instead of iframe; (2) PDF: embed `.pdf` for individual figs; (3) PDF: LaTeX minipage grid for panels/timeseries |
| `dashboard/pages/paper_page.py` | Modify | Add Paper View tab with `pn.Tabs`, periodic callback, `_paper_view_building` guard |
| `tests/test_extension.py` | Modify | Add `window_size` assertion for PNG figure generation |
| `tests/test_utils.py` | Modify | Add paperview branch test for `run_quarto_render` |
| `tests/test_pages.py` | Modify | Add Paper View tab smoke test |

---

## Task 1: Fix window_size in generate_png_figure and video frame

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py:1161` (PNG figure plotter)
- Modify: `_extensions/4dpaper/4dpaper.py:1945` (video frame plotter)
- Test: `tests/test_extension.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_extension.py`. This test patches `pyvista.Plotter` and checks the `window_size` argument:

```python
class TestGeneratePngWindowSize:
    """Verify generate_png_figure uses 900x600 (matching HTML aspect ratio)."""

    def test_png_figure_uses_900x600(self, tmp_path, monkeypatch):
        import importlib.util, sys
        from pathlib import Path
        from unittest.mock import MagicMock, patch, call

        # Load 4dpaper module
        spec = importlib.util.spec_from_file_location(
            "fourDpaper_ws",
            Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
        )
        mod = importlib.util.module_from_spec(spec)

        # Stub pyvista before module executes
        fake_pv = MagicMock()
        fake_pl = MagicMock()
        fake_pl.screenshot.return_value = None
        fake_pv.Plotter.return_value = fake_pl
        sys.modules["pyvista"] = fake_pv

        # Stub SimulationData
        fake_sim = MagicMock()
        fake_sim.n_steps = 3
        fake_mesh = MagicMock()
        fake_surface = MagicMock()
        fake_surface.point_data.__contains__ = lambda self, k: True
        fake_surface.point_data.__getitem__ = lambda self, k: MagicMock()
        fake_surface.cell_data.__contains__ = lambda self, k: False
        fake_mesh.extract_surface.return_value = fake_surface
        fake_sim.get_mesh.return_value = fake_mesh
        fake_SimData = MagicMock(return_value=MagicMock(load=MagicMock(return_value=fake_sim)))

        spec.loader.exec_module(mod)
        out_png = tmp_path / "fig.png"

        with patch.object(mod, "SimulationData" if hasattr(mod, "SimulationData") else "_SimData", fake_SimData, create=True):
            with patch("scripts.data_loader.SimulationData", fake_SimData):
                try:
                    mod.generate_png_figure(
                        src_path=Path("/fake/case.foam"),
                        field="Vm",
                        time_spec="mid",
                        output_path=out_png,
                        fig_id="fig-test",
                    )
                except Exception:
                    pass  # We only care about the Plotter call

        fake_pv.Plotter.assert_called_once()
        _, kwargs = fake_pv.Plotter.call_args
        assert kwargs.get("window_size") == (900, 600), (
            f"Expected (900, 600) but got {kwargs.get('window_size')}"
        )
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /Users/simaocastro/4Dpapers && .venv/bin/pytest tests/test_extension.py::TestGeneratePngWindowSize -v
```

Expected: FAIL — `AssertionError: Expected (900, 600) but got (1920, 1080)`

- [ ] **Step 3: Fix generate_png_figure window_size**

In `_extensions/4dpaper/4dpaper.py` line 1161:

```python
# Before:
pl = pv.Plotter(off_screen=True, window_size=(1920, 1080))

# After:
pl = pv.Plotter(off_screen=True, window_size=(900, 600))
```

- [ ] **Step 4: Fix video frame window_size**

In `_extensions/4dpaper/4dpaper.py` line 1945:

```python
# Before:
pl = pv.Plotter(off_screen=True, window_size=(1920, 1080))

# After:
pl = pv.Plotter(off_screen=True, window_size=(900, 600))
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /Users/simaocastro/4Dpapers && .venv/bin/pytest tests/test_extension.py::TestGeneratePngWindowSize -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_extension.py
git commit -m "fix: unify PNG/HTML aspect ratio — generate_png_figure uses 900x600 window"
```

---

## Task 2: Create Quarto paperview profile and CSS

**Files:**
- Create: `_quarto-paperview.yml`
- Create: `_extensions/4dpaper/paperview.css`

No Python tests — verified by the dashboard auto-build in Task 6.

- [ ] **Step 1: Create `_quarto-paperview.yml`**

```yaml
format:
  html:
    theme: default
    toc: false
    embed-resources: false
    css: _extensions/4dpaper/paperview.css
    output-file: analysis_report-paperview.html
```

- [ ] **Step 2: Create `_extensions/4dpaper/paperview.css`**

```css
body {
  max-width: 700px;
  margin: 2rem auto;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 11pt;
  line-height: 1.6;
  color: #111;
}
h1, h2, h3, h4 {
  font-family: system-ui, Arial, sans-serif;
}
figure {
  margin: 1.5rem 0;
  text-align: center;
}
figure img {
  width: 100%;
  display: block;
}
figcaption {
  font-style: italic;
  font-size: 0.9em;
  margin-top: 0.4rem;
  color: #444;
}
```

- [ ] **Step 3: Commit**

```bash
git add _quarto-paperview.yml _extensions/4dpaper/paperview.css
git commit -m "feat: add paperview Quarto profile and print CSS"
```

---

## Task 3: Add paperview branch to run_quarto_render

**Files:**
- Modify: `dashboard/utils.py`
- Test: `tests/test_utils.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_utils.py`:

```python
class TestRunQuartoRenderPaperview:
    def test_paperview_sets_env_vars_and_profile(self, tmp_path):
        import subprocess
        from unittest.mock import patch, MagicMock
        from dashboard.utils import run_quarto_render

        qmd = tmp_path / "paper.qmd"
        qmd.write_text("# Test\n")

        captured = {}

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env", {})
            proc = MagicMock()
            proc.stdout.__iter__ = lambda s: iter([])
            proc.wait.return_value = None
            proc.returncode = 0
            return proc

        with patch("subprocess.Popen", fake_popen):
            run_quarto_render(qmd, [], output_format="paperview")

        assert "--profile" in captured["cmd"]
        profile_idx = captured["cmd"].index("--profile")
        assert captured["cmd"][profile_idx + 1] == "paperview"
        assert captured["env"].get("FOURD_PAPER_VIEW") == "1"
        assert captured["env"].get("FOURD_APP_MODE") == "1"
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /Users/simaocastro/4Dpapers && .venv/bin/pytest tests/test_utils.py::TestRunQuartoRenderPaperview -v
```

Expected: FAIL — `KeyError` or assertion error on missing env vars

- [ ] **Step 3: Add paperview branch to run_quarto_render**

In `dashboard/utils.py`, update `run_quarto_render`:

```python
def run_quarto_render(qmd_path: Path, log_lines: list[str], output_format: str = "html") -> int:
    import os
    import subprocess
    import threading

    env = os.environ.copy()
    _venv_bin = Path(__file__).parent.parent / ".venv" / "bin"
    _venv_python = _venv_bin / "python"
    env["QUARTO_PYTHON"] = str(_venv_python) if _venv_python.exists() else sys.executable
    env["PATH"] = str(_venv_bin) + ":" + env.get("PATH", "")

    cmd = ["quarto", "render", str(qmd_path), "--to", "html"]
    if output_format == "html":
        env["FOURD_APP_MODE"] = "1"
        cmd += ["--profile", "apphtml"]
    elif output_format == "paperview":
        env["FOURD_APP_MODE"] = "1"
        env["FOURD_PAPER_VIEW"] = "1"
        cmd += ["--profile", "paperview"]
    else:
        # pdf or any other format — pass --to directly
        cmd = ["quarto", "render", str(qmd_path), "--to", output_format]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(qmd_path.parent),
        env=env,
    )

    def _read():
        for line in proc.stdout:
            log_lines.append(line.rstrip("\n"))

    thread = threading.Thread(target=_read, daemon=True)
    thread.start()
    proc.wait()
    thread.join()
    return proc.returncode
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/simaocastro/4Dpapers && .venv/bin/pytest tests/test_utils.py::TestRunQuartoRenderPaperview -v
```

Expected: PASS

- [ ] **Step 5: Run full utils test suite**

```bash
cd /Users/simaocastro/4Dpapers && .venv/bin/pytest tests/test_utils.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add dashboard/utils.py tests/test_utils.py
git commit -m "feat: add paperview branch to run_quarto_render"
```

---

## Task 4: Lua — FOURD_PAPER_VIEW mode (static img for all shortcodes)

**Files:**
- Modify: `_extensions/4dpaper/shortcodes.lua`

Lua cannot be unit-tested in Python. Verification is done by running a paperview build and checking the output HTML contains `<img>` tags instead of `<iframe>` tags. This is checked after Task 6 (dashboard integration).

- [ ] **Step 1: Add `_paper_view` flag at the top of shortcodes.lua**

After the existing `local _app_mode = ...` line (line ~18), add:

```lua
-- Paper-view mode: embed static PNG <img> instead of interactive iframes.
-- Set by dashboard when building the paper-view profile.
local _paper_view = os.getenv("FOURD_PAPER_VIEW") == "1"
```

- [ ] **Step 2: Add paper-view branch to fourd_image HTML section**

In `fourd_image`, inside `if quarto.doc.isFormat("html") then`, before the existing `local fig_path = ...` line (around line 194), insert:

```lua
    -- Paper-view: embed static PNG instead of interactive iframe
    if _paper_view then
      local png_path = "state/figures/" .. id .. ".png"
      local pf = io.open(png_path, "r")
      if pf then pf:close() end
      local cap_html = caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' ..
        caption .. '</figcaption>\n' or ""
      if not pf then
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;">' ..
          '<div style="border:2px dashed #888;padding:1rem;text-align:center;">' ..
          '⚠ Figure <code>' .. id .. '</code> not rendered — click Rebuild HTML</div>' ..
          cap_html .. '</figure>')
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        '<img src="/state/figures/' .. id .. '.png" style="width:100%;display:block;">\n' ..
        cap_html .. '</figure>')
    end
```

- [ ] **Step 3: Add paper-view branch to fourd_video HTML section**

In `fourd_video`, inside `if quarto.doc.isFormat("html") then`, before the existing iframe/body logic, insert:

```lua
    if _paper_view then
      local frame_path = "state/figures/" .. id .. "-frame.png"
      local pf = io.open(frame_path, "r")
      if pf then pf:close() end
      local cap_html = caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' ..
        caption .. '</figcaption>\n' or ""
      if not pf then
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;">' ..
          '<div style="border:2px dashed #888;padding:1rem;text-align:center;">' ..
          '⚠ Video frame <code>' .. id .. '</code> not rendered</div>' ..
          cap_html .. '</figure>')
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        '<img src="/state/figures/' .. id .. '-frame.png" style="width:100%;display:block;">\n' ..
        cap_html .. '</figure>')
    end
```

- [ ] **Step 4: Add paper-view branch to fourd_panel HTML section**

In `fourd_panel`, inside `if quarto.doc.isFormat("html") then`, before the manifest reading logic, insert:

```lua
    if _paper_view then
      local png_path = "state/figures/" .. id .. ".png"
      local pf = io.open(png_path, "r")
      if pf then pf:close() end
      local cap_html = caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' ..
        caption .. '</figcaption>\n' or ""
      if not pf then
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;">' ..
          '<div style="border:2px dashed #888;padding:1rem;text-align:center;">' ..
          '⚠ Panel <code>' .. id .. '</code> not rendered</div>' ..
          cap_html .. '</figure>')
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        '<img src="/state/figures/' .. id .. '.png" style="width:100%;display:block;">\n' ..
        cap_html .. '</figure>')
    end
```

- [ ] **Step 5: Add paper-view branch to fourd_pvsm HTML section**

In `fourd_pvsm`, inside `if quarto.doc.isFormat("html") then`, after the `not exists` early return block, insert:

```lua
    if _paper_view then
      local png_path = "state/figures/" .. id .. ".png"
      local pf = io.open(png_path, "r")
      if pf then pf:close() end
      local cap_html = caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' ..
        caption .. '</figcaption>\n' or ""
      if not pf then
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;">' ..
          '<div style="border:2px dashed #888;padding:1rem;text-align:center;">' ..
          '⚠ PVSM figure <code>' .. id .. '</code> not rendered</div>' ..
          cap_html .. '</figure>')
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        '<img src="/state/figures/' .. id .. '.png" style="width:100%;display:block;">\n' ..
        cap_html .. '</figure>')
    end
```

- [ ] **Step 6: Add paper-view branch to fourd_timeseries HTML section**

In `fourd_timeseries`, inside `if quarto.doc.isFormat("html") then`, before the manifest reading logic, insert:

```lua
    if _paper_view then
      local png_path = "state/figures/" .. id .. ".png"
      local pf = io.open(png_path, "r")
      if pf then pf:close() end
      local cap_html = caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' ..
        caption .. '</figcaption>\n' or ""
      if not pf then
        return pandoc.RawBlock("html",
          '<figure class="fourd-figure" style="margin:1.5rem 0;">' ..
          '<div style="border:2px dashed #888;padding:1rem;text-align:center;">' ..
          '⚠ Timeseries <code>' .. id .. '</code> not rendered</div>' ..
          cap_html .. '</figure>')
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        '<img src="/state/figures/' .. id .. '.png" style="width:100%;display:block;">\n' ..
        cap_html .. '</figure>')
    end
```

- [ ] **Step 7: Commit**

```bash
git add _extensions/4dpaper/shortcodes.lua
git commit -m "feat: Lua FOURD_PAPER_VIEW mode — embed static PNG img instead of iframe"
```

---

## Task 5: Lua — individual figures embed .pdf for PDF output

**Files:**
- Modify: `_extensions/4dpaper/shortcodes.lua`

- [ ] **Step 1: Update fourd_image PDF branch**

Replace the `else` block in `fourd_image` (lines ~239–253, the PNG embed):

```lua
  -- ── PDF / LaTeX output: embed vector .pdf if available, else .png ─────────
  else
    local pdf_path = "state/figures/" .. id .. ".pdf"
    local png_path = "state/figures/" .. id .. ".png"
    local pf = io.open(pdf_path, "r")
    local fig_path
    if pf then
      pf:close()
      fig_path = pdf_path
    else
      local f2 = io.open(png_path, "r")
      if f2 then f2:close(); fig_path = png_path end
    end
    if fig_path then
      local img = pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" }))
      return pandoc.Para({ img })
    else
      return pandoc.Para({
        pandoc.Str("[Figure "),
        pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
  end
```

- [ ] **Step 2: Update fourd_pvsm PDF branch**

Replace the `else` block in `fourd_pvsm` (lines ~626–641):

```lua
  -- PDF / LaTeX output: embed vector .pdf if available, else .png
  else
    local pdf_path = "state/figures/" .. id .. ".pdf"
    local png_path = "state/figures/" .. id .. ".png"
    local pf = io.open(pdf_path, "r")
    local fig_path
    if pf then
      pf:close()
      fig_path = pdf_path
    else
      local f2 = io.open(png_path, "r")
      if f2 then f2:close(); fig_path = png_path end
    end
    if fig_path then
      local img = pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" }))
      return pandoc.Para({ img })
    else
      return pandoc.Para({
        pandoc.Str("[PVSM figure "),
        pandoc.Code(id),
        pandoc.Str(" - run 'Rebuild HTML' from the dashboard to generate this figure]"),
      })
    end
  end
```

Note: `fourd_video` PDF branch keeps `.png` — video frames are rasters only, no `save_graphic` call exists for them.

- [ ] **Step 3: Commit**

```bash
git add _extensions/4dpaper/shortcodes.lua
git commit -m "feat: Lua PDF output — embed vector .pdf for individual figures (fallback to .png)"
```

---

## Task 6: Lua — panels and timeseries emit LaTeX minipage grid for PDF

**Files:**
- Modify: `_extensions/4dpaper/shortcodes.lua`

- [ ] **Step 1: Replace fourd_panel PDF branch with LaTeX minipage grid**

Replace the `else` block in `fourd_panel` (lines ~530–545):

```lua
  -- ── PDF / LaTeX output: LaTeX minipage grid from manifest ─────────────────
  else
    local manifest_path = "state/figures/" .. id .. ".manifest.json"
    local mf = io.open(manifest_path, "r")
    if not mf then
      -- Fallback to composite PNG if manifest missing
      local fig_path = "state/figures/" .. id .. ".png"
      local f2 = io.open(fig_path, "r")
      if f2 then
        f2:close()
        return pandoc.Para({ pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" })) })
      end
      return pandoc.Para({
        pandoc.Str("[Panel "), pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
    local manifest_str = mf:read("*all"); mf:close()

    -- Parse subfigure IDs: ["id1","id2",...]
    local subfig_ids = {}
    for s in manifest_str:gmatch('"subfigures"%s*:%s*%[([^%]]*)%]') do
      for sub_id in s:gmatch('"([^"]+)"') do
        table.insert(subfig_ids, sub_id)
      end
    end
    -- Parse column count from layout: "2x1" → ncols=2
    local ncols_str = manifest_str:match('"layout"%s*:%s*"(%d+)x%d+"') or "1"
    local ncols = math.max(1, tonumber(ncols_str) or 1)
    local mp_width = string.format("%.3f", 0.98 / ncols)

    if #subfig_ids == 0 then
      return pandoc.Para({
        pandoc.Str("[Panel "), pandoc.Code(id),
        pandoc.Str(" — manifest empty, run 'Export PDF']"),
      })
    end

    local lines = { "\\begin{figure}[h]\n\\centering\n" }
    for i, sub_id in ipairs(subfig_ids) do
      local pdf_path = "state/figures/" .. sub_id .. ".pdf"
      local png_path = "state/figures/" .. sub_id .. ".png"
      local pf = io.open(pdf_path, "r")
      local fig_src
      if pf then pf:close(); fig_src = pdf_path else fig_src = png_path end
      table.insert(lines, "\\begin{minipage}{" .. mp_width .. "\\textwidth}\n")
      table.insert(lines, "  \\centering\n")
      table.insert(lines, "  \\includegraphics[width=\\linewidth]{" .. fig_src .. "}\n")
      table.insert(lines, "\\end{minipage}")
      local col_pos = (i - 1) % ncols + 1
      local is_last_in_row = col_pos == ncols
      local is_last = i == #subfig_ids
      if not is_last then
        if is_last_in_row then
          table.insert(lines, "\\\\\n")
        else
          table.insert(lines, "\\hfill\n")
        end
      end
    end
    if caption ~= "" then
      table.insert(lines, "\n\\caption{" .. caption .. "}\n")
    end
    table.insert(lines, "\\end{figure}\n")
    return pandoc.RawBlock("latex", table.concat(lines))
  end
```

- [ ] **Step 2: Replace fourd_timeseries PDF branch with LaTeX minipage grid**

Replace the `else` block in `fourd_timeseries` (lines ~763–777):

```lua
  else
    -- PDF: LaTeX minipage grid — timeseries is always Nx1, read manifest for IDs
    local manifest_path = "state/figures/" .. id .. ".manifest.json"
    local mf = io.open(manifest_path, "r")
    if not mf then
      -- Fallback to composite PNG
      local fig_path = "state/figures/" .. id .. ".png"
      local f2 = io.open(fig_path, "r")
      if f2 then
        f2:close()
        return pandoc.Para({ pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" })) })
      end
      return pandoc.Para({
        pandoc.Str("[Timeseries "), pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
    local manifest_str = mf:read("*all"); mf:close()

    local subfig_ids = {}
    for s in manifest_str:gmatch('"subfigures"%s*:%s*%[([^%]]*)%]') do
      for sub_id in s:gmatch('"([^"]+)"') do
        table.insert(subfig_ids, sub_id)
      end
    end
    local ncols = math.max(1, #subfig_ids)
    local mp_width = string.format("%.3f", 0.98 / ncols)

    if #subfig_ids == 0 then
      return pandoc.Para({
        pandoc.Str("[Timeseries "), pandoc.Code(id),
        pandoc.Str(" — manifest empty, run 'Export PDF']"),
      })
    end

    local lines = { "\\begin{figure}[h]\n\\centering\n" }
    for i, sub_id in ipairs(subfig_ids) do
      local pdf_path = "state/figures/" .. sub_id .. ".pdf"
      local png_path = "state/figures/" .. sub_id .. ".png"
      local pf = io.open(pdf_path, "r")
      local fig_src
      if pf then pf:close(); fig_src = pdf_path else fig_src = png_path end
      table.insert(lines, "\\begin{minipage}{" .. mp_width .. "\\textwidth}\n")
      table.insert(lines, "  \\centering\n")
      table.insert(lines, "  \\includegraphics[width=\\linewidth]{" .. fig_src .. "}\n")
      table.insert(lines, "\\end{minipage}")
      if i < #subfig_ids then
        table.insert(lines, "\\hfill\n")
      end
    end
    if caption ~= "" then
      table.insert(lines, "\n\\caption{" .. caption .. "}\n")
    end
    table.insert(lines, "\\end{figure}\n")
    return pandoc.RawBlock("latex", table.concat(lines))
  end
```

- [ ] **Step 3: Commit**

```bash
git add _extensions/4dpaper/shortcodes.lua
git commit -m "feat: Lua PDF panels/timeseries — LaTeX minipage grid with vector subfigure PDFs"
```

---

## Task 7: Dashboard Paper View tab with auto-rebuild

**Files:**
- Modify: `dashboard/pages/paper_page.py`
- Test: `tests/test_pages.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pages.py`:

```python
def test_paper_page_has_paper_view_tab():
    """Paper View tab must exist in the page layout."""
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        from importlib import reload
        import dashboard.pages.paper_page as pp_mod
        reload(pp_mod)
        layout, page = pp_mod.build_paper_page(config=FAKE_CONFIG)
    # layout should contain a Tabs widget
    import panel as pn
    def _find_tabs(obj):
        if isinstance(obj, pn.Tabs):
            return obj
        children = getattr(obj, "objects", None) or []
        for child in children:
            result = _find_tabs(child)
            if result is not None:
                return result
        return None
    tabs = _find_tabs(layout)
    assert tabs is not None, "Expected a pn.Tabs widget in the paper page layout"
    tab_names = [t[0] if isinstance(t, tuple) else getattr(t, "name", "") for t in tabs.objects]
    assert any("Paper" in str(n) for n in tab_names), f"Expected a 'Paper View' tab, got: {tab_names}"


def test_paper_page_periodic_callback_starts_on_tab_open():
    """_enable_paper_view must set _paper_view_enabled=True."""
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        from importlib import reload
        import dashboard.pages.paper_page as pp_mod
        reload(pp_mod)
        _, page = pp_mod.build_paper_page(config=FAKE_CONFIG)
    assert not page._paper_view_enabled
    page._enable_paper_view()
    assert page._paper_view_enabled
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /Users/simaocastro/4Dpapers && .venv/bin/pytest tests/test_pages.py -v
```

Expected: FAIL — `AssertionError: Expected a pn.Tabs widget` and `AttributeError: _paper_view_enabled`

- [ ] **Step 3: Rewrite dashboard/pages/paper_page.py**

Replace the full file with:

```python
"""Paper tab: iframe preview + Rebuild HTML + Export PDF + Paper View auto-rebuild."""
from __future__ import annotations

import html as html_mod
import threading
import time
from pathlib import Path
from typing import Any

import panel as pn
import param

from dashboard.theme import THEME
from dashboard.utils import run_quarto_render


class PaperPage(param.Parameterized):
    is_building = param.Boolean(default=False)

    def __init__(self, config: dict[str, Any], **params):
        super().__init__(**params)
        self._config = config
        self._qmd_path = Path(config["quarto_paper_path"])
        self._log_lines: list[str] = []
        self._log_cb = None
        self._hide_timer: threading.Timer | None = None
        self._status_text = ""
        self._status_type = "info"
        self._build_start: float | None = None

        # Paper-view state
        self._paper_view_enabled = False
        self._paper_view_building = False
        self._paper_view_cb = None

        self._rebuild_html_btn = pn.widgets.Button(
            name="HTML",
            icon="file-type-html",
            icon_size="1em",
            button_type="primary",
            width=88,
            height=26,
            margin=(0, 2),
            styles={"font-size": "11px"},
            css_classes=["dash-btn-build-primary"],
        )
        self._export_pdf_btn = pn.widgets.Button(
            name="PDF",
            icon="file-type-pdf",
            icon_size="1em",
            button_type="default",
            width=84,
            height=26,
            margin=(0, 2),
            styles={"font-size": "11px"},
            css_classes=["dash-btn-build-secondary"],
        )

        self._overlay = pn.pane.HTML(
            "",
            sizing_mode="stretch_width",
            visible=False,
            styles={
                "position": "absolute",
                "top": "8px",
                "left": "8px",
                "right": "8px",
                "z-index": "100",
            },
        )

        self._iframe = pn.pane.HTML(
            f'<div style="border:1px dashed {THEME["border_subtle"]};padding:2.5rem 1.5rem;'
            f'text-align:center;color:{THEME["text_muted"]};border-radius:6px;'
            f'background:{THEME["bg_panel"]};font-size:13px;line-height:1.5;">'
            f'<strong style="color:{THEME["text_primary"]};">HTML preview</strong><br><br>'
            f'Run <strong>HTML</strong> to render the paper here.</div>',
            sizing_mode="stretch_both",
        )

        self._paper_view_iframe = pn.pane.HTML(
            f'<div style="border:1px dashed {THEME["border_subtle"]};padding:2.5rem 1.5rem;'
            f'text-align:center;color:{THEME["text_muted"]};border-radius:6px;'
            f'background:{THEME["bg_panel"]};font-size:13px;line-height:1.5;">'
            f'<strong style="color:{THEME["text_primary"]};">Paper View</strong><br><br>'
            f'Opens this tab to start auto-rebuilding every 30 s.</div>',
            sizing_mode="stretch_both",
        )

        self._pdf_link = pn.pane.HTML("", sizing_mode="stretch_width", margin=(2, 4))
        self._set_pdf_link_if_exists()

        self._rebuild_html_btn.on_click(self._on_rebuild_html)
        self._export_pdf_btn.on_click(self._on_export_pdf)

    # ── Paper-view auto-rebuild ───────────────────────────────────────────────

    def _enable_paper_view(self) -> None:
        """Called once when the user first opens the Paper View tab."""
        if self._paper_view_enabled:
            return
        self._paper_view_enabled = True
        # Start 30-second periodic rebuild
        self._paper_view_cb = pn.state.add_periodic_callback(
            self._tick_paper_view,
            period=30_000,
        )
        # Trigger an immediate first build
        self._tick_paper_view()

    def _tick_paper_view(self) -> None:
        if self._paper_view_building or self.is_building:
            return
        self._paper_view_building = True
        threading.Thread(target=self._run_paper_view_build, daemon=True).start()

    def _run_paper_view_build(self) -> None:
        log: list[str] = []
        try:
            exit_code = run_quarto_render(self._qmd_path, log, output_format="paperview")
        except Exception as exc:
            exit_code = 1
            log.append(f"[ERROR] {exc}")
        finally:
            self._paper_view_building = False

        if exit_code == 0:
            ts = int(time.time())
            doc = pn.state.curdoc
            if doc is not None:
                doc.add_next_tick_callback(lambda: self._refresh_paper_view(ts))

    def _refresh_paper_view(self, ts: int) -> None:
        self._paper_view_iframe.object = (
            f'<iframe src="/output/analysis_report-paperview.html?t={ts}" '
            f'width="100%" frameborder="0" '
            f'style="border:none;border-radius:4px;width:100%;height:100%;'
            f'display:block;background:{THEME["bg_app"]};"></iframe>'
        )

    # ── Existing HTML / PDF build logic (unchanged) ───────────────────────────

    def _set_pdf_link_if_exists(self) -> None:
        pdf_path = self._qmd_path.parent / "_output" / "analysis_report.pdf"
        if pdf_path.exists():
            ts = int(time.time())
            self._pdf_link.object = (
                f'<a href="/output/analysis_report.pdf?t={ts}" target="_blank" '
                f'style="background:{THEME["accent"]};color:#fff;padding:5px 10px;'
                f'border-radius:4px;text-decoration:none;font-size:11px;'
                f'font-weight:600;font-family:system-ui,sans-serif;display:inline-flex;'
                f'align-items:center;gap:5px;margin:0 4px;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.25);">PDF</a>'
            )

    def _update_overlay(self, status_text: str, status_type: str = "info", show_log: bool = True) -> None:
        self._status_text = status_text
        self._status_type = status_type
        colors = {
            "info": THEME["info"],
            "warning": THEME["warning"],
            "success": THEME["success"],
            "danger": THEME["danger"],
        }
        color = colors.get(status_type, THEME["info"])
        elapsed_html = ""
        if self._build_start is not None and self.is_building:
            elapsed = int(time.time() - self._build_start)
            elapsed_html = (
                f'<div style="color:{THEME["text_muted"]};font-size:11px;margin-bottom:4px;">'
                f"{elapsed}s elapsed</div>"
            )
        log_html = ""
        if show_log and self._log_lines:
            escaped = "<br>".join(html_mod.escape(line) for line in self._log_lines[-30:])
            log_html = (
                f'<div style="margin-top:8px;font-size:11px;opacity:0.85;'
                f'max-height:180px;overflow-y:auto;">{escaped}</div>'
            )
        self._overlay.object = (
            f'<div style="background:rgba(24,22,20,0.94);color:{THEME["text_primary"]};'
            f'padding:12px 16px;border-radius:6px;font-family:monospace;'
            f'font-size:12px;box-shadow:0 4px 12px rgba(0,0,0,0.45);">'
            f'<div style="color:{color};font-weight:bold;margin-bottom:4px;">'
            f'{html_mod.escape(status_text)}</div>{elapsed_html}{log_html}</div>'
        )
        self._overlay.visible = True

    def _hide_overlay(self) -> None:
        self._overlay.visible = False
        self._hide_timer = None

    def _schedule_hide_overlay(self, doc, delay_s: float = 4.0) -> None:
        if self._hide_timer is not None:
            self._hide_timer.cancel()
        def _trigger():
            try:
                doc.add_next_tick_callback(self._hide_overlay)
            except Exception:
                pass
        self._hide_timer = threading.Timer(delay_s, _trigger)
        self._hide_timer.daemon = True
        self._hide_timer.start()

    def _on_rebuild_html(self, event) -> None:
        if self.is_building:
            return
        self.is_building = True
        self._rebuild_html_btn.disabled = True
        self._export_pdf_btn.disabled = True
        self._log_lines.clear()
        self._pdf_link.object = ""
        self._build_start = time.time()
        self._update_overlay("Building HTML paper...", "warning")
        doc = pn.state.curdoc

        def _run() -> None:
            try:
                self._log_lines.append("[INFO] Running quarto render --to html...")
                code = run_quarto_render(self._qmd_path, self._log_lines)
                doc.add_next_tick_callback(lambda: self._finish_html(code, doc))
            except Exception as exc:
                self._log_lines.append(f"[ERROR] {exc}")
                doc.add_next_tick_callback(lambda: self._finish_html(1, doc))

        threading.Thread(target=_run, daemon=True).start()
        if self._log_cb is not None:
            self._log_cb.stop()
            self._log_cb = None
        self._log_cb = pn.state.add_periodic_callback(self._refresh_log, period=500, count=600)

    def _finish_html(self, exit_code: int, doc) -> None:
        if self._log_cb is not None:
            self._log_cb.stop()
            self._log_cb = None
        self.is_building = False
        self._rebuild_html_btn.disabled = False
        self._export_pdf_btn.disabled = False
        if exit_code == 0:
            elapsed = f" ({int(time.time() - self._build_start)}s)" if self._build_start else ""
            self._build_start = None
            self._update_overlay(f"HTML paper built successfully!{elapsed}", "success", show_log=False)
            self._schedule_hide_overlay(doc, delay_s=4.0)
            ts = int(time.time())
            self._iframe.object = (
                f'<iframe src="/output/analysis_report.html?t={ts}" '
                f'width="100%" frameborder="0" '
                f'style="border:none;border-radius:4px;width:100%;height:100%;'
                f'display:block;background:{THEME["bg_app"]};"></iframe>'
            )
        else:
            self._build_start = None
            self._update_overlay(f"Build failed (exit code {exit_code}). See log.", "danger")

    def _on_export_pdf(self, event) -> None:
        if self.is_building:
            return
        self.is_building = True
        self._rebuild_html_btn.disabled = True
        self._export_pdf_btn.disabled = True
        self._log_lines.clear()
        self._pdf_link.object = ""
        self._build_start = time.time()
        self._update_overlay("Exporting PDF...", "warning")
        doc = pn.state.curdoc

        def _run() -> None:
            try:
                self._log_lines.append(
                    "[INFO] Running quarto render --to pdf...\n"
                    "[INFO] Using camera positions from current HTML preview. "
                    "Rotate figures in the HTML view to update the viewpoint before exporting."
                )
                exit_code = run_quarto_render(self._qmd_path, self._log_lines, output_format="pdf")
                pdf_path = self._qmd_path.parent / "_output" / "analysis_report.pdf"
                doc.add_next_tick_callback(lambda: self._finish_pdf(exit_code, pdf_path, doc))
            except Exception as exc:
                self._log_lines.append(f"[ERROR] {exc}")
                doc.add_next_tick_callback(lambda: self._finish_pdf(1, None, doc))

        threading.Thread(target=_run, daemon=True).start()
        if self._log_cb is not None:
            self._log_cb.stop()
            self._log_cb = None
        self._log_cb = pn.state.add_periodic_callback(self._refresh_log, period=500, count=600)

    def _finish_pdf(self, exit_code: int, pdf_path, doc) -> None:
        if self._log_cb is not None:
            self._log_cb.stop()
            self._log_cb = None
        self.is_building = False
        self._rebuild_html_btn.disabled = False
        self._export_pdf_btn.disabled = False
        if exit_code == 0 and pdf_path and Path(pdf_path).exists():
            elapsed = f" ({int(time.time() - self._build_start)}s)" if self._build_start else ""
            self._build_start = None
            self._update_overlay(f"PDF exported successfully!{elapsed}", "success", show_log=False)
            self._schedule_hide_overlay(doc, delay_s=4.0)
            cache_bust = int(time.time())
            self._pdf_link.object = (
                f'<a href="/output/analysis_report.pdf?t={cache_bust}" target="_blank" '
                f'style="background:{THEME["accent"]};color:#fff;padding:5px 10px;'
                f'border-radius:4px;text-decoration:none;font-size:11px;'
                f'font-weight:600;font-family:system-ui,sans-serif;display:inline-flex;'
                f'align-items:center;gap:5px;margin:0 4px;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.25);">PDF</a>'
            )
        else:
            self._build_start = None
            self._update_overlay(f"PDF export failed (exit code {exit_code}). See log.", "danger")

    def _refresh_log(self) -> None:
        if self.is_building:
            self._update_overlay(self._status_text, self._status_type)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def rebuild_btn(self) -> pn.widgets.Button:
        return self._rebuild_html_btn

    @property
    def export_btn(self) -> pn.widgets.Button:
        return self._export_pdf_btn

    @property
    def pdf_link(self) -> pn.pane.HTML:
        return self._pdf_link

    def layout(self) -> pn.Column:
        # Interactive HTML tab
        html_tab = pn.Column(
            pn.Column(
                self._overlay,
                self._iframe,
                sizing_mode="stretch_both",
                min_height=0,
                styles={"position": "relative", "flex": "1 1 auto"},
            ),
            sizing_mode="stretch_both",
            min_height=0,
        )

        # Paper View tab — enable auto-rebuild on first open
        paper_tab = pn.Column(
            self._paper_view_iframe,
            sizing_mode="stretch_both",
            min_height=0,
        )

        tabs = pn.Tabs(
            ("Interactive HTML", html_tab),
            ("Paper View", paper_tab),
            sizing_mode="stretch_both",
            min_height=0,
        )

        # Trigger paper-view rebuild when user switches to that tab (index 1)
        def _on_tab_change(event):
            if event.new == 1:
                self._enable_paper_view()

        tabs.param.watch(_on_tab_change, "active")

        return pn.Column(tabs, sizing_mode="stretch_both", min_height=0)


def build_paper_page(config: dict[str, Any]) -> tuple[pn.Column, PaperPage]:
    page = PaperPage(config=config)
    return page.layout(), page
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/simaocastro/4Dpapers && .venv/bin/pytest tests/test_pages.py -v
```

Expected: all PASS including the two new tests

- [ ] **Step 5: Run the full test suite**

```bash
cd /Users/simaocastro/4Dpapers && .venv/bin/pytest tests/ -v --ignore=tests/e2e
```

Expected: all PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add dashboard/pages/paper_page.py tests/test_pages.py
git commit -m "feat: dashboard Paper View tab with 30s auto-rebuild via paperview Quarto profile"
```

---

## Verification Checklist (manual, after all tasks complete)

- [ ] Run `quarto render analysis_report.qmd --to pdf` — check that figures in the generated PDF are crisp (vector) rather than pixelated. Open a generated `.pdf` file in `state/figures/` to confirm it exists and is non-empty.
- [ ] Open the dashboard, click "HTML" to rebuild. Open "Paper View" tab — it should trigger an immediate paperview build and show a static paper-like HTML with `<img>` figures (no iframes).
- [ ] Wait 30 s on the Paper View tab — the iframe should refresh with an updated build timestamp visible in the network tab.
- [ ] Confirm panel figures (`4d-panel`, `4d-timeseries`) in the PDF use minipage grids by inspecting the intermediate `.tex` file in `_output/` (add `keep-tex: true` to `_quarto.yml` temporarily).
- [ ] Confirm video frames in PDF are still `.png` (no `.pdf` file generated for video frames).
