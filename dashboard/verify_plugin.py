"""Dashboard endpoint for verifying signed 4Dpapers HTML documents."""
from __future__ import annotations

import json

import tornado.web

from dashboard.auth import SecureMixin
from dashboard.document_signing import verify_signed_html

_MAX_VERIFY_BODY_BYTES = 50 * 1024 * 1024


class VerifyDocumentHandler(SecureMixin, tornado.web.RequestHandler):
    """POST /api/verify — verify a signed HTML document."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="POST, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    def post(self) -> None:
        if not self.check_auth():
            return

        try:
            if len(self.request.body) > _MAX_VERIFY_BODY_BYTES:
                self.set_status(413)
                self.write({"error": "Request body exceeds 50 MB limit"})
                return

            filename = "document.html"
            html_content: str | None = None

            uploaded = self.request.files.get("file") or self.request.files.get("document")
            if uploaded:
                item = uploaded[0]
                filename = item.get("filename") or filename
                body = item.get("body", b"")
                if len(body) > _MAX_VERIFY_BODY_BYTES:
                    self.set_status(413)
                    self.write({"error": f"Uploaded file '{filename}' exceeds 50 MB limit"})
                    return
                try:
                    html_content = body.decode("utf-8")
                except UnicodeDecodeError:
                    self.set_status(400)
                    self.write({"error": "Uploaded file must be UTF-8 encoded HTML"})
                    return
            else:
                body = json.loads(self.request.body or b"{}")
                html_content = body.get("html") or body.get("content")
                filename = body.get("filename", filename)
                if not isinstance(html_content, str) or not html_content:
                    self.set_status(400)
                    self.write({"error": "Provide HTML via multipart field 'file' or JSON field 'html'"})
                    return

            result = verify_signed_html(html_content)
            self.write({
                "filename": filename,
                **result.to_dict(),
            })
        except json.JSONDecodeError as exc:
            self.set_status(400)
            self.write({"error": f"Invalid JSON: {exc}"})
        except Exception as exc:
            self.set_status(500)
            self.write({"error": f"{type(exc).__name__}: {exc}"})


ROUTES = [
    (r"/api/verify", VerifyDocumentHandler),
]
