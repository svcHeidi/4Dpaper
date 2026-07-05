"""
Shared authentication and CORS helpers for the 4Dpapers dashboard.

Authentication
--------------
If the environment variable ``FOURD_API_KEY`` is set, every non-exempt
request must include either the header::

    X-API-Key: <value>

or the same key in the browser cookie ``fourd_api_key``. Supporting the
cookie path keeps same-origin browser fetches, iframe previews, and file
downloads working in the single-tenant deployment flow.

If ``FOURD_API_KEY`` is *not* set the check is skipped so the server remains
usable in the default local-development mode without any configuration
changes.

CORS
----
``FOURD_ALLOWED_ORIGIN`` controls the ``Access-Control-Allow-Origin``
response header.  Default: ``http://localhost:5006``.  Set to the actual
URL the dashboard is served from when deploying remotely.
"""
from __future__ import annotations

import os

import tornado.web

# ---------------------------------------------------------------------------
# Configuration (read once at import time)
# ---------------------------------------------------------------------------

#: Shared secret that clients must send in the ``X-API-Key`` header.
#: Leave unset to disable authentication (local-dev mode).
_API_KEY: str | None = os.getenv("FOURD_API_KEY") or None

#: Same-origin browser cookie used by the dashboard for iframe/file access.
_API_KEY_COOKIE = "fourd_api_key"

#: The origin that is allowed to make cross-origin requests to this server.
_ALLOWED_ORIGIN: str = os.getenv("FOURD_ALLOWED_ORIGIN", "http://localhost:5006")

# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------


class SecureMixin:
    """
    Tornado ``RequestHandler`` mixin that:

    * Applies a strict ``Access-Control-Allow-Origin`` header (replaces ``*``).
    * Enforces ``X-API-Key`` authentication when ``FOURD_API_KEY`` is set.
    * Provides a helper ``check_auth()`` that handlers call at the top of
      every method that needs protecting.

    Usage::

        class MyHandler(SecureMixin, tornado.web.RequestHandler):
            def set_default_headers(self):
                self.apply_cors_headers()

            def get(self):
                if not self.check_auth():
                    return
                ...
    """

    # Endpoints listed here skip the API-key check even when FOURD_API_KEY is set.
    _AUTH_EXEMPT_PATHS: frozenset[str] = frozenset({"/api/health"})

    def apply_cors_headers(self, methods: str = "GET, POST, OPTIONS") -> None:
        """Set strict CORS headers.  Call from ``set_default_headers``."""
        self.set_header("Access-Control-Allow-Origin", _ALLOWED_ORIGIN)
        self.set_header("Access-Control-Allow-Methods", methods)
        self.set_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, X-Upload-Id, X-Rel-Path")
        self.set_header("Access-Control-Allow-Credentials", "false")

    def check_auth(self) -> bool:
        """
        Validate the ``X-API-Key`` header when ``FOURD_API_KEY`` is configured.

        Returns ``True`` if the request is authorised (or auth is disabled).
        Returns ``False`` and writes a 401 response if the key is missing or wrong.
        Handlers must return early when this method returns ``False``.
        """
        if _API_KEY is None:
            return True  # auth disabled — local-dev mode

        request_path = getattr(self, "request", None)
        if request_path is not None and self.request.path in self._AUTH_EXEMPT_PATHS:
            return True

        provided = (
            self.request.headers.get("X-API-Key", "")
            or self.get_cookie(_API_KEY_COOKIE, default="")
        )
        if provided != _API_KEY:
            self.set_status(401)
            self.set_header("Content-Type", "application/json")
            self.finish({"error": "Unauthorized — missing or invalid X-API-Key"})
            return False
        return True


class AuthenticatedStaticFileHandler(SecureMixin, tornado.web.StaticFileHandler):
    """Static-file handler that enforces the dashboard API key when configured."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="GET, HEAD, OPTIONS")

    def options(self, path: str) -> None:
        self.finish()

    async def get(self, path: str, include_body: bool = True) -> None:
        if not self.check_auth():
            return
        await super().get(path, include_body=include_body)


class DenyStateFileHandler(SecureMixin, tornado.web.RequestHandler):
    """Deny direct access to runtime state that is not explicitly public."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="GET, HEAD, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self, path: str) -> None:
        self.finish()

    def get(self, path: str) -> None:
        if not self.check_auth():
            return
        self.set_status(403)
        self.write({"error": "Access denied"})

    def head(self, path: str) -> None:
        if not self.check_auth():
            return
        self.set_status(403)
        self.finish()
