"""
Panel plugin wrapper to expose camera/field sync routes and static file serving.

Add to panel serve with:
    panel serve dashboard/app.py --plugins dashboard.plugins ...
"""
from __future__ import annotations

from pathlib import Path

import tornado.web

from dashboard.camera_plugin import ROUTES as camera_routes
from dashboard.color_plugin import ROUTES as color_routes
from dashboard.field_plugin import ROUTES as field_routes
from dashboard.upload_plugin import ROUTES as upload_routes

_PROJECT_ROOT = Path(__file__).parent.parent

_state_route = (
    r"/state/(.*)",
    tornado.web.StaticFileHandler,
    {"path": str(_PROJECT_ROOT / "state")},
)

_output_route = (
    r"/output/(.*)",
    tornado.web.StaticFileHandler,
    {"path": str(_PROJECT_ROOT / "_output")},
)

ROUTES = (
    camera_routes + color_routes + field_routes + upload_routes
    + [_state_route, _output_route]
)
