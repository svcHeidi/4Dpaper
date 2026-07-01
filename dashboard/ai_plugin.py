from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

import tornado.web

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

from dashboard.auth import SecureMixin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — read once at import time from environment variables
# ---------------------------------------------------------------------------

_OLLAMA_URL: str = os.environ.get(
    "OLLAMA_URL", "http://host.docker.internal:11434/api/chat"
)
_OPENAI_API_KEY: str | None = os.environ.get("OPENAI_API_KEY") or None
_ANTHROPIC_API_KEY: str | None = os.environ.get("ANTHROPIC_API_KEY") or None
_GEMINI_API_KEY: str | None = os.environ.get("GEMINI_API_KEY") or None
_EXPOSE_AGENTS: bool = os.environ.get("FOURD_EXPOSE_AGENTS", "0").strip() == "1"

# Path to agents.yaml — sit next to serve.py at the project root
_APP_ROOT = Path(__file__).parent.parent
_AGENTS_YAML = _APP_ROOT / "agents.yaml"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROVIDER_DEFAULTS: dict[str, list[str]] = {
    "ollama": ["llama3", "mistral", "phi3", "gemma3"],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "anthropic": ["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-3-5"],
    "gemini": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-3.5-flash", "gemini-pro-latest"],
}

# Hardcoded fallback persona list — used when agents.yaml is absent or
# FOURD_EXPOSE_AGENTS is not set, so the frontend always has something.
_FALLBACK_AGENTS = [
    {
        "id": "default",
        "name": "General Assistant",
        "description": "A helpful AI assistant for 4Dpapers",
        "system_prompt": "You are a helpful AI assistant for 4Dpapers, an advanced scientific paper editor.",
    },
    {
        "id": "data_architect",
        "name": "Data Architect",
        "description": "Architecture, data modelling, and data engineering best practices",
        "system_prompt": "You are a Data Architect AI agent. Provide robust architecture advice, data modeling, and best practices for data engineering.",
    },
    {
        "id": "visualization_engineer",
        "name": "Visualization Engineer",
        "description": "Expert advice on data visualisation, plotting, and UI design",
        "system_prompt": "You are a Visualization Engineer AI agent. Provide expert advice on data visualization, plotting (Plotly, matplotlib), and UI design.",
    },
    {
        "id": "technical_writer",
        "name": "Technical Writer",
        "description": "Clear, concise documentation, LaTeX, and copy-editing",
        "system_prompt": "You are a Technical Writer AI agent. Provide clear, concise, and well-structured documentation advice and copy editing.",
    },
]


def _load_agents() -> list[dict[str, str]]:
    """Load persona definitions from agents.yaml, falling back to the hardcoded list."""
    if not _YAML_AVAILABLE:
        logger.warning("PyYAML not installed — using fallback agent list")
        return _FALLBACK_AGENTS

    if not _AGENTS_YAML.exists():
        logger.warning("agents.yaml not found at %s — using fallback agent list", _AGENTS_YAML)
        return _FALLBACK_AGENTS

    try:
        with open(_AGENTS_YAML, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        agents = data.get("agents", [])
        if not isinstance(agents, list) or not agents:
            raise ValueError("agents key is empty or not a list")
        return agents
    except Exception as exc:
        logger.error("Failed to parse agents.yaml: %s — using fallback", exc)
        return _FALLBACK_AGENTS


def _build_system_prompt(persona: str) -> str:
    """Return the system prompt for the given persona id."""
    for agent in _load_agents():
        if agent.get("id") == persona:
            return agent.get("system_prompt", "")
    # Unknown persona — use the default agent's prompt
    for agent in _load_agents():
        if agent.get("id") == "default":
            return agent.get("system_prompt", "")
    return "You are a helpful AI assistant for 4Dpapers."


# ---------------------------------------------------------------------------
# GET /api/providers
# ---------------------------------------------------------------------------

class ProvidersHandler(SecureMixin, tornado.web.RequestHandler):
    """Return which AI providers are configured server-side."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="GET, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    def get(self) -> None:
        if not self.check_auth():
            return

        providers = [
            {
                "id": "ollama",
                "name": "Ollama (Local)",
                "available": True,  # Always offered; connection errors surface at chat time
                "default_model": "llama3",
                "models": _PROVIDER_DEFAULTS["ollama"],
            },
            {
                "id": "openai",
                "name": "OpenAI",
                "available": _OPENAI_API_KEY is not None,
                "default_model": "gpt-4o",
                "models": _PROVIDER_DEFAULTS["openai"] if _OPENAI_API_KEY else [],
            },
            {
                "id": "anthropic",
                "name": "Anthropic",
                "available": _ANTHROPIC_API_KEY is not None,
                "default_model": "claude-sonnet-4-5",
                "models": _PROVIDER_DEFAULTS["anthropic"] if _ANTHROPIC_API_KEY else [],
            },
            {
                "id": "gemini",
                "name": "Google Gemini",
                "available": _GEMINI_API_KEY is not None,
                "default_model": "gemini-2.5-pro",
                "models": _PROVIDER_DEFAULTS["gemini"] if _GEMINI_API_KEY else [],
            },
        ]

        self.write({"providers": providers})


# ---------------------------------------------------------------------------
# GET /api/agents
# ---------------------------------------------------------------------------

class AgentsHandler(SecureMixin, tornado.web.RequestHandler):
    """Return the list of agent personas.

    Controlled by FOURD_EXPOSE_AGENTS=1.  When the flag is not set the
    endpoint returns the full list anyway (the flag only gates whether it
    is advertised / reachable from the outside — the frontend always needs
    the data to build its dropdown).
    """

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="GET, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    def get(self) -> None:
        if not self.check_auth():
            return

        agents = _load_agents()
        # Strip system_prompt from the public response — keep id, name, description only
        public = [
            {"id": a.get("id", ""), "name": a.get("name", ""), "description": a.get("description", "")}
            for a in agents
        ]
        self.write({"agents": public})


# ---------------------------------------------------------------------------
# POST /api/ai/chat
# ---------------------------------------------------------------------------

class AIChatHandler(SecureMixin, tornado.web.RequestHandler):
    """Proxy chat messages to the configured AI provider.

    Request body (JSON):
        messages  list[{role, content}]   Conversation history (no system msg)
        persona   str                     Agent persona id  (default: "default")
        provider  str                     "ollama" | "openai" | "anthropic"
        model     str                     Model name for the chosen provider

    API keys are read exclusively from server-side environment variables —
    they are never accepted from the client request body.
    """

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="POST, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    def post(self) -> None:
        if not self.check_auth():
            return

        try:
            body = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_status(400)
            self.write({"status": "error", "detail": "invalid JSON"})
            return

        messages: list[dict[str, str]] = body.get("messages", [])
        persona: str = body.get("persona", "default")
        provider: str = body.get("provider", "ollama")
        model: str = body.get("model", "")

        # Resolve defaults
        if not model:
            model = _PROVIDER_DEFAULTS.get(provider, [""])[0]

        system_prompt = _build_system_prompt(persona)
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        reply_content = ""

        try:
            if provider == "ollama":
                reply_content = self._call_ollama(model, full_messages)

            elif provider == "openai":
                if not _OPENAI_API_KEY:
                    self.set_status(400)
                    self.write({
                        "status": "error",
                        "detail": "OpenAI is not configured on this server (OPENAI_API_KEY not set).",
                    })
                    return
                reply_content = self._call_openai(model, full_messages)

            elif provider == "anthropic":
                if not _ANTHROPIC_API_KEY:
                    self.set_status(400)
                    self.write({
                        "status": "error",
                        "detail": "Anthropic is not configured on this server (ANTHROPIC_API_KEY not set).",
                    })
                    return
                # Routing wired up in a future iteration
                self.set_status(501)
                self.write({"status": "error", "detail": "Anthropic routing coming soon."})
                return

            elif provider == "gemini":
                if not _GEMINI_API_KEY:
                    self.set_status(400)
                    self.write({
                        "status": "error",
                        "detail": "Gemini is not configured on this server (GEMINI_API_KEY not set).",
                    })
                    return
                reply_content = self._call_gemini(model, full_messages)

            else:
                self.set_status(400)
                self.write({"status": "error", "detail": f"Unknown provider: {provider}"})
                return

        except urllib.error.URLError as exc:
            logger.error("AI API error (%s): %s", provider, exc)
            self.set_status(502)
            if provider == "ollama":
                self.write({
                    "status": "error",
                    "detail": "Could not connect to Ollama. Ensure Ollama is running and reachable.",
                })
            else:
                self.write({"status": "error", "detail": f"Failed to connect to AI provider: {exc}"})
            return
        except Exception as exc:
            logger.error("Unexpected error in AI chat (%s): %s", provider, exc)
            self.set_status(500)
            self.write({"status": "error", "detail": f"Internal server error: {exc}"})
            return

        self.write({"status": "ok", "reply": reply_content})

    # ------------------------------------------------------------------ #
    # Private provider implementations
    # ------------------------------------------------------------------ #

    def _call_ollama(self, model: str, messages: list[dict]) -> str:
        req_body = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
        req = urllib.request.Request(
            _OLLAMA_URL,
            data=req_body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        return data.get("message", {}).get("content", "")

    def _call_openai(self, model: str, messages: list[dict]) -> str:
        req_body = json.dumps({"model": model, "messages": messages}).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=req_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_OPENAI_API_KEY}",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    def _call_gemini(self, model: str, messages: list[dict]) -> str:
        req_body = json.dumps({"model": model, "messages": messages}).encode()
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            data=req_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_GEMINI_API_KEY}",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")


# ---------------------------------------------------------------------------
# Route table
# ---------------------------------------------------------------------------

ROUTES = [
    (r"/api/providers", ProvidersHandler),
    (r"/api/agents", AgentsHandler),
    (r"/api/ai/chat", AIChatHandler),
]
