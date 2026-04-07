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

# Static files directory (in app, not project)
static_dir = app_root / "dashboard" / "static"

class IndexHandler(tornado.web.StaticFileHandler):
    """Serve index.html for root path."""
    def get(self, path=""):
        if path == "" or not path:
            self.path = str(static_dir)
            path = "index.html"
        return super().get(path)

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

    # Get port from: CLI args > environment variable > None (auto)
    port = args.port or os.getenv("PORT")
    if port:
        port = int(port)

    print(f"Starting 4Dpapers Dashboard...")
    print(f"Application root: {app_root}")
    print(f"Project root: {project_root}")
    print(f"Static files: {static_dir}")
    print(f"API routes registered: {len(plugin_routes)}")

    # Serve with explicit static directory AND plugin routes
    # Map /assets/ to dashboard/static/ (Panel reserves /static/ for internal use)
    extra_patterns = [
        (r"^/$", IndexHandler, {"path": str(static_dir)}),  # Serve index.html at root
        (r"^/assets/(.*)", tornado.web.StaticFileHandler, {"path": str(static_dir)}),  # Asset files
        *plugin_routes,  # API routes from plugins
    ]

    pn.serve(
        {},  # No Panel apps, just static + API routes
        port=port,
        show=False,
        title="4Dpapers Dashboard",
        extra_patterns=extra_patterns,
    )


if __name__ == '__main__':
    main()
