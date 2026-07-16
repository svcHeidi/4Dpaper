"""Guard: the dashboard must not depend on external CDNs at runtime.

The dashboard is designed to run inside egress-restricted / air-gapped
research containers (e.g. an electrophysiology solver image). If index.html
loads styling or scripts from a public CDN, the whole UI renders unstyled and
the editor/export buttons silently break when the container cannot reach the
network. These tests fail if any resource-loading tag (or @font-face / @import)
points at an http(s) host, so the regression can never sneak back in.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_STATIC_DIR = Path(__file__).parent.parent / "dashboard" / "static"
_INDEX = _STATIC_DIR / "index.html"


def _index_html() -> str:
    return _INDEX.read_text(encoding="utf-8")


# Resource-loading attributes that must resolve to a locally-served asset.
# <a href="https://..."> (navigation links) are intentionally NOT checked —
# only tags that fetch a subresource at load time break offline rendering.
_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
_LINK_HREF = re.compile(r"<link\b[^>]*\bhref=[\"']([^\"']+)[\"']", re.IGNORECASE)
_CSS_URL = re.compile(r"url\(\s*[\"']?([^\"')]+)[\"']?\s*\)", re.IGNORECASE)


def _is_external(url: str) -> bool:
    return url.strip().lower().startswith(("http://", "https://", "//"))


def test_index_scripts_are_all_local():
    external = [src for src in _SCRIPT_SRC.findall(_index_html()) if _is_external(src)]
    assert external == [], f"index.html loads scripts from external hosts: {external}"


def test_index_stylesheets_are_all_local():
    external = [href for href in _LINK_HREF.findall(_index_html()) if _is_external(href)]
    assert external == [], f"index.html loads stylesheets from external hosts: {external}"


def test_index_css_urls_are_all_local():
    """@font-face / @import / background url() references must be local."""
    external = [u for u in _CSS_URL.findall(_index_html()) if _is_external(u)]
    assert external == [], f"index.html references external CSS assets: {external}"


def test_no_known_cdn_hosts_referenced():
    """Belt-and-braces: the specific CDNs that used to power the UI are gone."""
    html = _index_html()
    banned = [
        "cdn.tailwindcss.com",
        "fonts.googleapis.com",
        "fonts.gstatic.com",
        "unpkg.com",
        "cdnjs.cloudflare.com",
        "cdn.jsdelivr.net",
        "polyfill",
    ]
    hit = [host for host in banned if host in html]
    assert hit == [], f"index.html still references banned CDN hosts: {hit}"


@pytest.mark.parametrize(
    "asset",
    [
        "vendor/tailwind/tailwind.min.js",
        "vendor/codemirror/codemirror.min.js",
        "vendor/codemirror/codemirror.min.css",
        "vendor/phosphor/phosphor.css",
    ],
)
def test_vendored_asset_present(asset):
    """Core vendored assets must exist on disk so the local references resolve."""
    path = _STATIC_DIR / asset
    assert path.is_file(), f"missing vendored asset: {asset}"
    assert path.stat().st_size > 0, f"vendored asset is empty: {asset}"
