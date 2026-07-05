"""Security regression tests for file reads and static runtime routes."""
from __future__ import annotations

import tempfile
from pathlib import Path

import tornado.web
from tornado.testing import AsyncHTTPTestCase

import dashboard.auth as auth
import dashboard.file_plugin as file_plugin
from dashboard.auth import AuthenticatedStaticFileHandler, DenyStateFileHandler


class SecurityRouteTest(AsyncHTTPTestCase):
    def get_app(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_project_root = file_plugin._PROJECT_ROOT
        self.old_api_key = auth._API_KEY

        file_plugin._PROJECT_ROOT = self.root
        auth._API_KEY = "test-key"

        (self.root / "AGENTS.md").write_text("internal", encoding="utf-8")
        (self.root / "private.pem").write_text("private", encoding="utf-8")
        (self.root / "normal.qmd").write_text("# ok", encoding="utf-8")
        (self.root / "_output").mkdir()
        (self.root / "_output" / "paper.html").write_text("<html>paper</html>", encoding="utf-8")
        (self.root / "state" / "figures").mkdir(parents=True)
        (self.root / "state" / "figures" / "fig.html").write_text("<html>figure</html>", encoding="utf-8")
        (self.root / "state" / "upload_tmp" / "probe").mkdir(parents=True)
        (self.root / "state" / "upload_tmp" / "probe" / "secret.txt").write_text("secret", encoding="utf-8")

        return tornado.web.Application([
            (r"/api/file", file_plugin.FileHandler),
            (
                r"/state/figures/(.*)",
                AuthenticatedStaticFileHandler,
                {"path": str(self.root / "state" / "figures")},
            ),
            (r"/state/(.*)", DenyStateFileHandler),
            (
                r"/output/(.*)",
                AuthenticatedStaticFileHandler,
                {"path": str(self.root / "_output")},
            ),
        ])

    def tearDown(self):
        file_plugin._PROJECT_ROOT = self.old_project_root
        auth._API_KEY = self.old_api_key
        self.tmp.cleanup()
        super().tearDown()

    def _get(self, path: str, *, key: bool = True):
        headers = {"X-API-Key": "test-key"} if key else None
        return self.fetch(path, headers=headers, raise_error=False)

    def test_direct_file_read_blocks_sensitive_files(self):
        assert self._get("/api/file?path=AGENTS.md").code == 403
        assert self._get("/api/file?path=private.pem").code == 403
        ok = self._get("/api/file?path=normal.qmd")
        assert ok.code == 200
        assert b"# ok" in ok.body

    def test_output_requires_api_key_when_auth_enabled(self):
        assert self._get("/output/paper.html", key=False).code == 401
        ok = self._get("/output/paper.html")
        assert ok.code == 200
        assert b"paper" in ok.body

    def test_state_figures_require_api_key_when_auth_enabled(self):
        assert self._get("/state/figures/fig.html", key=False).code == 401
        ok = self._get("/state/figures/fig.html")
        assert ok.code == 200
        assert b"figure" in ok.body

    def test_non_figure_state_is_never_static_public(self):
        assert self._get("/state/upload_tmp/probe/secret.txt", key=False).code == 401
        assert self._get("/state/upload_tmp/probe/secret.txt").code == 403
