"""
Panel plugin: per-figure colormap state sync endpoint.

POST /color/<fig_id>
  Body:     {"fieldName": "colormapName", ...}
  Response: {"status": "ok"}

Saves to state/color_<fig_id>.json, merging with any existing state.
Add to panel serve with --plugins dashboard.plugins.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import tornado.web

_PROJECT_ROOT = Path(__file__).parent.parent
_SAFE_FIG_ID = re.compile(r'^[A-Za-z0-9_-]+$')

# Whitelist of accepted colormap names (matplotlib + common aliases)
_VALID_COLORMAPS = frozenset({
    "coolwarm", "viridis", "plasma", "inferno", "magma",
    "turbo", "jet", "hot", "bwr", "RdBu", "rainbow",
    "Blues", "Greens", "Reds", "Oranges", "Purples",
    "YlOrRd", "RdYlBu", "Spectral", "PiYG", "seismic",
    "cividis", "bone", "copper", "gray", "pink",
})


class ColorHandler(tornado.web.RequestHandler):
    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def options(self, fig_id: str) -> None:
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def post(self, fig_id: str) -> None:
        if not _SAFE_FIG_ID.fullmatch(fig_id):
            self.set_status(400)
            self.write({"status": "error", "detail": "invalid fig_id"})
            return
        try:
            body = json.loads(self.request.body)
        except json.JSONDecodeError as exc:
            self.set_status(400)
            self.write({"status": "error", "detail": f"invalid JSON: {exc}"})
            return

        # Validate: only accept known colormap names
        payload: dict[str, str] = {}
        for field_name, cmap_name in body.items():
            if not isinstance(field_name, str) or not isinstance(cmap_name, str):
                continue
            if cmap_name not in _VALID_COLORMAPS:
                continue
            payload[field_name] = cmap_name

        # Merge with existing state
        color_path = _PROJECT_ROOT / "state" / f"color_{fig_id}.json"
        if color_path.exists():
            try:
                existing = json.loads(color_path.read_text())
                existing.update(payload)
                payload = existing
            except json.JSONDecodeError:
                pass

        color_path.parent.mkdir(parents=True, exist_ok=True)
        color_path.write_text(json.dumps(payload, indent=2))
        self.write({"status": "ok"})


ROUTES = [
    (r"/color/(?P<fig_id>[^/]+)", ColorHandler),
]
