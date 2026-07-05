"""Regression tests for backend health readiness reporting."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import tornado.web
from tornado.testing import AsyncHTTPTestCase

import dashboard.compile_plugin as compile_plugin


class HealthEndpointTest(AsyncHTTPTestCase):
    def get_app(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_project_root = compile_plugin._PROJECT_ROOT
        self.old_which = shutil.which

        compile_plugin._PROJECT_ROOT = self.root
        shutil.which = lambda cmd: "/usr/bin/quarto" if cmd == "quarto" else self.old_which(cmd)

        return tornado.web.Application([(r"/api/health", compile_plugin.HealthCheckHandler)])

    def tearDown(self):
        compile_plugin._PROJECT_ROOT = self.old_project_root
        shutil.which = self.old_which
        self.tmp.cleanup()
        super().tearDown()

    def test_health_reports_degraded_when_workspace_not_ready(self):
        response = self.fetch("/api/health", raise_error=False)
        assert response.code == 503
        assert b'"status": "degraded"' in response.body
        assert b'"backend_ready": false' in response.body
        assert b'"exists": false' in response.body

    def test_health_reports_ok_when_workspace_is_ready(self):
        (self.root / "main.qmd").write_text("# ok", encoding="utf-8")
        (self.root / "_output").mkdir()
        (self.root / "state").mkdir()

        response = self.fetch("/api/health", raise_error=False)
        assert response.code == 200
        assert b'"status": "ok"' in response.body
        assert b'"backend_ready": true' in response.body
        assert b'"available": true' in response.body

