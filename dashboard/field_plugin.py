"""Per-figure field and timestep state endpoint."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import tornado.web

_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))
_SAFE_FIG_ID = re.compile(r'^[A-Za-z0-9_-]+$')


class FieldHandler(tornado.web.RequestHandler):
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

        cam_path = _PROJECT_ROOT / "state" / f"field_{fig_id}.json"

        payload: dict = {}
        if "field" in body:
            payload["field"] = str(body["field"])
        if "time" in body:
            payload["time"] = str(body["time"])

        if cam_path.exists():
            try:
                existing = json.loads(cam_path.read_text())
                existing.update(payload)
                payload = existing
            except json.JSONDecodeError:
                pass

        cam_path.parent.mkdir(parents=True, exist_ok=True)
        cam_path.write_text(json.dumps(payload, indent=2))

        self.write({"status": "ok"})


ROUTES = [
    (r"/field/(?P<fig_id>[^/]+)", FieldHandler),
]
