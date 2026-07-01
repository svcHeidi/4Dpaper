#!/usr/bin/env python3
"""Render 4DPaper shortcode assets before Quarto runs."""
from __future__ import annotations

import base64 as _b64
import json
import os
import re
import sys
from pathlib import Path

# Apply nest_asyncio early to allow trame's async server in non-Jupyter contexts
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

_here = Path(__file__).resolve().parent.parent
_project_root = Path(
    os.environ.get("PROJECT_ROOT")
    or os.environ.get("QUARTO_PROJECT_DIR")
    or str(_here.parent.parent)
)

def _resolve_app_root() -> Path | None:
    candidates = []
    for raw in (
        os.environ.get("FOURD_APP_ROOT"),
        str(_here.parent.parent),
        "/app",
    ):
        if raw and Path(raw).is_dir():
            candidates.append(Path(raw))
    for cand in candidates:
        if (cand / "dashboard").is_dir() and (cand / "scripts").is_dir():
            return cand
    return None

_app_root = _resolve_app_root()

import importlib.util as _ilu
_sr_spec = _ilu.spec_from_file_location("shortcut_resolver", _here / "shortcut_resolver.py")
_sr_mod = _ilu.module_from_spec(_sr_spec)
_sr_spec.loader.exec_module(_sr_mod)
ShortcutResolver = _sr_mod.ShortcutResolver

_shortcuts_yml_path = _project_root / "_shortcuts.yml"
_shortcut_resolver = ShortcutResolver(
    config_path=_shortcuts_yml_path,
    project_root=_project_root
)

_DECIMATE_TARGET_FACES = 150_000
