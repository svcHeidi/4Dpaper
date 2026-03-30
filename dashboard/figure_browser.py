"""
Figure browser sidebar for the 4Dpapers dashboard.

Provides a fixed-width left sidebar with:
  - Panel FileSelector filtered to .foam files (system-file-browser feel)
  - Figure settings (field, fig-id, time, caption)
  - Optional copy of case data into project data/
  - Insert-at-end button that appends the shortcode to the QMD editor
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import panel as pn

from dashboard.theme import THEME


# ── Filesystem helpers ────────────────────────────────────────────────────────

def find_foam_files(directory: Path) -> list[Path]:
    """Return .foam files found recursively in *directory*, sorted."""
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(directory.rglob("*.foam"))


def get_timesteps(case_root: Path) -> list[str]:
    """
    Discover numeric time-step directory names inside an OpenFOAM case.

    Checks ``processor0/`` first (parallel), then *case_root* (serial).
    Returns a float-sorted list, e.g. ``["0.005", "0.01", …]``.
    """
    search_root = case_root / "processor0"
    if not search_root.exists():
        search_root = case_root

    timesteps: list[str] = []
    if search_root.is_dir():
        for d in search_root.iterdir():
            if d.is_dir():
                try:
                    float(d.name)
                    timesteps.append(d.name)
                except ValueError:
                    pass
    return sorted(timesteps, key=float)


def copy_case_data(foam_path: Path, dest_data_dir: Path, log_lines: list[str]) -> Path:
    """
    Copy the minimal OpenFOAM case files required for PyVista rendering into
    *dest_data_dir*/<case_name>/.

    Copies:
    - The .foam marker file
    - constant/polyMesh/
    - processor*/constant/polyMesh/
    - processor*/<timestep>/  (all timesteps)

    Returns the path to the new .foam marker file.
    """
    case_root = foam_path.parent
    case_name = case_root.name
    dest_case = dest_data_dir / case_name
    dest_case.mkdir(parents=True, exist_ok=True)

    dest_foam = dest_case / foam_path.name
    shutil.copy2(foam_path, dest_foam)
    log_lines.append(f"  Copied {foam_path.name}")

    serial_mesh = case_root / "constant" / "polyMesh"
    if serial_mesh.exists():
        dst = dest_case / "constant" / "polyMesh"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(serial_mesh, dst)
        log_lines.append("  Copied constant/polyMesh/")

    for proc_dir in sorted(case_root.glob("processor*")):
        if not proc_dir.is_dir():
            continue
        dest_proc = dest_case / proc_dir.name
        dest_proc.mkdir(exist_ok=True)

        proc_mesh = proc_dir / "constant" / "polyMesh"
        if proc_mesh.exists():
            dst = dest_proc / "constant" / "polyMesh"
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(proc_mesh, dst)

        for item in proc_dir.iterdir():
            if item.is_dir():
                try:
                    float(item.name)
                    dst = dest_proc / item.name
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(item, dst)
                except ValueError:
                    pass

        log_lines.append(f"  Copied {proc_dir.name}/")

    return dest_foam


# ── Shortcode generator ───────────────────────────────────────────────────────

def generate_shortcode(
    *,
    src: str,
    field: str,
    fig_id: str,
    time: str,
    caption: str,
) -> str:
    """Return a ``{{< 4d-image … >}}`` shortcode string."""
    parts = [f'src="{src}"', f'field="{field}"', f'id="{fig_id}"']
    if time and time != "mid":
        parts.append(f'time="{time}"')
    if caption.strip():
        parts.append(f'caption="{caption.strip()}"')
    return "{{< 4d-image " + " ".join(parts) + " >}}"


# ── Panel sidebar widget ──────────────────────────────────────────────────────

# Total sidebar column width in pixels.
_W = 360
# Inner widget width: sidebar minus 2×10 px padding.
_IW = _W - 20

_SIDEBAR_STYLES = {
    "background": THEME["bg_sidebar"],
    "border-right": f"1px solid {THEME['border_subtle']}",
    "padding": "10px",
    "overflow-x": "hidden",
    "overflow-y": "auto",
    "box-sizing": "border-box",
}


def build_figure_insert_form(
    editor: pn.widgets.CodeEditor,
    qmd_path: Path,
    config: dict[str, Any],
) -> pn.Column:
    """
    Build the figure-insertion form for browsing .foam files and inserting
    4d-image shortcodes into the QMD editor.

    Returns a plain Column (no fixed width/styles) — the caller decides how
    to present it (e.g. as a toggle panel or modal).
    """
    project_root = qmd_path.parent
    cf_root_str = config.get("cardiacfoam_root", str(Path.home()))

    root_select = pn.widgets.RadioButtonGroup(
        name="Root",
        options=["Cases", "Project"],
        value="Cases",
        button_type="default",
        width=_IW,
    )

    file_selector = pn.widgets.FileSelector(
        directory=cf_root_str,
        file_pattern="*.foam",
        width=_IW,
        height=300,
    )

    def _on_root_change(event):
        directory = cf_root_str if event.new == "Cases" else str(project_root)
        file_selector.directory = directory

    root_select.param.watch(_on_root_change, "value")

    # ── Figure settings ───────────────────────────────────────────────────────
    # Explicit width on every widget instead of sizing_mode="stretch_width" so
    # Bokeh's layout engine doesn't miscompute the sidebar width.
    field_input = pn.widgets.TextInput(
        name="Field",
        value="Vm",
        placeholder="e.g. Vm, activationTime",
        width=_IW,
    )
    fig_id_input = pn.widgets.TextInput(
        name="Figure ID",
        value="fig-vm",
        placeholder="e.g. fig-vm",
        width=_IW,
    )
    time_select = pn.widgets.Select(
        name="Time",
        options=["mid", "last"],
        value="mid",
        width=_IW,
    )
    caption_input = pn.widgets.TextInput(
        name="Caption",
        value="",
        placeholder="Optional caption…",
        width=_IW,
    )

    def _on_field_change(event):
        slug = event.new.lower().replace(" ", "_")
        fig_id_input.value = f"fig-{slug}"

    field_input.param.watch(_on_field_change, "value")

    def _on_foam_selected(event):
        paths = event.new
        if not paths:
            return
        foam = Path(paths[0])
        timesteps = get_timesteps(foam.parent)
        time_select.options = ["mid", "last"] + timesteps

    file_selector.param.watch(_on_foam_selected, "value")

    # ── Copy-case option ──────────────────────────────────────────────────────
    copy_toggle = pn.widgets.Checkbox(
        name="Copy case data into project  (data/<case>/)",
        value=False,
        width=_IW,
    )
    copy_log_pane = pn.pane.Str(
        "",
        styles={
            "font-size": "10px",
            "color": THEME["text_muted"],
            "white-space": "pre",
            "max-height": "60px",
            "overflow-y": "auto",
        },
        width=_IW,
        visible=False,
    )

    copy_toggle.param.watch(lambda e: setattr(copy_log_pane, "visible", e.new), "value")

    # ── Shortcode preview ─────────────────────────────────────────────────────
    shortcode_preview = pn.widgets.TextAreaInput(
        name="Shortcode",
        value="",
        rows=2,
        width=_IW,
        disabled=True,
    )

    def _refresh_preview(*_args):
        paths = file_selector.value
        src = paths[0] if paths else ""
        if copy_toggle.value and src:
            foam = Path(src)
            src = f"data/{foam.parent.name}/{foam.name}"
        shortcode_preview.value = generate_shortcode(
            src=src,
            field=field_input.value,
            fig_id=fig_id_input.value,
            time=time_select.value,
            caption=caption_input.value,
        )

    for w in (file_selector, field_input, fig_id_input, time_select, caption_input, copy_toggle):
        w.param.watch(lambda _e: _refresh_preview(), "value")

    _refresh_preview()

    # ── Insert button ─────────────────────────────────────────────────────────
    insert_btn = pn.widgets.Button(
        name="Insert at end of QMD",
        button_type="success",
        width=_IW,
    )
    insert_status = pn.pane.Alert(
        "", alert_type="info", visible=False, width=_IW,
    )

    def _on_insert(_event):
        paths = file_selector.value
        if not paths:
            insert_status.object = "Select a .foam file first."
            insert_status.alert_type = "warning"
            insert_status.visible = True
            return

        log_msgs: list[str] = []
        src = paths[0]

        if copy_toggle.value:
            try:
                foam = Path(src)
                data_dir = project_root / "data"
                data_dir.mkdir(exist_ok=True)
                copy_case_data(foam, data_dir, log_msgs)
                copy_log_pane.object = "\n".join(log_msgs)
                src = f"data/{foam.parent.name}/{foam.name}"
            except Exception as exc:
                insert_status.object = f"✗ Copy failed: {exc}"
                insert_status.alert_type = "danger"
                insert_status.visible = True
                return

        shortcode = generate_shortcode(
            src=src,
            field=field_input.value,
            fig_id=fig_id_input.value,
            time=time_select.value,
            caption=caption_input.value,
        )
        shortcode_preview.value = shortcode

        current = editor.value or ""
        if current and not current.endswith("\n"):
            current += "\n"
        editor.value = current + "\n" + shortcode + "\n"

        insert_status.object = f"✓ Inserted `{fig_id_input.value}` — remember to Save."
        insert_status.alert_type = "success"
        insert_status.visible = True

    insert_btn.on_click(_on_insert)

    # ── Form layout ───────────────────────────────────────────────────────────
    return pn.Column(
        pn.pane.Markdown(
            "### Insert Figure",
            styles={"color": THEME["text_primary"]},
        ),
        root_select,
        file_selector,
        pn.layout.Divider(margin=(6, 0)),
        field_input,
        fig_id_input,
        time_select,
        caption_input,
        pn.layout.Divider(margin=(6, 0)),
        copy_toggle,
        copy_log_pane,
        shortcode_preview,
        insert_btn,
        insert_status,
    )
