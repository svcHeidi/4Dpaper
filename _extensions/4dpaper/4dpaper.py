#!/usr/bin/env python3
"""
4DPaper pre-render hook — run by Quarto before rendering.

Scans the .qmd for {{< 4d-image >}} shortcodes and generates
figure files in state/figures/ (HTML for web, PNG for PDF).

Full implementation added in Task 2 and Task 3.
"""
import sys
print("[4dpaper] pre-render hook: stub (no figures generated yet)", file=sys.stderr)
