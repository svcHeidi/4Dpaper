"""
Panel plugin: per-figure camera state sync endpoint.

Add to panel serve with:
    panel serve dashboard/app.py --plugins dashboard.camera_plugin ...

Panel reads the ROUTES list and registers the handlers with Tornado.
The srcdoc iframe has a null origin, so CORS headers allow all origins.
"""
from __future__ import annotations

import json
from pathlib import Path

import tornado.web

from dashboard.utils import save_camera_state

_PROJECT_ROOT = Path(__file__).parent.parent


class CameraHandler(tornado.web.RequestHandler):
    def set_default_headers(self) -> None:
        # srcdoc iframes have a null origin — allow all for local-only server
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def options(self, fig_id: str) -> None:
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def post(self, fig_id: str) -> None:
        body = json.loads(self.request.body)
        cam_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}.json"
        save_camera_state(
            position=body["position"],
            focal_point=body["focal_point"],
            view_up=body["view_up"],
            parallel_scale=body.get("parallel_scale"),
            output_path=cam_path,
        )
        self.write({"status": "ok"})


ROUTES = [
    (r"/camera/(?P<fig_id>[^/]+)", CameraHandler),
]
