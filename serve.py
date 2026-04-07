"""
4Dpapers Dashboard - Serve Entry Point

This script starts the Panel development server with proper static file
serving configuration. Use this instead of 'panel serve dashboard/app.py'.

Run with:
    python serve.py

Then visit: http://localhost:5006/
"""

import sys
from pathlib import Path

# Add repo root to path so imports work
repo_root = Path(__file__).parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import panel as pn
from dashboard.app import create_app

# Static files directory
static_dir = repo_root / "dashboard" / "static"

def main():
    """Start the dashboard server."""
    print(f"Starting 4Dpapers Dashboard...")
    print(f"Static files: {static_dir}")
    print(f"Visit: http://localhost:5006/")

    # Create app
    app = create_app()

    # Serve with explicit static directory
    # Map /static/ to dashboard/static/ so /static/css/ and /static/js/ work
    pn.serve(
        {'/': app},
        static_dirs={'static': str(static_dir)},
        port=5006,
        show=False,
        title="4Dpapers Dashboard"
    )


if __name__ == '__main__':
    main()
