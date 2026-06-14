"""Per-figure camera state and lock endpoints."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import tornado.web

from dashboard.auth import SecureMixin
from dashboard.utils import save_camera_state

_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))
_SAFE_FIG_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class CameraHandler(SecureMixin, tornado.web.RequestHandler):
    """Persist camera state for one figure."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="POST, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self, fig_id: str) -> None:
        self.finish()

    def post(self, fig_id: str) -> None:
        if not self.check_auth():
            return
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
        missing = [k for k in ("position", "focal_point", "view_up") if k not in body]
        if missing:
            self.set_status(400)
            self.write({"status": "error", "detail": f"missing keys: {missing}"})
            return
        cam_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}.json"
        save_camera_state(
            position=body["position"],
            focal_point=body["focal_point"],
            view_up=body["view_up"],
            parallel_scale=body.get("parallel_scale"),
            output_path=cam_path,
        )
        self.write({"status": "ok"})


class CameraLockHandler(SecureMixin, tornado.web.RequestHandler):
    """Read or write the lock state for one figure."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="GET, POST, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self, fig_id: str) -> None:
        self.finish()

    def get(self, fig_id: str) -> None:
        if not self.check_auth():
            return
        if not _SAFE_FIG_ID.fullmatch(fig_id):
            self.set_status(400)
            self.write({"status": "error"})
            return
        lock_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}_lock.json"
        if lock_path.exists():
            self.write(json.loads(lock_path.read_text()))
        else:
            self.write({"locked": False})

    def post(self, fig_id: str) -> None:
        if not self.check_auth():
            return
        if not _SAFE_FIG_ID.fullmatch(fig_id):
            self.set_status(400)
            self.write({"status": "error"})
            return
        try:
            body = json.loads(self.request.body)
        except json.JSONDecodeError as exc:
            self.set_status(400)
            self.write({"status": "error", "detail": f"invalid JSON: {exc}"})
            return
        lock_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}_lock.json"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps({"locked": bool(body.get("locked", False))}))
        self.write({"status": "ok"})


ROUTES = [
    (r"/camera/(?P<fig_id>[^/]+)", CameraHandler),
    (r"/camera-lock/(?P<fig_id>[^/]+)", CameraLockHandler),
]
