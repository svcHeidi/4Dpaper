"""Shared dashboard colors (keep in sync with static/theme.css :root)."""

from __future__ import annotations

THEME: dict[str, str] = {
    "bg_app": "#0f0f0f",
    "bg_panel": "#121212",
    "bg_sidebar": "#1f1c19",
    "border_subtle": "#3d3834",
    # High-contrast text: white + light blue accents in CSS explorer
    "text_primary": "#ffffff",
    "text_muted": "#b8def5",
    "accent": "#138a7c",
    "accent_hover": "#1aad9a",
    "toolbar_bg": "#181614",
    "success": "#5ee4a8",
    "warning": "#ffe066",
    "danger": "#ff8a8a",
    "info": "#7ec8ff",
}
