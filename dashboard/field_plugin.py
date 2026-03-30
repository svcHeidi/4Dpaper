"""Panel plugin: preview-only per-figure field and timestep state sync endpoint."""
from __future__ import annotations

import json
from pathlib import Path

import tornado.web

from dashboard.figure_state import (
    is_safe_fig_id,
    merge_preview_state,
    preview_state_path,
    validate_field_payload,
)

_PROJECT_ROOT = Path(__file__).parent.parent


class FieldHandler(tornado.web.RequestHandler):
    def set_default_headers(self) -> None:
        # srcdoc iframes have a null origin — allow all for local-only server
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

        state_path = preview_state_path(_PROJECT_ROOT, "field", fig_id)
        payload = validate_field_payload(body)
        merge_preview_state(state_path, payload)
        self.write({"status": "ok"})


ROUTES = [
    (r"/field/(?P<fig_id>[^/]+)", FieldHandler),
]
