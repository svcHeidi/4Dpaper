#!/usr/bin/env python3
"""Quarto post-render hook: inject standalone HTML figures directly into the output."""
from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path

_here = Path(__file__).resolve()
_project_root = Path(
    os.environ.get("PROJECT_ROOT")
    or os.environ.get("QUARTO_PROJECT_DIR")
    or str(Path.cwd())
)

INJECT_PATTERN = re.compile(r'data-fourd-inject="([^"]+)"')

def _output_dir() -> Path:
    return _project_root / "_output"


def main() -> int:
    # Only run if FOURD_APP_MODE is not 1 (meaning we are exporting standalone)
    if os.environ.get("FOURD_APP_MODE") == "1":
        return 0

    output_dir = _output_dir()
    if not output_dir.exists():
        print(f"No output directory at {output_dir} — skipping figure injection.", file=sys.stderr)
        return 0

    injected_count = 0

    for html_path in sorted(output_dir.rglob("*.html")):
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Find all placeholders
            matches = INJECT_PATTERN.findall(content)
            if not matches:
                continue

            print(f"Injecting {len(matches)} 4D figures into {html_path.name}...", file=sys.stderr)
            
            def repl(m: re.Match) -> str:
                fig_path_rel = m.group(1)
                fig_path_abs = _project_root / fig_path_rel

                if not fig_path_abs.exists():
                    print(f"  Warning: Figure not found at {fig_path_abs}", file=sys.stderr)
                    return 'data-fourd-inject-failed="true"'

                # Inline the (already self-contained) figure HTML directly into the
                # iframe as `srcdoc` so the exported document is a single portable
                # file. Referencing a copied sibling file instead would break the
                # moment the HTML is moved or shared on its own.
                with open(fig_path_abs, "r", encoding="utf-8") as fig_f:
                    fig_html = fig_f.read()

                return 'srcdoc="' + html.escape(fig_html, quote=True) + '"'

            new_content = INJECT_PATTERN.sub(repl, content)

            with open(html_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            injected_count += 1
            
        except Exception as e:
            print(f"Error injecting figures into {html_path}: {e}", file=sys.stderr)

    if injected_count > 0:
        print(f"Successfully injected figures into {injected_count} HTML file(s).", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
