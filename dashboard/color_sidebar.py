"""
Color-template sidebar for the 4Dpapers dashboard.

Parses the QMD for {{< 4d-image >}} shortcodes and renders a compact
colormap selector for every (figure, field) pair.

- Gradient preview bar updates immediately when a colormap is chosen.
- Selection is persisted via POST /color/<fig_id> as preview-only dashboard
  state (no page rebuild needed).
- Selection does not rewrite checked-in figure/render config.
"""
from __future__ import annotations

import json
from pathlib import Path

import panel as pn

from dashboard.figure_state import (
    load_json_state,
    parse_4d_image_figures,
    preview_state_path,
)

_PROJECT_ROOT = Path(__file__).parent.parent

# ── Curated colormap catalogue ───────────────────────────────────────────────
# Each entry: human label + CSS gradient for the preview strip.
COLORMAPS: dict[str, dict[str, str]] = {
    "coolwarm": {
        "label": "Cool Warm",
        "gradient": "linear-gradient(to right,#3b4cc0,#7b9dd9,#f7f7f7,#e0604e,#b40426)",
    },
    "viridis": {
        "label": "Viridis",
        "gradient": "linear-gradient(to right,#440154,#31688e,#35b779,#fde725)",
    },
    "plasma": {
        "label": "Plasma",
        "gradient": "linear-gradient(to right,#0d0887,#7e03a8,#cc4778,#f89540,#f0f921)",
    },
    "inferno": {
        "label": "Inferno",
        "gradient": "linear-gradient(to right,#000004,#56106e,#bb3754,#f98e09,#fcffa4)",
    },
    "magma": {
        "label": "Magma",
        "gradient": "linear-gradient(to right,#000004,#3b0f70,#8c2981,#de4968,#fcfdbf)",
    },
    "turbo": {
        "label": "Turbo",
        "gradient": "linear-gradient(to right,#30123b,#4875cb,#1bd0cd,#a1fc3d,#fbb318,#d93806,#7a0403)",
    },
    "RdBu": {
        "label": "Red-Blue",
        "gradient": "linear-gradient(to right,#b2182b,#ef8a62,#fddbc7,#f7f7f7,#d1e5f0,#67a9cf,#2166ac)",
    },
    "RdYlBu": {
        "label": "Red-Yellow-Blue",
        "gradient": "linear-gradient(to right,#d73027,#fc8d59,#fee090,#ffffbf,#e0f3f8,#91bfdb,#4575b4)",
    },
    "seismic": {
        "label": "Seismic",
        "gradient": "linear-gradient(to right,#00004d,#0000ff,#ffffff,#ff0000,#4d0000)",
    },
    "hot": {
        "label": "Hot",
        "gradient": "linear-gradient(to right,#000000,#ff0000,#ffff00,#ffffff)",
    },
    "jet": {
        "label": "Jet",
        "gradient": "linear-gradient(to right,#000080,#0000ff,#00ffff,#00ff00,#ffff00,#ff0000,#800000)",
    },
    "rainbow": {
        "label": "Rainbow",
        "gradient": "linear-gradient(to right,#ff0000,#ff8000,#ffff00,#00ff00,#0000ff,#8000ff)",
    },
}

_DEFAULT_CMAP = "coolwarm"


def _load_color_state(fig_id: str) -> dict[str, str]:
    return load_json_state(preview_state_path(_PROJECT_ROOT, "color", fig_id))


# ── HTML builder ─────────────────────────────────────────────────────────────

def _options_html(current_cmap: str) -> str:
    parts = []
    for key, info in COLORMAPS.items():
        sel = " selected" if key == current_cmap else ""
        parts.append(f'<option value="{key}"{sel}>{info["label"]}</option>')
    return "\n".join(parts)


def _build_html(qmd_path: Path) -> str:
    figures = parse_4d_image_figures(qmd_path)

    if not figures:
        return (
            '<div style="padding:12px 8px;font-family:monospace;color:#555;font-size:11px;">'
            'No <code>4d-image</code> shortcodes found.<br>'
            'Restart the dashboard after adding figures.'
            '</div>'
        )

    # ── gradient JS map (plain string — no f-string brace escaping needed) ──
    grad_entries = [
        f'"{k}":{json.dumps(v["gradient"])}' for k, v in COLORMAPS.items()
    ]
    gradients_js = "{" + ",".join(grad_entries) + "}"

    # ── per-figure rows ──────────────────────────────────────────────────────
    fig_blocks: list[str] = []
    for fig in figures:
        fig_id = fig["id"]
        color_state = _load_color_state(fig_id)
        field_rows: list[str] = []

        for field in fig["fields"]:
            cmap = color_state.get(field, _DEFAULT_CMAP)
            grad_css = COLORMAPS.get(cmap, COLORMAPS[_DEFAULT_CMAP])["gradient"]
            elem_grad = f"cgrad-{fig_id}-{field}"
            elem_sel = f"csel-{fig_id}-{field}"
            field_rows.append(
                f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:5px;">'
                f'<span title="{field}" style="color:#999;font-size:10px;min-width:72px;'
                f'max-width:72px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                f'{field}</span>'
                f'<div style="flex:1;display:flex;flex-direction:column;gap:2px;">'
                f'<div id="{elem_grad}"'
                f' style="height:7px;border-radius:2px;background:{grad_css};"></div>'
                f'<select id="{elem_sel}"'
                f' data-fig="{fig_id}" data-field="{field}"'
                f' onchange="cmapChange(this)"'
                f' style="background:#222;color:#ddd;border:1px solid #383838;'
                f'border-radius:3px;font-size:10px;padding:1px 3px;width:100%;cursor:pointer;">'
                f'{_options_html(cmap)}'
                f'</select>'
                f'</div>'
                f'</div>'
            )

        fig_blocks.append(
            f'<div style="margin-bottom:14px;">'
            f'<div style="color:#ffffff;font-size:10px;font-weight:bold;padding:2px 5px;'
            f'background:#2a2a2a;border-radius:3px;margin-bottom:6px;'
            f'border-left:2px solid #4a9c6d;">{fig_id}</div>'
            + "".join(field_rows)
            + "</div>"
        )

    rows_html = "".join(fig_blocks)

    # ── JS (plain string to avoid brace-escaping in f-strings) ───────────────
    js = """
(function() {
  var G = GRADIENTS_PLACEHOLDER;
  var _t = {};
  window.cmapChange = function(sel) {
    var figId = sel.getAttribute('data-fig');
    var field = sel.getAttribute('data-field');
    var cmap  = sel.value;
    var grad  = document.getElementById('cgrad-' + figId + '-' + field);
    if (grad && G[cmap]) grad.style.background = G[cmap];
    var key = figId + '/' + field;
    clearTimeout(_t[key]);
    _t[key] = setTimeout(function() {
      var body = {};
      body[field] = cmap;
      fetch('/color/' + figId, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
      }).catch(function() {});
    }, 300);
  };
})();
""".replace("GRADIENTS_PLACEHOLDER", gradients_js)

    return (
        '<div style="padding:8px 6px;font-family:monospace;overflow-y:auto;">'
        '<div style="color:#888;font-size:10px;margin-bottom:10px;line-height:1.5;">'
        'Pick a colormap per field.<br>'
        'Click <b style="color:#ccc;">Rebuild HTML</b> to apply.'
        '</div>'
        + rows_html
        + "</div>"
        + f"<script>{js}</script>"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def build_color_sidebar(qmd_path: Path) -> pn.pane.HTML:
    """Return a Panel HTML pane containing the colormap selector UI."""
    return pn.pane.HTML(
        _build_html(qmd_path),
        sizing_mode="stretch_width",
        styles={"background": "transparent", "border-radius": "4px"},
    )
