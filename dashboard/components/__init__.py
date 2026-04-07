"""
UI Components for the 4Dpapers dashboard.

This module provides factory functions and helpers for creating
styled UI components (buttons, headers, etc.) with consistent styling.
"""

from dashboard.components.buttons import (
    ButtonVariant,
    ButtonSize,
    create_button,
)

__all__ = [
    "ButtonVariant",
    "ButtonSize",
    "create_button",
]
