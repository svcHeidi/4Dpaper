"""
Panel plugin: per-figure colormap preview-state sync endpoint.

POST /color/<fig_id>
  Body:     {"fieldName": "colormapName", ...}
  Response: {"status": "ok"}

Saves to state/preview/color_<fig_id>.json, merging with any existing state.
This is preview-only dashboard state, not authored render configuration.
"""
from __future__ import annotations

import json
from pathlib import Path

import os

import tornado.web

from dashboard.auth import SecureMixin
from dashboard.figure_state import (
    is_safe_fig_id,
    merge_preview_state,
    preview_state_path,
    validate_colormap_payload,
)

# PROJECT_ROOT can be set via environment variable (for Docker) or defaults to parent directory
_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))


class ColorHandler(SecureMixin, tornado.web.RequestHandler):
    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="POST, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self, fig_id: str) -> None:
        self.finish()

    def post(self, fig_id: str) -> None:
        if not self.check_auth():
            return
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
        color_path = preview_state_path(_PROJECT_ROOT, "color", fig_id)
        merge_preview_state(color_path, payload)
        self.write({"status": "ok"})


ROUTES = [
    (r"/color/(?P<fig_id>[^/]+)", ColorHandler),
]
