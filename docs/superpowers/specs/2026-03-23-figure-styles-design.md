# Figure Style Templates Design

**Goal:** Add a `_4dpaper_styles.yml` file that defines named visual style templates (colormap per field, background color, axis text color) and wire them into `{{< 4d-image >}}` via a new `style=` shortcode parameter.

**Scope:** `4d-image` only for this implementation. Other figure types (`4d-video`, `4d-panel`, `4d-pvsm`) are out of scope.

**Tech Stack:** PyYAML (already available), PyVista `scalar_bar_args` + `add_axes`, existing `is_cache_valid()` `extra_deps` parameter, `4dpaper.py` / `shortcodes.lua` unchanged except targeted additions.

---

## Style File Format

`_4dpaper_styles.yml` lives in the repo root alongside `_quarto.yml`.

```yaml
defaults:
  background: "transparent"
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
    background: "transparent"
    axis_color: "black"
    fields:
      Vm: RdBu
      activationTime: YlOrRd
```

### Schema

**`defaults` block** (all optional — hard defaults used if absent):
| Key | Type | Hard default |
|-----|------|--------------|
| `background` | CSS color string or `"transparent"` | `"transparent"` |
| `axis_color` | CSS color string | `"black"` |
| `cmap` | matplotlib colormap name | `"coolwarm"` |

**`styles` block** — named templates, each optionally overriding any default key plus a `fields:` mapping:
| Key | Type | Description |
|-----|------|-------------|
| `background` | CSS color string or `"transparent"` | Overrides `defaults.background` |
| `axis_color` | CSS color string | Overrides `defaults.axis_color` |
| `cmap` | matplotlib colormap name | Fallback cmap if field not in `fields:` |
| `fields` | dict[str, str] | Per-field colormap overrides |

The file is optional. If absent, all figures render with the hard defaults (transparent background, black axis text, coolwarm colormap) — same behavior as today.

---

## Shortcode Change

`{{< 4d-image >}}` gains one new optional parameter:

```
{{< 4d-image src="case.foam" field="Vm" id="fig-vm" style="vm-dark" >}}
```

`style=""` is the default (no style = use `defaults` block). Existing shortcodes without `style=` are unaffected.

`parse_shortcodes()` adds `style` to the optional kwargs with default `""`.

---

## Resolution Logic

`resolve_style(styles_config, style_name, field_name) -> dict` is a pure function that returns `{background, axis_color, cmap}`.

**Resolution order (first match wins):**

For `cmap`:
1. `styles[style_name].fields[field_name]` — per-field override in named style
2. `styles[style_name].cmap` — style-level fallback
3. `defaults.cmap` — global fallback
4. Hard default: `"coolwarm"`

For `background` and `axis_color`:
1. `styles[style_name].background` / `styles[style_name].axis_color`
2. `defaults.background` / `defaults.axis_color`
3. Hard defaults: `"transparent"` / `"black"`

**Error handling:**
- Unknown `style_name` (not in `styles:` block): log warning, fall back to defaults — never a hard error
- Malformed YAML: log warning, treat as empty file — never a hard error
- Missing `_4dpaper_styles.yml`: silently use hard defaults

---

## Changes to `4dpaper.py`

### New functions

```python
def load_styles(path: Path) -> dict:
    """Load _4dpaper_styles.yml. Returns {} on missing/malformed file."""
```

```python
def resolve_style(styles_config: dict, style_name: str, field_name: str) -> dict:
    """
    Resolve {background, axis_color, cmap} from styles config.
    Pure function — no I/O. Safe to call with empty styles_config.
    """
```

### Modified functions

**`parse_shortcodes(text)`** — add `style` to optional kwargs, default `""`.

**`generate_html_figure(src_path, field, time_spec, output_path, fig_id, available_fields, camera_preview_only)`** — add three new keyword args:
```python
background: str = "transparent",
axis_color: str = "black",
cmap: str = "coolwarm",
```
Replace hardcoded `"#1a1a2e"` with `background` param, `"coolwarm"` with `cmap` param. Apply `axis_color` to scalar bar and axes via:
```python
scalar_bar_args={"title": field, "color": axis_color}
pl.add_axes(color=axis_color)
```
When `background == "transparent"`, pass `None` to `pl.background_color` (PyVista treats `None` as transparent/white for HTML export).

**`generate_png_figure(...)`** — same three new kwargs, same replacements. For PNG export, `transparent` background means passing `None` to `pl.background_color`.

**`main()`**:
1. Load `_4dpaper_styles.yml` once: `styles_config = load_styles(_project_root / "_4dpaper_styles.yml")`
2. For each `4d-image` shortcode, call `resolve_style(styles_config, fig["style"], fig["field"])` and pass the result into `generate_html_figure()` / `generate_png_figure()`
3. If `_4dpaper_styles.yml` exists, pass it as `extra_deps=[styles_yml_path]` to `is_cache_valid()` — editing styles triggers regeneration

---

## Cache Invalidation

`_4dpaper_styles.yml` mtime is added as an `extra_dep` on all `4d-image` figures when the file exists. Editing the styles file triggers regeneration of all figures that have a `style=` param (and only those, since others pass `extra_deps=[]`).

Actually, to keep it simple: if `_4dpaper_styles.yml` exists, pass it as an extra dep for ALL `4d-image` figures — even those without `style=`, since a change to `defaults:` could affect them. This is conservative but correct.

---

## New file: `_4dpaper_styles.yml`

A starter template committed to the repo:

```yaml
# 4Dpapers figure style templates
# Reference in shortcodes: {{< 4d-image style="vm-dark" ... >}}
#
# defaults: applied to all figures with no style= or missing field mapping
# styles:   named templates referenced via style="name"

defaults:
  background: "transparent"
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
```

---

## Testing

`tests/test_styles.py` covers:

1. **`load_styles`** — missing file returns `{}`, malformed YAML returns `{}` with warning, valid file parses correctly
2. **`resolve_style`** — per-field override wins, style-level fallback works, global defaults used when no style, unknown style name returns defaults
3. **`parse_shortcodes`** — `style=` param parsed correctly, defaults to `""` when absent
4. **`generate_html_figure`** — accepts `background`, `axis_color`, `cmap` params without error (use synthetic mesh)
5. **Cache invalidation** — touching `_4dpaper_styles.yml` triggers `is_cache_valid()` returning False for `4d-image` figures

---

## Out of Scope

- `4d-video`, `4d-panel`, `4d-pvsm` style support — next step after this lands
- Dashboard UI for style selection (autocomplete or popup) — separate feature
- Scalar range overrides (`vmin`, `vmax` per field) — future extension
- Per-figure style overrides of individual params (e.g., `cmap="viridis"` directly in shortcode overriding the template) — future extension
