"""Shared render-serialization lock for the 4Dpapers dashboard.

Kept in its own dependency-free module (rather than dashboard/utils.py, which
pulls in the cryptography-backed signing helpers) so both compile_plugin and
upload_plugin can import the single shared instance cheaply.
"""
from __future__ import annotations

import asyncio

# Semaphore shared by compile_plugin and upload_plugin: only one render
# (Quarto compile or upload figure preview) may run at a time to prevent
# resource exhaustion.
_render_lock = asyncio.Semaphore(1)
