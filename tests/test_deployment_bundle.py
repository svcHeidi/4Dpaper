"""Regression checks for the supported production deployment bundle."""
from __future__ import annotations

from pathlib import Path


def test_prod_compose_bundle_exists_and_references_caddy():
    root = Path(__file__).parent.parent
    compose = (root / "docker-compose.prod.yml").read_text(encoding="utf-8")
    caddy = (root / "deploy" / "Caddyfile").read_text(encoding="utf-8")

    assert "caddy:" in compose
    assert "image: caddy:2" in compose
    assert "./deploy/Caddyfile:/etc/caddy/Caddyfile:ro" in compose
    assert "reverse_proxy 4dpapers:5006" in caddy


def test_base_compose_supports_env_selected_runtime_file_and_bind_address():
    compose = (Path(__file__).parent.parent / "docker-compose.yml").read_text(encoding="utf-8")

    assert '${FOURD_APP_PUBLISH:-5006:5006}' in compose
    assert '${FOURD_ENV_FILE:-.env}' in compose


def test_production_env_example_declares_single_host_settings():
    text = (Path(__file__).parent.parent / ".env.production.example").read_text(encoding="utf-8")

    assert "FOURD_ENV_FILE=.env.production" in text
    assert "FOURD_APP_PUBLISH=127.0.0.1:5006:5006" in text
    assert "FOURD_DROP_PRIVILEGES=1" in text
    assert "FOURD_CHOWN_WORKSPACE=1" in text
    assert "FOURD_ALLOWED_ORIGIN=https://paper.example.com" in text
    assert "FOURD_API_KEY=replace-with-a-long-random-secret" in text


def test_container_files_define_non_root_runtime_strategy():
    root = Path(__file__).parent.parent
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (root / "docker-entrypoint.sh").read_text(encoding="utf-8")

    assert "gosu" in dockerfile
    assert "useradd --system --uid 10001" in dockerfile
    assert "--home-dir /home/fourd" in dockerfile
    assert 'FOURD_DROP_PRIVILEGES="${FOURD_DROP_PRIVILEGES:-0}"' in entrypoint
    assert 'FOURD_CHOWN_WORKSPACE="${FOURD_CHOWN_WORKSPACE:-0}"' in entrypoint
    assert 'RUNTIME_HOME="${FOURD_RUNTIME_HOME:-/home/fourd}"' in entrypoint
    assert 'export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"' in entrypoint
    assert 'exec gosu "${RUNTIME_USER}:${RUNTIME_GROUP}" python serve.py --port "$PORT"' in entrypoint


def test_container_bundles_opt_in_quick_export_page():
    root = Path(__file__).parent.parent
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8")

    assert "COPY development/quick-export /app/development/quick-export" in dockerfile
    assert "!development/quick-export/quick.html" in dockerignore
