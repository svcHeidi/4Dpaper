from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
import urllib.parse
from typing import Any

import tornado.web

from dashboard.auth import SecureMixin

logger = logging.getLogger(__name__)

class AIChatHandler(SecureMixin, tornado.web.RequestHandler):
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

        messages = body.get("messages", [])
        persona = body.get("persona", "default")
        config = body.get("config", {})
        
        provider = config.get("provider", "ollama")
        model = config.get("model", "llama3")
        api_key = config.get("apiKey", "")
        
        # System prompt based on persona
        system_prompts = {
            "data_architect": "You are a Data Architect AI agent. Provide robust architecture advice, data modeling, and best practices for data engineering.",
            "visualization_engineer": "You are a Visualization Engineer AI agent. Provide expert advice on data visualization, plotting (Plotly, matplotlib), and UI design.",
            "technical_writer": "You are a Technical Writer AI agent. Provide clear, concise, and well-structured documentation advice and copy editing.",
            "default": "You are a helpful AI assistant for 4Dpapers, an advanced code editor."
        }
        
        system_message = {"role": "system", "content": system_prompts.get(persona, system_prompts["default"])}
        
        full_messages = [system_message] + messages

        reply_content = ""

        try:
            if provider == "ollama":
                # Ollama API
                req_body = json.dumps({
                    "model": model,
                    "messages": full_messages,
                    "stream": False
                }).encode("utf-8")
                
                ollama_url = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434/api/chat")
                req = urllib.request.Request(
                    ollama_url,
                    data=req_body,
                    headers={"Content-Type": "application/json"}
                )
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    reply_content = res_data.get("message", {}).get("content", "")
                    
            elif provider == "openai":
                if not api_key:
                    self.set_status(400)
                    self.write({"status": "error", "detail": "OpenAI API key is required for openai provider."})
                    return
                    
                req_body = json.dumps({
                    "model": model,
                    "messages": full_messages,
                }).encode("utf-8")
                
                req = urllib.request.Request(
                    "https://api.openai.com/v1/chat/completions",
                    data=req_body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}"
                    }
                )
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    reply_content = res_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                self.set_status(400)
                self.write({"status": "error", "detail": f"Unknown provider: {provider}"})
                return
                
        except urllib.error.URLError as e:
            logger.error(f"AI API error: {e}")
            self.set_status(502)
            if provider == "ollama":
                self.write({"status": "error", "detail": "Could not connect to Ollama. Ensure Ollama is running locally on port 11434."})
            else:
                self.write({"status": "error", "detail": f"Failed to connect to AI provider: {str(e)}"})
            return
        except Exception as e:
            logger.error(f"Unexpected error in AI Chat: {e}")
            self.set_status(500)
            self.write({"status": "error", "detail": f"Internal server error: {str(e)}"})
            return

        self.write({
            "status": "ok",
            "reply": reply_content
        })

ROUTES = [
    (r"/api/ai/chat", AIChatHandler),
]
