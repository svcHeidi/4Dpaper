#!/usr/bin/env python3
"""Quarto post-render hook: sign rendered HTML outputs when configured."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_here = Path(__file__).resolve()
_app_root = _here.parent.parent.parent
_project_root = Path(
    os.environ.get("PROJECT_ROOT")
    or os.environ.get("QUARTO_PROJECT_DIR")
    or str(Path.cwd())
)

if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))

from dashboard.document_signing import sign_html_file_if_configured  # noqa: E402


def _output_dir() -> Path:
    return _project_root / "_output"


def main() -> int:
    output_dir = _output_dir()
    if not output_dir.exists():
        print(f"No output directory at {output_dir} — skipping HTML signing.", file=sys.stderr)
        return 0

    signed = 0
    for html_path in sorted(output_dir.rglob("*.html")):
        if sign_html_file_if_configured(html_path):
            signed += 1
            print(f"Signed rendered HTML: {html_path}", file=sys.stderr)

    if signed == 0:
        print("Rendered HTML signing disabled or no HTML outputs found.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
