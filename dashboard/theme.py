"""Shared dashboard colors (keep in sync with static/theme.css :root)."""

from __future__ import annotations

THEME: dict[str, str] = {
    "bg_app": "#1c1c1c",
    "bg_panel": "#262626",
    "bg_sidebar": "#1f1f1f",
    "border_subtle": "#383838",
    "text_primary": "#ffffff",
    "text_muted": "#aaaaaa",
    "accent": "#4a9c6d",  # Overleaf muted green
    "accent_hover": "#3c7d57",
    "toolbar_bg": "#222222",
    "success": "#5cb85c",
    "warning": "#f0ad4e",
    "danger": "#d9534f",
    "info": "#5bc0de",
    "chrome_font_size": "13px",
}


def chrome_css() -> str:
    """Dark Overleaf-style overrides for Panel's default Bootstrap/Bokeh chrome."""
    t = THEME
    return f"""
        html, body,
        .bk-root, .bk-app,
        #main, .main-content {{
            background-color: {t["bg_app"]} !important;
            color: {t["text_primary"]} !important;
        }}
        .bk.pn-container, .bk.pn-column, .bk.pn-row {{
            background-color: transparent !important;
        }}
        .bk-input-group > label,
        .bk-clearfix > label,
        label.bk {{
            color: {t["text_muted"]} !important;
        }}
        .bk-btn.bk-btn-light, button.bk-btn-light {{
            background-color: {t["bg_panel"]} !important;
            color: {t["text_primary"]} !important;
            border-color: {t["border_subtle"]} !important;
        }}
        .bk-btn.bk-btn-light:hover, button.bk-btn-light:hover {{
            background-color: #2f2f2f !important;
        }}
        .bk-btn.bk-btn-primary, button.bk-btn-primary {{
            background-color: {t["accent"]} !important;
            border-color: {t["accent_hover"]} !important;
        }}
        .bk-btn.bk-btn-primary:hover, button.bk-btn-primary:hover {{
            background-color: {t["accent_hover"]} !important;
        }}
        .bk-btn.bk-btn-default, button.bk-btn-default {{
            background-color: {t["bg_panel"]} !important;
            color: {t["text_primary"]} !important;
            border-color: {t["border_subtle"]} !important;
        }}
        .bk-markdown, .bk.markdown, .bk-clearfix.bk-markdown {{
            color: {t["text_muted"]} !important;
        }}
    """
