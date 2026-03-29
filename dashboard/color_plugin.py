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
from pathlib import Path

import tornado.web

from dashboard.figure_state import (
    figure_state_path,
    is_safe_fig_id,
    merge_json_state,
    validate_colormap_payload,
)

_PROJECT_ROOT = Path(__file__).parent.parent


class ColorHandler(tornado.web.RequestHandler):
    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def options(self, fig_id: str) -> None:
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def post(self, fig_id: str) -> None:
        if not is_safe_fig_id(fig_id):
            self.set_status(400)
            self.write({"status": "error", "detail": "invalid fig_id"})
            return
        try:
            body = json.loads(self.request.body)
        except json.JSONDecodeError as exc:
            self.set_status(400)
            self.write({"status": "error", "detail": f"invalid JSON: {exc}"})
            return

        payload = validate_colormap_payload(body)
        color_path = figure_state_path(_PROJECT_ROOT, "color", fig_id)
        merge_json_state(color_path, payload)
        self.write({"status": "ok"})


ROUTES = [
    (r"/color/(?P<fig_id>[^/]+)", ColorHandler),
]
