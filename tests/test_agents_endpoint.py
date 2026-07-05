"""Tests for optional agent persona exposure."""
from __future__ import annotations

import tempfile
from pathlib import Path

import tornado.web
from tornado.testing import AsyncHTTPTestCase

import dashboard.ai_plugin as ai_plugin
import dashboard.auth as auth


class AgentsEndpointTest(AsyncHTTPTestCase):
    def get_app(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_api_key = auth._API_KEY
        self.old_expose_agents = ai_plugin._EXPOSE_AGENTS
        self.old_agents_yaml = ai_plugin._AGENTS_YAML

        auth._API_KEY = "test-key"
        ai_plugin._AGENTS_YAML = self.root / "agents.yaml"
        ai_plugin._AGENTS_YAML.write_text(
            """
agents:
  - id: paper_writer
    name: Paper Writer
    description: Helps authors write scientific papers
    system_prompt: hidden prompt
""".strip(),
            encoding="utf-8",
        )

        return tornado.web.Application([(r"/api/agents", ai_plugin.AgentsHandler)])

    def tearDown(self):
        auth._API_KEY = self.old_api_key
        ai_plugin._EXPOSE_AGENTS = self.old_expose_agents
        ai_plugin._AGENTS_YAML = self.old_agents_yaml
        self.tmp.cleanup()
        super().tearDown()

    def _get(self):
        return self.fetch(
            "/api/agents",
            headers={"X-API-Key": "test-key"},
            raise_error=False,
        )

    def test_agents_endpoint_disabled_returns_404(self):
        ai_plugin._EXPOSE_AGENTS = False
        response = self._get()
        assert response.code == 404
        assert b"disabled" in response.body

    def test_agents_endpoint_enabled_strips_system_prompt(self):
        ai_plugin._EXPOSE_AGENTS = True
        response = self._get()
        assert response.code == 200
        assert b"paper_writer" in response.body
        assert b"Paper Writer" in response.body
        assert b"system_prompt" not in response.body
        assert b"hidden prompt" not in response.body
