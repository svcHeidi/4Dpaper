#!/usr/bin/env python3
"""
4DPaper pre-render hook — run by Quarto before rendering.

Scans the .qmd for {{< 4d-image >}} shortcodes and generates
figure files in state/figures/ (HTML for web, PNG for PDF).

Quarto calls this script before rendering. It reads QUARTO_DOCUMENT_PATH
and QUARTO_OUTPUT_FORMAT from the environment.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# ── Ensure venv Python is used ────────────────────────────────────────────────
_here = Path(__file__).resolve()
_project_root = _here.parent.parent.parent  # _extensions/4dpaper/ → project root
_venv_python = _project_root / ".venv" / "bin" / "python"
_under_pytest = "pytest" in sys.modules or any("pytest" in a for a in sys.argv)
if (
    _venv_python.exists()
    and not _under_pytest
    and Path(sys.executable).resolve() != _venv_python.resolve()
):
    os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

# Add project root to path for scripts/
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ── Shortcode parsing ─────────────────────────────────────────────────────────

def parse_shortcodes(text: str) -> list[dict]:
    """
    Parse {{< 4d-image key="value" ... >}} shortcodes from QMD text.

    Returns a list of dicts with at minimum 'id', 'src', 'field' keys.
    Shortcodes missing 'id' or 'src' are silently skipped.
    'time' defaults to 'mid' if not specified.
    """
    # Strip fenced code blocks (``` ... ```) before scanning for shortcodes
    # so that shortcodes shown as examples in code blocks are not processed.
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)

    pattern = r'\{\{<\s*4d-image\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)=["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("time", "mid")
        kwargs.setdefault("field", "")
        results.append(kwargs)
    return results


# ── Cache helpers ─────────────────────────────────────────────────────────────

def is_cache_valid(fig_path: Path, src_path: Path) -> bool:
    """
    Return True if fig_path exists and is newer than src_path.
    Returns True (assume valid) if src_path does not exist.
    """
    if not fig_path.exists():
        return False
    if not src_path.exists():
        return True
    return fig_path.stat().st_mtime > src_path.stat().st_mtime


# ── Figure generation (Task 3) ────────────────────────────────────────────────

def generate_png_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
) -> None:
    """
    Generate a static PNG figure using PyVista (default camera angle).

    Used as a fallback for PDF export when no pvpython camera state exists.
    """
    import pyvista as pv
    from scripts.data_loader import SimulationData

    sim = SimulationData(str(src_path)).load()

    if sim.n_steps == 0:
        raise RuntimeError(
            f"[4dpaper] Simulation at {src_path} has no time steps."
        )

    n = sim.n_steps
    if time_spec == "first":
        idx = 0
    elif time_spec == "last":
        idx = max(0, n - 1)
    else:
        try:
            idx = max(0, min(int(time_spec), n - 1))
        except ValueError:
            idx = n // 2

    mesh = sim.get_mesh(idx)
    if mesh is None:
        raise RuntimeError(f"[4dpaper] Could not load mesh at step {idx} from {src_path}")

    surface = mesh.extract_surface()

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
    else:
        pl.add_mesh(surface, color="#aaaaaa", opacity=0.9)
        print(
            f"[4dpaper] Warning: field '{field}' not found — rendering geometry only.",
            file=sys.stderr,
        )

    pl.isometric_view()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(output_path))
    pl.close()
    print(f"[4dpaper] Generated (PNG): {output_path}", file=sys.stderr)


def generate_html_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
) -> None:
    """
    Generate a self-contained vtk.js HTML figure using PyVista.

    Uses PyVista's Plotter.export_html() which produces a standalone
    file powered by panel + trame — no server required to view.
    """
    import pyvista as pv
    from scripts.data_loader import SimulationData

    sim = SimulationData(str(src_path)).load()

    if sim.n_steps == 0:
        raise RuntimeError(
            f"[4dpaper] Simulation at {src_path} has no time steps. "
            "Ensure the case has been solved and time directories exist."
        )

    # Resolve time step index
    n = sim.n_steps
    if time_spec == "first":
        idx = 0
    elif time_spec == "last":
        idx = max(0, n - 1)
    else:  # "mid" or numeric string
        try:
            idx = max(0, min(int(time_spec), n - 1))
        except ValueError:
            idx = n // 2

    mesh = sim.get_mesh(idx)
    if mesh is None:
        raise RuntimeError(f"[4dpaper] Could not load mesh at step {idx} from {src_path}")

    surface = mesh.extract_surface()

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
    else:
        pl.add_mesh(surface, color="#aaaaaa", opacity=0.9)
        print(
            f"[4dpaper] Warning: field '{field}' not found in mesh — rendering geometry only.",
            file=sys.stderr,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.export_html(str(output_path))
    pl.close()

    # Patch viewport units so the widget has a fixed height when embedded inline.
    # PyVista's trame output uses 100vw/100vh which fills the whole page.
    html = output_path.read_text()
    html = html.replace("100vw", "900px").replace("100vh", "600px")
    output_path.write_text(html)

    print(f"[4dpaper] Generated: {output_path}", file=sys.stderr)


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> None:
    if os.environ.get("QUARTO_NO_EXECUTE"):
        print("[4dpaper] --no-execute mode: skipping figure generation.", file=sys.stderr)
        return

    qmd_path = os.environ.get("QUARTO_DOCUMENT_PATH", "")
    output_format = os.environ.get("QUARTO_OUTPUT_FORMAT", "html")

    # QUARTO_DOCUMENT_PATH is not always set for project-level pre-render hooks.
    # Fall back to scanning all .qmd files in QUARTO_PROJECT_DIR (or project root).
    if qmd_path and Path(qmd_path).exists():
        qmd_files = [Path(qmd_path)]
    else:
        project_dir = Path(os.environ.get("QUARTO_PROJECT_DIR", str(_project_root)))
        qmd_files = sorted(project_dir.glob("*.qmd"))
        if not qmd_files:
            print("[4dpaper] No .qmd files found — skipping.", file=sys.stderr)
            return
        print(f"[4dpaper] Scanning {len(qmd_files)} QMD file(s) in {project_dir}", file=sys.stderr)

    figures = []
    for qmd in qmd_files:
        figures.extend(parse_shortcodes(qmd.read_text()))

    if not figures:
        print("[4dpaper] No 4d-image shortcodes found.", file=sys.stderr)
        return

    figures_dir = _project_root / "state" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    for fig in figures:
        fig_id = fig["id"]
        src = Path(fig["src"]) if Path(fig["src"]).is_absolute() else _project_root / fig["src"]
        field = fig["field"]
        time_spec = fig.get("time", "mid")

        if output_format in ("html", "html4", "html5"):
            out = figures_dir / f"{fig_id}.html"
            if is_cache_valid(out, src):
                print(f"[4dpaper] {fig_id}.html is up to date — skipping.", file=sys.stderr)
                continue
            print(f"[4dpaper] Generating {fig_id}.html …", file=sys.stderr)
            try:
                generate_html_figure(src, field, time_spec, out)
            except Exception as exc:
                print(
                    f"[4dpaper] ERROR generating {fig_id}.html: {exc}",
                    file=sys.stderr,
                )
                sys.exit(1)

        elif output_format in ("pdf", "latex"):
            out = figures_dir / f"{fig_id}.png"
            if is_cache_valid(out, src):
                print(f"[4dpaper] {fig_id}.png is up to date — skipping.", file=sys.stderr)
                continue
            print(f"[4dpaper] Generating {fig_id}.png (default camera) …", file=sys.stderr)
            try:
                generate_png_figure(src, field, time_spec, out)
            except Exception as exc:
                print(
                    f"[4dpaper] ERROR generating {fig_id}.png: {exc}",
                    file=sys.stderr,
                )
                sys.exit(1)


if __name__ == "__main__":
    main()
