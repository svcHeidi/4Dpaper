# Figure Style Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `_4dpaper_styles.yml` file and wire named visual style templates (per-field colormap, background color, axis text color) into `{{< 4d-image >}}` via a new `style=` shortcode parameter.

**Architecture:** Two pure functions (`load_styles`, `resolve_style`) handle all style logic in isolation. `parse_shortcodes` gets a `style` key. `generate_html_figure` and `generate_png_figure` get three new kwargs (`background`, `axis_color`, `cmap`). `main()` loads styles once and passes resolved config to generators; the styles YAML path is added as an `extra_dep` for cache invalidation.

**Tech Stack:** PyYAML (`import yaml`), PyVista `scalar_bar_args`, existing `is_cache_valid(extra_deps=)` parameter, `4dpaper.py` only — `shortcodes.lua` not touched.

---

## Project State

These files exist and must not be replaced, only modified:
- `_extensions/4dpaper/4dpaper.py` — pre-render hook
- `tests/test_extension.py` — existing tests; run to verify no regressions
- `tests/test_pvsm.py` — existing tests; run to verify no regressions

Run tests with: `source .venv/bin/activate && pytest tests/ -v`

Key line numbers in `4dpaper.py` (verify with `grep -n` before editing):
- `parse_shortcodes()` — line 63; `setdefault` block at lines 84–86
- `generate_png_figure()` — line 781; `pl.background_color = "#1a1a2e"` at line 823; `cmap="coolwarm"` at line 829; `scalar_bar_args={"title": field}` at line 831
- `generate_html_figure()` — line 849; same hardcoded values at lines 894, 900, 902
- `main()` — line 1489; figure loop at lines 1529–1607
- HTML cache check: line 1566 — `is_cache_valid(out_html, src, field_path=field_state_path)`
- PNG cache check: line 1598 — `is_cache_valid(out_png, src, camera_path=camera_path, field_path=field_state_path)`
- HTML generator call: lines 1571–1574
- PNG generator call: line 1604

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `_extensions/4dpaper/4dpaper.py` | **Modify** | Add `load_styles()`, `resolve_style()`, update `parse_shortcodes()`, `generate_html_figure()`, `generate_png_figure()`, `main()` |
| `_4dpaper_styles.yml` | **Create** | User-facing style definitions (starter template) |
| `tests/test_styles.py` | **Create** | Tests for all new/modified functions |

---

## Task 1: `load_styles()` and `resolve_style()` — pure functions

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (add two functions after `is_cache_valid`)
- Create: `tests/test_styles.py`

---

- [ ] **Step 1: Create `tests/test_styles.py` with failing tests**

```python
# tests/test_styles.py
"""Tests for figure style template loading and resolution."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
import pytest

def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLoadStyles:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        mod = _load_4dpaper()
        result = mod.load_styles(tmp_path / "nonexistent.yml")
        assert result == {}

    def test_malformed_yaml_returns_empty_dict(self, tmp_path):
        bad = tmp_path / "styles.yml"
        bad.write_text(": bad: yaml: [[[")
        mod = _load_4dpaper()
        result = mod.load_styles(bad)
        assert result == {}

    def test_valid_file_parses_correctly(self, tmp_path):
        yml = tmp_path / "styles.yml"
        yml.write_text("""
defaults:
  background: "white"
  axis_color: "black"
  cmap: "coolwarm"
styles:
  vm-dark:
    background: "#1a1a2e"
    axis_color: "white"
    fields:
      Vm: viridis
""")
        mod = _load_4dpaper()
        result = mod.load_styles(yml)
        assert result["defaults"]["background"] == "white"
        assert result["styles"]["vm-dark"]["background"] == "#1a1a2e"
        assert result["styles"]["vm-dark"]["fields"]["Vm"] == "viridis"


class TestResolveStyle:
    def _config(self):
        return {
            "defaults": {"background": "white", "axis_color": "black", "cmap": "coolwarm"},
            "styles": {
                "vm-dark": {
                    "background": "#1a1a2e",
                    "axis_color": "white",
                    "fields": {"Vm": "viridis", "activationTime": "plasma"},
                },
                "no-fields": {
                    "background": "#222",
                    "axis_color": "gray",
                    "cmap": "jet",
                },
            },
        }

    def test_per_field_cmap_wins(self):
        mod = _load_4dpaper()
        result = mod.resolve_style(self._config(), "vm-dark", "Vm")
        assert result["cmap"] == "viridis"

    def test_style_cmap_fallback_when_field_not_listed(self):
        mod = _load_4dpaper()
        result = mod.resolve_style(self._config(), "no-fields", "Vm")
        assert result["cmap"] == "jet"

    def test_defaults_cmap_when_no_style(self):
        mod = _load_4dpaper()
        result = mod.resolve_style(self._config(), "", "Vm")
        assert result["cmap"] == "coolwarm"

    def test_background_from_named_style(self):
        mod = _load_4dpaper()
        result = mod.resolve_style(self._config(), "vm-dark", "Vm")
        assert result["background"] == "#1a1a2e"

    def test_axis_color_from_named_style(self):
        mod = _load_4dpaper()
        result = mod.resolve_style(self._config(), "vm-dark", "Vm")
        assert result["axis_color"] == "white"

    def test_defaults_used_when_style_name_empty(self):
        mod = _load_4dpaper()
        result = mod.resolve_style(self._config(), "", "Vm")
        assert result["background"] == "white"
        assert result["axis_color"] == "black"

    def test_unknown_style_name_falls_back_to_defaults(self):
        mod = _load_4dpaper()
        result = mod.resolve_style(self._config(), "nonexistent", "Vm")
        assert result["cmap"] == "coolwarm"
        assert result["background"] == "white"

    def test_empty_config_returns_hard_defaults(self):
        mod = _load_4dpaper()
        result = mod.resolve_style({}, "", "Vm")
        assert result == {"background": "white", "axis_color": "black", "cmap": "coolwarm"}

    def test_transparent_background_normalised_to_white(self):
        mod = _load_4dpaper()
        config = {"defaults": {"background": "transparent", "axis_color": "black", "cmap": "coolwarm"}, "styles": {}}
        result = mod.resolve_style(config, "", "Vm")
        assert result["background"] == "white"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/test_styles.py -v
```

Expected: `FAILED` — `load_styles` and `resolve_style` do not exist yet.

- [ ] **Step 3: Add `load_styles()` and `resolve_style()` to `4dpaper.py`**

Read `4dpaper.py` and find `is_cache_valid()`. Add the two new functions immediately after it (before the next function).

```python
# -- Style template loading and resolution ------------------------------------

def load_styles(path: Path) -> dict:
    """
    Load _4dpaper_styles.yml. Returns {} on missing or malformed file.
    Never raises — warnings go to stderr.
    """
    if not path.exists():
        return {}
    try:
        import yaml
        with path.open() as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            print(f"[4dpaper] WARNING: {path} is not a YAML mapping — ignoring styles.", file=sys.stderr)
            return {}
        return data
    except Exception as exc:
        print(f"[4dpaper] WARNING: could not load {path}: {exc} — ignoring styles.", file=sys.stderr)
        return {}


def resolve_style(styles_config: dict, style_name: str, field_name: str) -> dict:
    """
    Resolve {background, axis_color, cmap} from styles config.

    Pure function — no I/O. Safe to call with empty styles_config.
    'transparent' background is normalised to 'white' (PyVista limitation).
    """
    _HARD = {"background": "white", "axis_color": "black", "cmap": "coolwarm"}

    defaults = styles_config.get("defaults", {}) if styles_config else {}
    styles   = styles_config.get("styles",   {}) if styles_config else {}

    # Start from hard defaults, override with file-level defaults
    resolved = {
        "background": defaults.get("background", _HARD["background"]),
        "axis_color": defaults.get("axis_color", _HARD["axis_color"]),
        "cmap":       defaults.get("cmap",       _HARD["cmap"]),
    }

    # Apply named style overrides (skip silently if style_name is "")
    if style_name:
        if style_name not in styles:
            print(
                f"[4dpaper] WARNING: style '{style_name}' not found in styles config — using defaults.",
                file=sys.stderr,
            )
        else:
            tmpl = styles[style_name]
            if "background"  in tmpl: resolved["background"]  = tmpl["background"]
            if "axis_color"  in tmpl: resolved["axis_color"]  = tmpl["axis_color"]
            if "cmap"        in tmpl: resolved["cmap"]        = tmpl["cmap"]
            # Per-field cmap override
            field_cmaps = tmpl.get("fields", {})
            if field_name and field_name in field_cmaps:
                resolved["cmap"] = field_cmaps[field_name]

    # Normalise 'transparent' → 'white' (PyVista does not support transparent backgrounds)
    if resolved["background"] == "transparent":
        resolved["background"] = "white"

    return resolved
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/test_styles.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Verify no regressions**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/test_extension.py tests/test_pvsm.py -v 2>&1 | tail -10
```

Expected: same pass/fail counts as before this task.

- [ ] **Step 6: Commit**

```bash
cd /Users/simaocastro/4Dpapers && git add _extensions/4dpaper/4dpaper.py tests/test_styles.py && git commit -m "feat: add load_styles() and resolve_style() for figure style templates"
```

---

## Task 2: Extend `parse_shortcodes()` with `style` param

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (line ~86)
- Modify: `tests/test_styles.py` (add `TestParseShortcodesStyle`)

---

- [ ] **Step 1: Add failing tests to `tests/test_styles.py`**

Append to the file:

```python
class TestParseShortcodesStyle:
    def test_style_param_parsed(self):
        mod = _load_4dpaper()
        text = '{{< 4d-image src="case.foam" id="fig-vm" field="Vm" style="vm-dark" >}}'
        result = mod.parse_shortcodes(text)
        assert len(result) == 1
        assert result[0]["style"] == "vm-dark"

    def test_style_defaults_to_empty_string(self):
        mod = _load_4dpaper()
        text = '{{< 4d-image src="case.foam" id="fig-vm" field="Vm" >}}'
        result = mod.parse_shortcodes(text)
        assert result[0]["style"] == ""

    def test_style_key_always_present(self):
        """Every returned dict must have 'style' key even when omitted."""
        mod = _load_4dpaper()
        text = '{{< 4d-image src="case.foam" id="fig-vm" >}}'
        result = mod.parse_shortcodes(text)
        assert "style" in result[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/test_styles.py::TestParseShortcodesStyle -v
```

Expected: `FAILED` — no `style` key in results yet.

- [ ] **Step 3: Add `style` default to `parse_shortcodes()`**

In `4dpaper.py`, find the `parse_shortcodes` function (line ~63). After the existing `setdefault` lines (currently lines 84–86):

```python
        kwargs.setdefault("time", "mid")
        kwargs.setdefault("field", "")
        kwargs.setdefault("fields", "")  # comma-separated list for live switching
```

Add one more line:

```python
        kwargs.setdefault("time", "mid")
        kwargs.setdefault("field", "")
        kwargs.setdefault("fields", "")  # comma-separated list for live switching
        kwargs.setdefault("style", "")   # named style template
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/test_styles.py -v
```

Expected: all 15 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/simaocastro/4Dpapers && git add _extensions/4dpaper/4dpaper.py tests/test_styles.py && git commit -m "feat: add style= param to parse_shortcodes()"
```

---

## Task 3: Update `generate_html_figure()` and `generate_png_figure()`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (lines ~781–910)
- Modify: `tests/test_styles.py` (add `TestGeneratorsAcceptStyleParams`)

---

- [ ] **Step 1: Add failing test to `tests/test_styles.py`**

Append:

```python
class TestGeneratorsAcceptStyleParams:
    def test_generate_png_figure_accepts_style_params(self):
        """generate_png_figure must accept background, axis_color, cmap kwargs."""
        import inspect
        mod = _load_4dpaper()
        sig = inspect.signature(mod.generate_png_figure)
        params = sig.parameters
        assert "background" in params
        assert "axis_color" in params
        assert "cmap" in params
        assert params["background"].default == "white"
        assert params["axis_color"].default == "black"
        assert params["cmap"].default == "coolwarm"

    def test_generate_html_figure_accepts_style_params(self):
        """generate_html_figure must accept background, axis_color, cmap kwargs."""
        import inspect
        mod = _load_4dpaper()
        sig = inspect.signature(mod.generate_html_figure)
        params = sig.parameters
        assert "background" in params
        assert "axis_color" in params
        assert "cmap" in params
        assert params["background"].default == "white"
        assert params["axis_color"].default == "black"
        assert params["cmap"].default == "coolwarm"

    def test_generate_png_figure_hardcoded_values_replaced(self):
        """generate_png_figure body must not contain hardcoded '#1a1a2e' or cmap='coolwarm'."""
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_png_figure)
        assert "#1a1a2e" not in source, \
            "Hardcoded background '#1a1a2e' must be replaced with background param"
        # After fix, body uses `cmap=cmap` (variable). Hardcoded literal would appear as cmap="coolwarm".
        # Note: the signature default `cmap: str = "coolwarm"` uses ': str =' not '=', so won't match.
        assert 'cmap="coolwarm"' not in source, \
            "Hardcoded cmap='coolwarm' in add_mesh call must be replaced with cmap param"

    def test_generate_html_figure_hardcoded_values_replaced(self):
        """generate_html_figure body must not contain hardcoded '#1a1a2e' or cmap='coolwarm'."""
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_html_figure)
        assert "#1a1a2e" not in source, \
            "Hardcoded background '#1a1a2e' must be replaced with background param"
        assert 'cmap="coolwarm"' not in source, \
            "Hardcoded cmap='coolwarm' in add_mesh call must be replaced with cmap param"
```

- [ ] **Step 2: Verify tests fail**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/test_styles.py::TestGeneratorsAcceptStyleParams -v
```

Expected: FAILED — params don't exist yet.

- [ ] **Step 3: Update `generate_png_figure()` signature and body**

Find `generate_png_figure` (line ~781). Change its signature from:

```python
def generate_png_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
) -> None:
```

To:

```python
def generate_png_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
    background: str = "white",
    axis_color: str = "black",
    cmap: str = "coolwarm",
) -> None:
```

Then in the body, replace:

```python
    pl = pv.Plotter(off_screen=True, window_size=(1920, 1080))
    pl.background_color = "#1a1a2e"

    if field and (field in surface.point_data or field in surface.cell_data):
        pl.add_mesh(
            surface,
            scalars=field,
            cmap="coolwarm",
            smooth_shading=True,
            scalar_bar_args={"title": field},
        )
```

With:

```python
    pl = pv.Plotter(off_screen=True, window_size=(1920, 1080))
    pl.background_color = background if background != "transparent" else "white"

    if field and (field in surface.point_data or field in surface.cell_data):
        pl.add_mesh(
            surface,
            scalars=field,
            cmap=cmap,
            smooth_shading=True,
            scalar_bar_args={"title": field, "color": axis_color},
        )
```

- [ ] **Step 4: Update `generate_html_figure()` signature and body**

Find `generate_html_figure` (line ~849). Change its signature from:

```python
def generate_html_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
    available_fields: list[str] | None = None,
    camera_preview_only: bool = False,
) -> None:
```

To:

```python
def generate_html_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
    available_fields: list[str] | None = None,
    camera_preview_only: bool = False,
    background: str = "white",
    axis_color: str = "black",
    cmap: str = "coolwarm",
) -> None:
```

Then in the body, replace (lines ~893–902):

```python
    pl = pv.Plotter(off_screen=True, window_size=(900, 600))
    pl.background_color = "#1a1a2e"

    if field and (field in surface.point_data or field in surface.cell_data):
        pl.add_mesh(
            surface,
            scalars=field,
            cmap="coolwarm",
            smooth_shading=True,
            scalar_bar_args={"title": field},
        )
```

With:

```python
    pl = pv.Plotter(off_screen=True, window_size=(900, 600))
    pl.background_color = background if background != "transparent" else "white"

    if field and (field in surface.point_data or field in surface.cell_data):
        pl.add_mesh(
            surface,
            scalars=field,
            cmap=cmap,
            smooth_shading=True,
            scalar_bar_args={"title": field, "color": axis_color},
        )
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/test_styles.py -v
```

Expected: all 19 tests PASS (12 from Task 1 + 3 from Task 2 + 4 new).

- [ ] **Step 6: Verify no regressions**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/test_extension.py tests/test_pvsm.py -v 2>&1 | tail -10
```

Expected: same counts as before.

- [ ] **Step 7: Commit**

```bash
cd /Users/simaocastro/4Dpapers && git add _extensions/4dpaper/4dpaper.py tests/test_styles.py && git commit -m "feat: add background/axis_color/cmap params to generate_html_figure() and generate_png_figure()"
```

---

## Task 4: Wire styles into `main()`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (lines ~1529–1607)
- Modify: `tests/test_styles.py` (add `TestCacheInvalidationWithStyles`)

---

- [ ] **Step 1: Add cache invalidation test to `tests/test_styles.py`**

Append:

```python
class TestCacheInvalidationWithStyles:
    def test_styles_yml_change_triggers_regen(self, tmp_path):
        """Touching _4dpaper_styles.yml should invalidate the figure cache."""
        import time
        mod = _load_4dpaper()

        styles_yml = tmp_path / "_4dpaper_styles.yml"
        src        = tmp_path / "case.foam"
        output     = tmp_path / "fig.html"

        styles_yml.write_text("defaults:\n  cmap: coolwarm\n")
        src.write_text("x")
        time.sleep(0.02)
        output.write_text("<html/>")   # output is newest
        time.sleep(0.02)
        styles_yml.touch()             # now styles_yml is newest

        result = mod.is_cache_valid(output, src, extra_deps=[styles_yml])
        assert result is False

    def test_styles_yml_older_than_output_no_regen(self, tmp_path):
        import time
        mod = _load_4dpaper()

        styles_yml = tmp_path / "_4dpaper_styles.yml"
        src        = tmp_path / "case.foam"
        output     = tmp_path / "fig.html"

        styles_yml.write_text("defaults:\n  cmap: coolwarm\n")
        src.write_text("x")
        time.sleep(0.02)
        output.write_text("<html/>")   # output is newest

        result = mod.is_cache_valid(output, src, extra_deps=[styles_yml])
        assert result is True
```

- [ ] **Step 2: Verify tests pass (they should — `is_cache_valid` already has `extra_deps`)**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/test_styles.py::TestCacheInvalidationWithStyles -v
```

Expected: both PASS immediately (no implementation change needed — `is_cache_valid` already supports `extra_deps`).

- [ ] **Step 3: Wire styles loading and resolution into `main()`**

In `4dpaper.py`, find `main()` (line ~1489). Add styles loading right after the `figures_dir.mkdir` call (currently around line 1527):

Find:
```python
    figures_dir = _project_root / "state" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    for fig in figures:
```

Replace with:
```python
    figures_dir = _project_root / "state" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Load style templates once for all figures
    styles_yml_path = _project_root / "_4dpaper_styles.yml"
    styles_config = load_styles(styles_yml_path)
    styles_extra_deps = [styles_yml_path] if styles_yml_path.exists() else []

    for fig in figures:
```

- [ ] **Step 4: Resolve style per figure and pass to generators**

In the same `main()` function, inside `for fig in figures:`, find the line that reads `field = fig["field"]` (around line 1532). Add the style resolution immediately after it:

Find:
```python
        fig_id = fig["id"]
        src = Path(fig["src"]) if Path(fig["src"]).is_absolute() else _project_root / fig["src"]
        field = fig["field"]
        time_spec = fig.get("time", "mid")
```

Replace with:
```python
        fig_id = fig["id"]
        src = Path(fig["src"]) if Path(fig["src"]).is_absolute() else _project_root / fig["src"]
        field = fig["field"]
        time_spec = fig.get("time", "mid")
        style = resolve_style(styles_config, fig["style"], field)
```

- [ ] **Step 5: Pass `extra_deps` to the HTML `is_cache_valid()` call**

Find the HTML cache check (around line 1566):

```python
        if not script_newer and is_cache_valid(out_html, src, field_path=field_state_path):
```

Replace with:

```python
        if not script_newer and is_cache_valid(out_html, src, field_path=field_state_path, extra_deps=styles_extra_deps):
```

- [ ] **Step 6: Pass style to `generate_html_figure()` and `extra_deps` to PNG cache check**

Find the generator call (around line 1571):

```python
                generate_html_figure(
                    src, field, time_spec, out_html,
                    fig_id=fig_id, available_fields=available_fields,
                )
```

Replace with:

```python
                generate_html_figure(
                    src, field, time_spec, out_html,
                    fig_id=fig_id, available_fields=available_fields,
                    background=style["background"],
                    axis_color=style["axis_color"],
                    cmap=style["cmap"],
                )
```

Find the PNG cache check (around line 1598):

```python
        png_fresh = is_cache_valid(out_png, src, camera_path=camera_path, field_path=field_state_path)
```

Replace with:

```python
        png_fresh = is_cache_valid(out_png, src, camera_path=camera_path, field_path=field_state_path, extra_deps=styles_extra_deps)
```

Find the PNG generator call (around line 1604):

```python
                generate_png_figure(src, field, time_spec, out_png, fig_id=fig_id)
```

Replace with:

```python
                generate_png_figure(
                    src, field, time_spec, out_png, fig_id=fig_id,
                    background=style["background"],
                    axis_color=style["axis_color"],
                    cmap=style["cmap"],
                )
```

- [ ] **Step 7: Run all tests**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/test_styles.py -v
```

Expected: all 21 tests PASS (19 from prior tasks + 2 new cache tests).

- [ ] **Step 8: Verify no regressions**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/ -v 2>&1 | tail -15
```

Expected: all `test_styles.py` tests PASS; existing test pass counts unchanged.

- [ ] **Step 9: Commit**

```bash
cd /Users/simaocastro/4Dpapers && git add _extensions/4dpaper/4dpaper.py tests/test_styles.py && git commit -m "feat: wire style templates into main() — resolve per figure, pass to generators, cache invalidation"
```

---

## Task 5: Create `_4dpaper_styles.yml` starter file + integration smoke test

**Files:**
- Create: `_4dpaper_styles.yml`
- Modify: `analysis_report.qmd` (add `style="vm-dark"` to one existing `4d-image` shortcode)

---

- [ ] **Step 1: Create `_4dpaper_styles.yml`**

```yaml
# 4Dpapers figure style templates
# Reference in shortcodes: {{< 4d-image style="vm-dark" ... >}}
#
# defaults: applied to all figures with no style= or missing field mapping
# styles:   named templates referenced via style="name"

defaults:
  background: "white"
  axis_color: "black"
  cmap: "coolwarm"

styles:
  vm-dark:
    background: "#1a1a2e"
    axis_color: "white"
    fields:
      Vm: coolwarm
      activationTime: viridis
      activationVelocity: plasma

  publication:
    background: "white"
    axis_color: "black"
    fields:
      Vm: RdBu
      activationTime: YlOrRd
      activationVelocity: plasma
```

- [ ] **Step 2: Add `style="vm-dark"` to one shortcode in `analysis_report.qmd`**

Read `analysis_report.qmd` to find the first `{{< 4d-image ... >}}` shortcode (the one with `id="fig-vm"`). Add `style="vm-dark"` to it. For example, change:

```
{{< 4d-image src="..." field="Vm" id="fig-vm" ... >}}
```

To:

```
{{< 4d-image src="..." field="Vm" id="fig-vm" style="vm-dark" ... >}}
```

- [ ] **Step 3: Touch existing figures to avoid script-mtime regeneration**

```bash
touch /Users/simaocastro/4Dpapers/state/figures/*.html /Users/simaocastro/4Dpapers/state/figures/*.png 2>/dev/null || true
```

- [ ] **Step 4: Rebuild HTML and verify style is applied**

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && FOURD_APP_MODE=1 quarto render analysis_report.qmd --to html --profile apphtml 2>&1 | grep -E "4dpaper|Output created|ERROR"
```

Expected:
- `[4dpaper] Generating fig-vm.html` appears (cache invalidated by `_4dpaper_styles.yml` being new)
- `Output created: _output/analysis_report.html`
- No `ERROR` lines

- [ ] **Step 4b: Verify the dark background was actually applied to the generated figure**

The `vm-dark` style sets `background: "#1a1a2e"`. After rebuild, the generated HTML figure must contain this colour, proving that `main()` correctly passed the resolved style to the generator.

```bash
grep -c "1a1a2e" /Users/simaocastro/4Dpapers/state/figures/fig-vm.html
```

Expected: `1` or more (the vtk.js scene will embed the background colour). If `0` is returned, the style was not wired through `main()` — re-check Task 4 Step 3–6.

- [ ] **Step 5: Commit**

```bash
cd /Users/simaocastro/4Dpapers && git add _4dpaper_styles.yml analysis_report.qmd && git commit -m "feat: add _4dpaper_styles.yml starter template and wire vm-dark style into fig-vm"
```

---

## Final verification

```bash
cd /Users/simaocastro/4Dpapers && source .venv/bin/activate && pytest tests/ -v 2>&1 | tail -20
```

Expected: all `test_styles.py` tests pass, no regressions in `test_extension.py` or `test_pvsm.py`.
