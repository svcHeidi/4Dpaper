#!/usr/bin/env python3
"""Render preview artifacts for one uploaded case.

Invoked as a subprocess by dashboard/upload_plugin.py on figure upload, so the
figure-generation code runs in the same execution mode it is proven in (a
fresh process, like the Quarto pre-render hook) rather than inside the
dashboard's live Tornado event loop.

On success the final stdout line is a JSON status object:
    {"status": "ok", "field": "<field>", "fields": ["a", "b", ...]}
Any exception prints to stderr and exits non-zero. The normal upload path
creates HTML and PNG; Quick Export passes ``--html-only`` because its temporary
workspace only needs the interactive figure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

# App root resolved relative to this file: correct both in the repo layout and
# in Docker, where scripts/ and _extensions/ are baked into /app while
# PROJECT_ROOT=/workspace.
_APP_ROOT = Path(__file__).resolve().parent.parent


def _select_field(field_arg: str, fields: list[str]) -> str:
    """Explicit --field wins; else first available field; else empty."""
    if field_arg:
        return field_arg
    if fields:
        return fields[0]
    return ""


def _fields_at_step(sim, idx: int) -> list[str]:
    """Field names on the mesh at the rendered timestep.

    Not SimulationData.fields, which reads step 0: OpenFOAM cases often carry
    setup fields (conductivity, fiber, ...) only at time 0 while the solved
    fields (Vm, ...) live in later time dirs — detecting at step 0 would pick
    a field that does not exist in the rendered mesh.
    """
    mesh = sim.get_mesh(idx)
    if mesh is None:
        return []
    return sorted(set(list(mesh.point_data.keys()) + list(mesh.cell_data.keys())))


def _resolve_project_root() -> Path:
    return Path(
        os.environ.get("PROJECT_ROOT")
        or os.environ.get("QUARTO_PROJECT_DIR")
        or str(_APP_ROOT)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="Path to the data source file")
    parser.add_argument("--fig-id", required=True, help="Figure identifier")
    parser.add_argument("--decimate", default="auto", help="auto|none|<float-ratio>")
    parser.add_argument("--field", default="", help="Scalar field override")
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Generate the interactive HTML figure without a PNG companion",
    )
    args = parser.parse_args(argv)

    # lib.* lives under _extensions/4dpaper; lib.utils imports
    # dashboard.document_signing and lib.render imports scripts.data_loader,
    # both resolved from the app root. A fresh subprocess has neither on
    # sys.path.
    for path in (_APP_ROOT / "_extensions" / "4dpaper", _APP_ROOT):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    project_root = _resolve_project_root()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from lib.render import _get_simulation, generate_html_figure, generate_png_figure

    # Absolute path required: SimulationData's decomposed-case staging
    # symlinks the raw path string, so a relative --case produces dangling
    # symlinks in the temp staging dirs.
    case = Path(args.case).resolve()
    # _get_simulation shares its cache with the generate_*_figure calls below,
    # so the case is loaded exactly once.
    sim = _get_simulation(case)
    # Same index "mid" resolves to in the generators; the mesh loaded here is
    # cached inside sim, so the generators reuse it.
    mid_idx = sim.n_steps // 2
    fields = _fields_at_step(sim, mid_idx)
    field = _select_field(args.field, fields)

    output_dir = project_root / "state" / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    generate_html_figure(
        src_path=case,
        field=field,
        time_spec="mid",
        output_path=output_dir / f"{args.fig_id}.html",
        fig_id=args.fig_id,
        available_fields=fields,
        decimate=args.decimate,
    )
    if not args.html_only:
        generate_png_figure(
            src_path=case,
            field=field,
            time_spec="mid",
            output_path=output_dir / f"{args.fig_id}.png",
            fig_id=args.fig_id,
            decimate=args.decimate,
        )

    print(json.dumps({"status": "ok", "field": field, "fields": fields}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
