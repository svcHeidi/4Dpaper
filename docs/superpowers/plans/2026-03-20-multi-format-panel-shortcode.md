# Multi-Format Compatibility + `4d-panel` Shortcode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify `{{< 4d-image >}}` works for all new 3D formats, then add a `{{< 4d-panel >}}` shortcode that composes multiple figures into a CSS grid layout (2×2, 3×1, etc.) with per-figure camera sync.

**Architecture:** Python pre-render hook generates a single composite HTML (CSS grid of vtk.js srcdoc iframes) and composite PNG (PIL grid); Lua embeds both exactly like `4d-image` — one file, one iframe. A bidirectional re-relay script in the composite HTML forwards camera messages up to `top` and acks back down to children so each sub-figure's camera badge works correctly.

**Tech Stack:** Python 3, PyVista/trame (existing), PIL/Pillow 12.1.1, Lua (Quarto shortcode handler), pytest.

---

## File Map

| File | Change |
|------|--------|
| `_extensions/4dpaper/4dpaper.py` | Add `parse_panel_shortcodes()`, `generate_panel_html()`, `generate_panel_png()`; wire into `__main__` |
| `_extensions/4dpaper/shortcodes.lua` | Add `fourd_panel` handler; register in return table |
| `analysis_report.qmd` | Task 1: temporarily add test shortcodes for format verification |
| `tests/test_extension.py` | Add `TestParsePanelShortcodes`, `TestGeneratePanelHtml`, `TestGeneratePanelPng` |

---

## Task 1: Format Compatibility Verification

**Files:**
- Modify: `analysis_report.qmd` (add test section, remove after verification)

This task has no new code. It confirms `generate_html_figure()` works for all formats added by the multi-format loader. The format loader changes are already in place — this is a render smoke test.

- [ ] **Step 1: Add a test section to `analysis_report.qmd`**

Append this section at the end of the file:

```markdown
## Format Compatibility Test

> Remove this section after verification.

{{< 4d-image src="tests/data/base.stl"             field=""      id="fig-test-stl"  caption="STL: base geometry" >}}
{{< 4d-image src="tests/data/airplane.ply"          field=""      id="fig-test-ply"  caption="PLY: airplane" >}}
{{< 4d-image src="tests/data/sphere.obj"            field=""      id="fig-test-obj"  caption="OBJ: sphere" >}}
{{< 4d-image src="tests/data/track0.vtp"            field=""      id="fig-test-vtp"  caption="VTP: track" >}}
{{< 4d-image src="tests/data/slab_cubic.msh"        field=""      id="fig-test-msh"  caption="MSH: slab" >}}
{{< 4d-image src="tests/data/fiber_directions.xdmf" field="fiber" id="fig-test-xdmf" caption="XDMF: fiber directions" >}}
```

- [ ] **Step 2: Run the render**

```bash
cd /path/to/4Dpapers
.venv/bin/quarto render analysis_report.qmd --to html
```

Expected: all six `fig-test-*.html` files appear in `state/figures/`. No `[4dpaper] ERROR` lines in output.

- [ ] **Step 3: Verify figures were generated**

```bash
ls state/figures/fig-test-*.html
```

Expected: six files — `fig-test-stl.html`, `fig-test-ply.html`, `fig-test-obj.html`, `fig-test-vtp.html`, `fig-test-msh.html`, `fig-test-xdmf.html`.

- [ ] **Step 4: Commit (keep the test section — it serves as a demo)**

```bash
git add analysis_report.qmd state/figures/fig-test-*.html state/figures/fig-test-*.png
git commit -m "test: verify 4d-image renders all new mesh formats (STL, PLY, OBJ, VTP, MSH, XDMF)"
```

---

## Task 2: `parse_panel_shortcodes()`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (~line 89, after `parse_shortcodes`)
- Test: `tests/test_extension.py` (add `TestParsePanelShortcodes` class)

This is a pure function — no PyVista, no disk I/O, no mocking needed.

- [ ] **Step 1: Write the failing tests**

Add this class to `tests/test_extension.py` after the existing `TestParseShortcodes` class:

```python
class TestParsePanelShortcodes:
    def test_finds_single_panel(self):
        mod = _load_4dpaper()
        text = (
            '{{< 4d-panel id="panel-1" layout="2x2" '
            'src1="a.foam" id1="fig-a" field1="Vm" '
            'src2="b.stl" id2="fig-b" field2="" >}}'
        )
        result = mod.parse_panel_shortcodes(text)
        assert len(result) == 1
        p = result[0]
        assert p["id"] == "panel-1"
        assert p["layout"] == "2x2"
        assert len(p["subfigures"]) == 2
        assert p["subfigures"][0] == {"src": "a.foam", "id": "fig-a", "field": "Vm", "time": "mid"}
        assert p["subfigures"][1] == {"src": "b.stl",  "id": "fig-b", "field": "",   "time": "mid"}

    def test_defaults_height_and_caption(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p" layout="1x1" src1="a.foam" id1="fig-a" field1="" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result[0]["height"] == "800px"
        assert result[0]["caption"] == ""

    def test_reads_custom_height_and_caption(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p" layout="1x1" height="600px" caption="My panel" src1="a.foam" id1="fig-a" field1="" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result[0]["height"] == "600px"
        assert result[0]["caption"] == "My panel"

    def test_reads_time_per_subfigure(self):
        mod = _load_4dpaper()
        text = (
            '{{< 4d-panel id="p" layout="1x2" '
            'src1="a.foam" id1="fig-a" field1="" time1="first" '
            'src2="b.foam" id2="fig-b" field2="" time2="last" >}}'
        )
        result = mod.parse_panel_shortcodes(text)
        subs = result[0]["subfigures"]
        assert subs[0]["time"] == "first"
        assert subs[1]["time"] == "last"

    def test_skips_panel_missing_id(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel layout="1x1" src1="a.foam" id1="fig-a" field1="" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result == []

    def test_skips_panel_with_no_subfigures(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p" layout="1x1" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result == []

    def test_ignores_panel_in_fenced_code_block(self):
        mod = _load_4dpaper()
        text = (
            "```\n"
            '{{< 4d-panel id="p" layout="1x1" src1="a.foam" id1="fig-a" field1="" >}}\n'
            "```\n"
            '{{< 4d-panel id="real" layout="1x1" src1="b.foam" id1="fig-b" field1="" >}}'
        )
        result = mod.parse_panel_shortcodes(text)
        assert len(result) == 1
        assert result[0]["id"] == "real"

    def test_finds_multiple_panels(self):
        mod = _load_4dpaper()
        text = (
            '{{< 4d-panel id="p1" layout="1x1" src1="a.foam" id1="fig-a" field1="" >}}\n'
            '{{< 4d-panel id="p2" layout="2x1" src1="b.stl" id1="fig-b" field1="" src2="c.stl" id2="fig-c" field2="" >}}'
        )
        result = mod.parse_panel_shortcodes(text)
        assert len(result) == 2
        assert result[0]["id"] == "p1"
        assert result[1]["id"] == "p2"
        assert len(result[1]["subfigures"]) == 2
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
.venv/bin/pytest tests/test_extension.py::TestParsePanelShortcodes -v
```

Expected: `AttributeError: module 'fourDpaper' has no attribute 'parse_panel_shortcodes'`

- [ ] **Step 3: Implement `parse_panel_shortcodes()` in `4dpaper.py`**

Insert after `parse_shortcodes()` (after line ~88):

```python
def parse_panel_shortcodes(text: str) -> list[dict]:
    """
    Parse {{< 4d-panel key="value" ... >}} shortcodes from QMD text.

    Layout convention: "COLSxROWS" — columns first, rows second.
    E.g. "2x2" = 2 columns 2 rows, "3x1" = 3 columns 1 row.

    Sub-figures are numbered from 1: src1/id1/field1/time1, src2/id2/...
    Parser reads until src<n> is absent for the next n.

    Returns list of panel dicts; panels missing 'id' or sub-figures are skipped.
    """
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-panel\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)=["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs:
            print("[4dpaper] Warning: 4d-panel shortcode missing 'id' — skipping.", file=sys.stderr)
            continue
        # Collect numbered sub-figures
        subfigures = []
        n = 1
        while f"src{n}" in kwargs:
            subfigures.append({
                "src":   kwargs[f"src{n}"],
                "id":    kwargs.get(f"id{n}", f"panel-sub-{n}"),
                "field": kwargs.get(f"field{n}", ""),
                "time":  kwargs.get(f"time{n}", "mid"),
            })
            n += 1
        if not subfigures:
            print(f"[4dpaper] Warning: 4d-panel '{kwargs['id']}' has no sub-figures — skipping.", file=sys.stderr)
            continue
        results.append({
            "id":         kwargs["id"],
            "layout":     kwargs.get("layout", "1x1"),
            "height":     kwargs.get("height", "800px"),
            "caption":    kwargs.get("caption", ""),
            "subfigures": subfigures,
        })
    return results
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
.venv/bin/pytest tests/test_extension.py::TestParsePanelShortcodes -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_extension.py
git commit -m "feat: add parse_panel_shortcodes() with full test coverage"
```

---

## Task 3: `generate_panel_html()`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (after `generate_html_figure`)
- Test: `tests/test_extension.py` (add `TestGeneratePanelHtml`)

`generate_html_figure` is mocked so tests run without PyVista.

- [ ] **Step 1: Write the failing tests**

Add after `TestParsePanelShortcodes` in `tests/test_extension.py`:

```python
class TestGeneratePanelHtml:
    """generate_panel_html() composes sub-figure HTMLs into a CSS grid."""

    def _make_panel(self, layout="2x1", subfigures=None):
        if subfigures is None:
            subfigures = [
                {"src": "a.foam", "id": "fig-a", "field": "", "time": "mid"},
                {"src": "b.stl",  "id": "fig-b", "field": "", "time": "mid"},
            ]
        return {
            "id": "panel-test",
            "layout": layout,
            "height": "800px",
            "caption": "",
            "subfigures": subfigures,
        }

    def test_creates_composite_html(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None):
            output_path.write_text(f"<html>content-{fig_id}</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            mod.generate_panel_html(self._make_panel(), tmp_path)

        out = tmp_path / "panel-test.html"
        assert out.exists()

    def test_composite_contains_css_grid(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None):
            output_path.write_text("<html>x</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            mod.generate_panel_html(self._make_panel("2x1"), tmp_path)

        html = (tmp_path / "panel-test.html").read_text()
        assert "display:grid" in html
        assert "grid-template-columns:repeat(2,1fr)" in html

    def test_composite_contains_re_relay_script(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None):
            output_path.write_text("<html>x</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            mod.generate_panel_html(self._make_panel(), tmp_path)

        html = (tmp_path / "panel-test.html").read_text()
        assert "top.postMessage" in html           # upward relay
        assert "4dpaper-camera-ack" in html        # downward ack relay
        assert "querySelectorAll" in html          # broadcast to child iframes

    def test_composite_contains_subfigure_content(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None):
            output_path.write_text(f"<html>unique-{fig_id}</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            mod.generate_panel_html(self._make_panel(), tmp_path)

        html = (tmp_path / "panel-test.html").read_text()
        # Content is escaped for srcdoc — angle brackets become &lt; or content encoded
        assert "unique-fig-a" in html
        assert "unique-fig-b" in html

    def test_invalid_layout_raises(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None):
            output_path.write_text("<html>x</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            with pytest.raises(ValueError, match="layout"):
                mod.generate_panel_html(self._make_panel("bad"), tmp_path)

    def test_3x1_layout_has_three_columns(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()
        subs = [{"src": f"{i}.stl", "id": f"fig-{i}", "field": "", "time": "mid"} for i in range(3)]

        def fake_gen_html(src, field, time_spec, output_path, fig_id=None, available_fields=None):
            output_path.write_text("<html>x</html>")

        with patch.object(mod, "generate_html_figure", side_effect=fake_gen_html):
            mod.generate_panel_html(self._make_panel("3x1", subs), tmp_path)

        html = (tmp_path / "panel-test.html").read_text()
        assert "grid-template-columns:repeat(3,1fr)" in html
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
.venv/bin/pytest tests/test_extension.py::TestGeneratePanelHtml -v
```

Expected: `AttributeError: module 'fourDpaper' has no attribute 'generate_panel_html'`

- [ ] **Step 3: Implement `generate_panel_html()` in `4dpaper.py`**

Insert after `generate_html_figure()`:

```python
def generate_panel_html(panel: dict, figures_dir: Path) -> None:
    """
    Generate a composite HTML file embedding multiple vtk.js figures in a CSS grid.

    Layout convention: "COLSxROWS" e.g. "2x2" = 2 columns 2 rows.
    Output: figures_dir/<panel-id>.html — a single self-contained file.

    Camera sync: a bidirectional re-relay script forwards camera/field messages
    from child srcdoc iframes up to top (Quarto relay), and acks back down to
    all children so each sub-figure's camera badge works correctly.
    """
    layout = panel["layout"]
    try:
        ncols_s, nrows_s = layout.split("x")
        ncols, nrows = int(ncols_s), int(nrows_s)
    except (ValueError, AttributeError):
        raise ValueError(
            f"[4dpaper] 4d-panel layout must be 'COLSxROWS' (e.g. '2x2', '3x1'), got: '{layout}'"
        )

    height = panel.get("height", "800px")

    # Generate each sub-figure HTML (reuses caching inside generate_html_figure)
    for sub in panel["subfigures"]:
        src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]
        out = figures_dir / f"{sub['id']}.html"
        generate_html_figure(src, sub["field"], sub["time"], out, fig_id=sub["id"])

    # Build composite HTML
    re_relay = """\
<script>
window.addEventListener("message",function(e){
  if(!e.data)return;
  if(e.data.type==="4dpaper-camera"||e.data.type==="4dpaper-field-update"){
    top.postMessage(e.data,"*");
  }
  if(e.data.type==="4dpaper-camera-ack"||e.data.type==="4dpaper-field-ack"){
    var iframes=document.querySelectorAll("iframe");
    for(var i=0;i<iframes.length;i++){iframes[i].contentWindow.postMessage(e.data,"*");}
  }
});
</script>"""

    grid_style = (
        f'display:grid;grid-template-columns:repeat({ncols},1fr);'
        f'grid-template-rows:repeat({nrows},1fr);gap:4px;'
        f'width:100%;height:{height};background:#111;'
    )

    cells = []
    for sub in panel["subfigures"]:
        content = (figures_dir / f"{sub['id']}.html").read_text()
        escaped = content.replace("&", "&amp;").replace('"', "&quot;")
        cells.append(
            f'<iframe srcdoc="{escaped}" '
            f'style="width:100%;height:100%;border:none;" frameborder="0"></iframe>'
        )

    composite = (
        f'<!DOCTYPE html><html><body style="margin:0;padding:0;">'
        f'{re_relay}'
        f'<div style="{grid_style}">'
        + "".join(cells)
        + f'</div></body></html>'
    )

    out_path = figures_dir / f"{panel['id']}.html"
    out_path.write_text(composite)
    print(f"[4dpaper] Generated panel (HTML): {out_path}", file=sys.stderr)
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
.venv/bin/pytest tests/test_extension.py::TestGeneratePanelHtml -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_extension.py
git commit -m "feat: add generate_panel_html() with CSS grid and bidirectional re-relay"
```

---

## Task 4: `generate_panel_png()`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (after `generate_panel_html`)
- Test: `tests/test_extension.py` (add `TestGeneratePanelPng`)

`generate_png_figure` is mocked to create simple colored PNGs without PyVista.

- [ ] **Step 1: Write the failing tests**

Add after `TestGeneratePanelHtml` in `tests/test_extension.py`:

```python
class TestGeneratePanelPng:
    """generate_panel_png() composes sub-figure PNGs into a 1920×1080 grid."""

    def _make_panel(self, layout="2x1", n_subs=2):
        return {
            "id": "panel-test",
            "layout": layout,
            "height": "800px",
            "caption": "",
            "subfigures": [
                {"src": f"{i}.stl", "id": f"fig-{i}", "field": "", "time": "mid"}
                for i in range(n_subs)
            ],
        }

    def _fake_png_gen(self, color):
        """Return a side_effect that writes a solid-color 1920×1080 PNG."""
        from PIL import Image
        def _write(src, field, time_spec, output_path, fig_id=None):
            img = Image.new("RGB", (1920, 1080), color=color)
            img.save(str(output_path))
        return _write

    def test_creates_composite_png(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()
        with patch.object(mod, "generate_png_figure", side_effect=self._fake_png_gen("red")):
            mod.generate_panel_png(self._make_panel(), tmp_path)
        assert (tmp_path / "panel-test.png").exists()

    def test_composite_is_1920x1080(self, tmp_path):
        from unittest.mock import patch
        from PIL import Image
        mod = _load_4dpaper()
        with patch.object(mod, "generate_png_figure", side_effect=self._fake_png_gen("blue")):
            mod.generate_panel_png(self._make_panel("2x1", 2), tmp_path)
        img = Image.open(tmp_path / "panel-test.png")
        assert img.size == (1920, 1080)

    def test_2x2_layout_produces_correct_size(self, tmp_path):
        from unittest.mock import patch
        from PIL import Image
        mod = _load_4dpaper()
        with patch.object(mod, "generate_png_figure", side_effect=self._fake_png_gen("green")):
            mod.generate_panel_png(self._make_panel("2x2", 4), tmp_path)
        img = Image.open(tmp_path / "panel-test.png")
        assert img.size == (1920, 1080)

    def test_invalid_layout_raises(self, tmp_path):
        from unittest.mock import patch
        mod = _load_4dpaper()
        with patch.object(mod, "generate_png_figure", side_effect=self._fake_png_gen("red")):
            with pytest.raises(ValueError, match="layout"):
                mod.generate_panel_png(self._make_panel("bad"), tmp_path)
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
.venv/bin/pytest tests/test_extension.py::TestGeneratePanelPng -v
```

Expected: `AttributeError: module 'fourDpaper' has no attribute 'generate_panel_png'`

- [ ] **Step 3: Implement `generate_panel_png()` in `4dpaper.py`**

Insert after `generate_panel_html()`:

```python
def generate_panel_png(panel: dict, figures_dir: Path) -> None:
    """
    Generate a composite 1920×1080 PNG composed of sub-figure PNGs in a grid.

    Layout convention: "COLSxROWS" e.g. "2x2" = 2 columns 2 rows.
    Sub-figures are arranged left-to-right, then top-to-bottom (row-major).
    Output: figures_dir/<panel-id>.png
    """
    from PIL import Image

    layout = panel["layout"]
    try:
        ncols_s, nrows_s = layout.split("x")
        ncols, nrows = int(ncols_s), int(nrows_s)
    except (ValueError, AttributeError):
        raise ValueError(
            f"[4dpaper] 4d-panel layout must be 'COLSxROWS' (e.g. '2x2', '3x1'), got: '{layout}'"
        )

    cell_w = 1920 // ncols
    cell_h = 1080 // nrows

    # Generate each sub-figure PNG (reuses caching inside generate_png_figure)
    for sub in panel["subfigures"]:
        src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]
        out = figures_dir / f"{sub['id']}.png"
        generate_png_figure(src, sub["field"], sub["time"], out, fig_id=sub["id"])

    # Compose into 1920×1080 canvas
    canvas = Image.new("RGB", (1920, 1080), color="#1a1a2e")
    for idx, sub in enumerate(panel["subfigures"]):
        row, col = divmod(idx, ncols)
        img = Image.open(figures_dir / f"{sub['id']}.png").convert("RGB")
        img = img.resize((cell_w, cell_h), Image.LANCZOS)
        canvas.paste(img, (col * cell_w, row * cell_h))

    out_path = figures_dir / f"{panel['id']}.png"
    canvas.save(str(out_path))
    print(f"[4dpaper] Generated panel (PNG): {out_path}")
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
.venv/bin/pytest tests/test_extension.py::TestGeneratePanelPng -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Run all extension tests to catch regressions**

```bash
.venv/bin/pytest tests/test_extension.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_extension.py
git commit -m "feat: add generate_panel_png() with PIL grid composition"
```

---

## Task 5: `__main__` wiring + `fourd_panel` Lua handler

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (`__main__` section, lines ~1066–1075)
- Modify: `_extensions/4dpaper/shortcodes.lua`

No TDD here — Lua is not unit-testable and the `__main__` wiring is integration-only. Verification is by render test in Task 6.

- [ ] **Step 1: Wire `parse_panel_shortcodes` into the `__main__` loop**

In `4dpaper.py`, find the QMD scanning loop (around line 1066):

```python
figures = []
videos = []
for qmd in qmd_files:
    text = qmd.read_text()
    figures.extend(parse_shortcodes(text))
    videos.extend(parse_video_shortcodes(text))
```

Change to:

```python
figures = []
videos = []
panels = []
for qmd in qmd_files:
    text = qmd.read_text()
    figures.extend(parse_shortcodes(text))
    videos.extend(parse_video_shortcodes(text))
    panels.extend(parse_panel_shortcodes(text))
```

- [ ] **Step 2: Add the "no shortcodes" guard update**

The existing guard (around line 1073) checks `if not figures and not videos`. Update it to also skip when no panels:

```python
if not figures and not videos and not panels:
    print("[4dpaper] No 4d-image, 4d-video, or 4d-panel shortcodes found.", file=sys.stderr)
    return
```

- [ ] **Step 3: Add the panels dispatch loop**

After the existing `for vid in videos:` loop, add:

```python
# ── Panel shortcode processing ─────────────────────────────────────────────
for panel in panels:
    panel_id = panel["id"]
    out_html = figures_dir / f"{panel_id}.html"
    out_png  = figures_dir / f"{panel_id}.png"

    # Determine max mtime of all sub-figure source files and camera JSONs
    sub_mtimes = []
    for sub in panel["subfigures"]:
        src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]
        if src.exists():
            sub_mtimes.append(src.stat().st_mtime)
        cam = _project_root / "state" / f"camera_{sub['id']}.json"
        if cam.exists():
            sub_mtimes.append(cam.stat().st_mtime)
    script_mtime = _here.stat().st_mtime
    sub_mtimes.append(script_mtime)
    max_dep_mtime = max(sub_mtimes) if sub_mtimes else 0.0

    if out_html.exists() and out_html.stat().st_mtime >= max_dep_mtime:
        print(f"[4dpaper] {panel_id}.html is up to date — skipping.", file=sys.stderr)
    else:
        print(f"[4dpaper] Generating panel {panel_id}.html …", file=sys.stderr)
        try:
            generate_panel_html(panel, figures_dir)
        except Exception as exc:
            print(f"[4dpaper] ERROR generating panel {panel_id}.html: {exc}", file=sys.stderr)
            sys.exit(1)

    if out_png.exists() and out_png.stat().st_mtime >= max_dep_mtime:
        print(f"[4dpaper] {panel_id}.png is up to date — skipping.")
    else:
        print(f"[4dpaper] Generating panel {panel_id}.png …")
        try:
            generate_panel_png(panel, figures_dir)
        except Exception as exc:
            print(f"[4dpaper] ERROR generating panel {panel_id}.png: {exc}")
            sys.exit(1)
```

- [ ] **Step 4: Add `fourd_panel` to `shortcodes.lua`**

Open `_extensions/4dpaper/shortcodes.lua`. After the `fourd_video` function (before the `return` table), add:

```lua
local function fourd_panel(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))
  local height  = pandoc.utils.stringify(kwargs["height"]  or pandoc.Str("800px"))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-panel: missing required attribute <code>id</code></div>')
  end

  -- ── HTML output: embed composite vtk.js panel ─────────────────────────────
  if quarto.doc.isFormat("html") then
    local fig_path = "state/figures/" .. id .. ".html"
    local f = io.open(fig_path, "r")
    if f then
      local content = f:read("*all")
      f:close()
      local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")

      -- Inject relay script once per page (shared with fourd_image/fourd_video)
      local relay_script = ""
      if not _relay_injected then
        _relay_injected = true
        relay_script = [[
<script>
(function(){
  window.addEventListener("message",function(e){
    if(!e.data)return;
    if(e.data.type==="4dpaper-camera"){
      var figId=e.data.fig_id;
      var camera=e.data.camera;
      fetch("/camera/"+figId,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(camera)
      }).then(function(r){
        if(r.ok&&e.source){
          e.source.postMessage({type:"4dpaper-camera-ack",fig_id:figId,status:"ok"},"*");
        }
      }).catch(function(){
        if(e.source){
          e.source.postMessage({type:"4dpaper-camera-ack",fig_id:figId,status:"error"},"*");
        }
      });
    } else if(e.data.type==="4dpaper-field-update"){
      var figId=e.data.fig_id;
      var payload=e.data.data;
      fetch("/field/"+figId,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(payload)
      }).then(function(r){
        if(r.ok&&e.source){
          e.source.postMessage({type:"4dpaper-field-ack",fig_id:figId,status:"ok"},"*");
        }
      }).catch(function(){
        if(e.source){
          e.source.postMessage({type:"4dpaper-field-ack",fig_id:figId,status:"error"},"*");
        }
      });
    }
  });
})();
</script>
]]
      end

      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        '<iframe srcdoc="' .. escaped .. '" width="100%" height="' .. height .. '" ' ..
        'frameborder="0" style="border:none;border-radius:4px;display:block;"></iframe>\n' ..
        (caption ~= "" and
          '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
          or "") ..
        '</figure>\n' ..
        relay_script)
    else
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;' ..
        'border-radius:4px;margin:1rem 0">' ..
        '<strong>⚠ 4D Panel not yet rendered</strong><br>' ..
        'Panel ID: <code>' .. id .. '</code><br>' ..
        '<small>Click <strong>Rebuild HTML</strong> in the dashboard to generate.</small>' ..
        '</div>')
    end

  -- ── PDF / LaTeX output: embed composite PNG ───────────────────────────────
  else
    local fig_path = "state/figures/" .. id .. ".png"
    local f = io.open(fig_path, "r")
    if f then
      f:close()
      local img = pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, { width = "90%" }))
      return pandoc.Para({ img })
    else
      return pandoc.Para({
        pandoc.Str("[Panel "),
        pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
  end
end
```

- [ ] **Step 5: Register `fourd_panel` in the return table**

Find the return table at the bottom of `shortcodes.lua`:

```lua
return {
  ["4d-image"] = fourd_image,
  ["4d-video"] = fourd_video,
}
```

Change to:

```lua
return {
  ["4d-image"] = fourd_image,
  ["4d-video"] = fourd_video,
  ["4d-panel"] = fourd_panel,
}
```

- [ ] **Step 6: Run existing tests to catch regressions**

```bash
.venv/bin/pytest tests/test_extension.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py _extensions/4dpaper/shortcodes.lua
git commit -m "feat: wire 4d-panel into __main__ dispatch and add fourd_panel Lua handler"
```

---

## Task 6: End-to-End Integration Test

**Files:**
- Modify: `analysis_report.qmd` (add one `{{< 4d-panel >}}` shortcode)

Verify the full pipeline: Python generates `state/figures/panel-demo.html` + `.png`; Lua embeds it in the rendered HTML.

- [ ] **Step 1: Add a demo panel to `analysis_report.qmd`**

After the existing format test section (or after `## Results`), add:

```markdown
## Panel Demo

{{< 4d-panel id="panel-demo" layout="2x1" height="600px"
    caption="Side-by-side comparison: STL geometry vs XDMF fiber directions"
    src1="tests/data/base.stl"             id1="fig-panel-stl"  field1=""
    src2="tests/data/fiber_directions.xdmf" id2="fig-panel-xdmf" field2="fiber" >}}
```

- [ ] **Step 2: Run the render**

```bash
.venv/bin/quarto render analysis_report.qmd --to html
```

Expected: no `[4dpaper] ERROR` lines. Output includes:
```
[4dpaper] Generating panel panel-demo.html …
[4dpaper] Generated panel (HTML): state/figures/panel-demo.html
[4dpaper] Generating panel panel-demo.png …
[4dpaper] Generated panel (PNG): state/figures/panel-demo.png
```

- [ ] **Step 3: Verify generated files**

```bash
ls -lh state/figures/panel-demo.*
```

Expected: `panel-demo.html` (non-zero size) and `panel-demo.png` exist.

- [ ] **Step 4: Open the rendered HTML and confirm the panel appears**

```bash
open _output/analysis_report.html
```

Confirm a 2-column panel is visible with two 3D viewers side by side.

- [ ] **Step 5: Rotate one sub-figure and check camera sync**

In the browser, rotate one of the sub-figures. Confirm:
- The green "📷 Camera synced" badge appears in that sub-figure after rotating.
- `state/camera_fig-panel-stl.json` or `state/camera_fig-panel-xdmf.json` is created/updated.

```bash
ls state/camera_fig-panel-*.json
```

- [ ] **Step 6: Run the full test suite one final time**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests PASS (51 data_loader tests + all extension tests).

- [ ] **Step 7: Commit**

```bash
git add analysis_report.qmd state/figures/panel-demo.html state/figures/panel-demo.png
git commit -m "feat: add 4d-panel end-to-end demo — 2x1 panel with STL + XDMF sub-figures"
```
