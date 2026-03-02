"""Outputs tab: grid of artifacts from plots.json."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import panel as pn


def build_outputs_page(
    manifest: dict[str, Any] | None,
    *,
    output_dir: Path | None = None,
) -> pn.Column:
    if manifest is None:
        return pn.Column(
            pn.pane.Alert(
                "No outputs yet. Run post-processing from the **Run** tab first.",
                alert_type="info",
            )
        )

    artifacts = manifest.get("artifacts", [])
    generated_at = manifest.get("generated_at_utc", "unknown")
    base_dir = Path(manifest.get("output_dir", "."))

    cards = []
    for artifact in artifacts:
        label = artifact.get("label", artifact.get("path", "output"))
        fmt = artifact.get("format", "").lower()
        rel_path = artifact.get("path", "")
        abs_path = base_dir / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)

        if fmt == "html" and abs_path.exists():
            pane = pn.pane.HTML(
                f'<iframe src="file://{abs_path}" width="100%" height="450px" '
                f'style="border:none;border-radius:4px;"></iframe>',
                sizing_mode="stretch_width",
            )
        elif fmt in ("png", "jpg", "jpeg", "svg") and abs_path.exists():
            pane = pn.pane.Image(str(abs_path), sizing_mode="stretch_width")
        elif fmt == "csv" and abs_path.exists():
            import pandas as pd
            df = pd.read_csv(abs_path)
            pane = pn.widgets.Tabulator(df, pagination="local", page_size=10,
                                        sizing_mode="stretch_width")
        else:
            pane = pn.pane.Alert(
                f"File not found or unsupported format: `{abs_path}`",
                alert_type="warning",
            )

        cards.append(
            pn.Card(
                pane,
                title=label,
                collapsible=True,
                sizing_mode="stretch_width",
            )
        )

    return pn.Column(
        pn.pane.Markdown(f"**Generated:** {generated_at}  |  **{len(artifacts)} artifact(s)**"),
        pn.layout.Divider(),
        *cards,
        sizing_mode="stretch_width",
    )
