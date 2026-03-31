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
