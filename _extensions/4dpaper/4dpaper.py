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

def generate_html_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
) -> None:
    """Generate a self-contained vtk.js HTML figure using PyVista."""
    raise NotImplementedError("HTML figure generation: implemented in Task 3")


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> None:
    qmd_path = os.environ.get("QUARTO_DOCUMENT_PATH", "")
    output_format = os.environ.get("QUARTO_OUTPUT_FORMAT", "html")

    if not qmd_path or not Path(qmd_path).exists():
        print("[4dpaper] No QUARTO_DOCUMENT_PATH set — skipping.", file=sys.stderr)
        return

    text = Path(qmd_path).read_text()
    figures = parse_shortcodes(text)

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
            generate_html_figure(src, field, time_spec, out)

        elif output_format in ("pdf", "latex"):
            out = figures_dir / f"{fig_id}.png"
            if is_cache_valid(out, src):
                print(f"[4dpaper] {fig_id}.png is up to date — skipping.", file=sys.stderr)
                continue
            print(f"[4dpaper] PDF figures: run 'Export PDF' from the dashboard.", file=sys.stderr)


if __name__ == "__main__":
    main()
