"""
4Dpapers Dashboard - Serve Entry Point

This script starts the Panel development server with proper static file
serving configuration AND loads all API plugins.

Run with:
    python serve.py [--port PORT]

Environment variables:
    PORT — Server port (default: auto)

Then visit the server at the URL shown in console output.
"""

import argparse
import importlib.util
import os
import sys
from pathlib import Path

# Determine application and project roots
app_root = Path(__file__).parent  # /app in Docker, or /Users/... in development
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

# Determine project root (workspace in Docker, or app root in development)
project_root = Path(os.getenv("PROJECT_ROOT", str(app_root)))
os.environ["PROJECT_ROOT"] = str(project_root)

import tornado.web
import panel as pn
from dashboard.plugins import ROUTES as plugin_routes
from dashboard.auth import auth_startup_report

# Address the server binds to. Defaults to all interfaces (Bokeh/Panel default)
# to preserve existing behaviour; set FOURD_BIND_ADDRESS=127.0.0.1 to restrict
# to loopback (e.g. when a reverse proxy handles public ingress).
bind_address = os.getenv("FOURD_BIND_ADDRESS", "0.0.0.0")

# Static files directory (in app, not project)
static_dir = app_root / "dashboard" / "static"


def _load_opt_in_quick_routes(root: Path) -> list:
    """Load development Quick Export routes only for an explicit Quick launch."""
    if not os.getenv("FOURD_QUICK_TARGET", "").strip():
        return []

    module_path = root / "development" / "quick-export" / "backend_handlers.py"
    if not module_path.is_file():
        raise RuntimeError(
            "FOURD_QUICK_TARGET is set but this image does not contain the "
            "Quick Export development module"
        )

    spec = importlib.util.spec_from_file_location("fourd_quick_export", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the Quick Export development module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return list(module.ROUTES)

class IndexHandler(tornado.web.StaticFileHandler):
    """Serve index.html for root path."""
    def get(self, path="", include_body=True):
        if path == "" or not path:
            self.path = str(static_dir)
            path = "index.html"
        return super().get(path, include_body=include_body)

    def head(self, path=""):
        return self.get(path, include_body=False)

def main():
    """Start the dashboard server."""
    parser = argparse.ArgumentParser(description="4Dpapers Dashboard Server")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Server port (default: auto-select, or use PORT environment variable)"
    )
    args = parser.parse_args()

    # Get port from: CLI args > environment variable > 5006
    port = args.port or os.getenv("PORT") or 5006
    port = int(port)

    # Fail-open auth guard: refuse to boot unauthenticated on a network address.
    level, message = auth_startup_report(bind_address)
    if message:
        print(message, file=sys.stderr)
    if level == "refuse":
        sys.exit(1)

    quick_routes = _load_opt_in_quick_routes(app_root)

    print(f"Starting 4Dpapers Dashboard...")
    print(f"Application root: {app_root}")
    print(f"Project root: {project_root}")
    print(f"Static files: {static_dir}")
    print(f"Bind address: {bind_address}")
    print(f"API routes registered: {len(plugin_routes) + len(quick_routes)}")
    if quick_routes:
        print("Quick Export mode: enabled")

    # Serve with explicit static directory AND plugin routes
    # Map /assets/ to dashboard/static/ (Panel reserves /static/ for internal use)
    output_dir = project_root / "_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    extra_patterns = [
        (r"^/$", IndexHandler, {"path": str(static_dir)}),  # Serve index.html at root
        (r"^/assets/(.*)", tornado.web.StaticFileHandler, {"path": str(static_dir)}),  # Asset files
        (r"^/dashboard/static/(.*)", tornado.web.StaticFileHandler, {"path": str(static_dir)}),  # JS/CSS files
        *plugin_routes,  # API routes from plugins
        *quick_routes,  # Opt-in development Quick Export routes
    ]

    pn.serve(
        {},  # No Panel apps, just static + API routes
        port=port,
        address=bind_address,
        show=False,
        title="4Dpapers Dashboard",
        extra_patterns=extra_patterns,
    )


if __name__ == '__main__':
    main()
