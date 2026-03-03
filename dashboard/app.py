"""
4Dpaper Dashboard — main Panel app.

Launch with:
    panel serve dashboard/app.py --plugins dashboard.camera_plugin --static-dirs output=_output --show --port 5006
from the 4Dpapers repository root.

The --static-dirs flag makes _output/ available at /output/ so the
paper iframe can embed the rendered HTML at /output/analysis_report.html.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repo root is on sys.path so `dashboard.*` imports work when
# panel serve runs this file directly.
_repo_root = Path(__file__).parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import panel as pn

from dashboard.utils import load_config, load_manifest, resolve_param_paths
from dashboard.pages.run_page import build_run_page
from dashboard.pages.outputs_page import build_outputs_page
from dashboard.pages.paper_page import build_paper_page

pn.extension("codeeditor", sizing_mode="stretch_width", template="bootstrap")


def create_app():
    config = load_config()
    tutorials = config.get("tutorials", {})
    tutorial_keys = list(tutorials.keys())

    # ── Sidebar ──────────────────────────────────────────────────────────────
    tutorial_selector = pn.widgets.Select(
        name="Tutorial",
        options={v["display_name"]: k for k, v in tutorials.items()},
        sizing_mode="stretch_width",
    )
    last_run_status = pn.pane.Markdown("*No run yet.*")

    sidebar = pn.Column(
        pn.pane.Markdown("## 4Dpaper\n---"),
        pn.pane.Markdown("**Tutorial**"),
        tutorial_selector,
        pn.layout.Divider(),
        pn.pane.Markdown("**Last run**"),
        last_run_status,
        width=260,
    )

    # ── Pages (built lazily when tutorial changes) ────────────────────────────
    current_tutorial_key = tutorial_keys[0] if tutorial_keys else None

    run_col = pn.Column(sizing_mode="stretch_width")
    outputs_col = pn.Column(sizing_mode="stretch_width")
    paper_col = pn.Column(sizing_mode="stretch_width")

    def _load_tutorial(key: str):
        run_col.clear()
        run_col.append(build_run_page(key, config))

        tut_cfg = config["tutorials"][key]
        manifest_rel = tut_cfg.get("plots_manifest", "")
        cf_root = Path(config["cardiacfoam_root"])
        manifest_path = cf_root / manifest_rel
        manifest = load_manifest(manifest_path)

        outputs_col.clear()
        outputs_col.append(build_outputs_page(manifest))

        paper_col.clear()
        paper_col.append(build_paper_page(config))

    if current_tutorial_key:
        _load_tutorial(current_tutorial_key)

    def _on_tutorial_change(event):
        _load_tutorial(event.new)

    tutorial_selector.param.watch(_on_tutorial_change, "value")

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tabs = pn.Tabs(
        ("▶ Run", run_col),
        ("📊 Outputs", outputs_col),
        ("📄 Paper", paper_col),
        dynamic=True,
        sizing_mode="stretch_width",
    )

    # ── Root layout ───────────────────────────────────────────────────────────
    app = pn.Row(
        sidebar,
        pn.layout.VSpacer(width=16),
        tabs,
        sizing_mode="stretch_width",
    )
    return app


app = create_app()
app.servable()
