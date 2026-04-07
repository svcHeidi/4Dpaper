"""
Button factory for creating styled buttons with consistent appearance.

All button styling is centralized in dashboard/static/css/components.css.
This module provides a clean Python API for creating buttons without
needing to know CSS class names.

Usage:
    from dashboard.components import create_button, ButtonVariant

    compile_btn = create_button("Compile", variant=ButtonVariant.PRIMARY)
    export_btn = create_button("Export PDF", variant=ButtonVariant.SECONDARY)
"""

from enum import Enum
from typing import Optional, Callable
import panel as pn


class ButtonVariant(Enum):
    """Button style variants."""
    PRIMARY = "btn-primary"        # High emphasis, teal accent
    SECONDARY = "btn-secondary"    # Low emphasis, subtle
    DANGER = "btn-danger"          # Destructive actions, red
    ICON = "btn-icon"              # Icon-only buttons


class ButtonSize(Enum):
    """Button size variants."""
    SMALL = "btn-size-small"       # 22px, for tabs and inline use
    MEDIUM = "btn-size-medium"     # 30px, for toolbars (default)
    LARGE = "btn-size-large"       # 36px, for prominent actions


def create_button(
    name: str,
    variant: ButtonVariant = ButtonVariant.SECONDARY,
    size: ButtonSize = ButtonSize.MEDIUM,
    icon: Optional[str] = None,
    button_type: str = "default",
    on_click: Optional[Callable] = None,
    **kwargs
) -> pn.widgets.Button:
    """
    Factory for creating styled buttons.

    All styling is centralized in components.css. This function ensures
    consistent styling across the app and makes adding new features trivial.

    Args:
        name: Button label text
        variant: Visual style (PRIMARY, SECONDARY, DANGER, ICON)
        size: Button size (SMALL, MEDIUM, LARGE)
        icon: Optional icon name (e.g., 'reload', 'file-download')
        button_type: Panel button_type parameter (default, primary, etc.)
        on_click: Optional callback function
        **kwargs: Additional kwargs passed to pn.widgets.Button

    Returns:
        A styled pn.widgets.Button with CSS classes applied

    Example:
        btn = create_button(
            "Compile",
            variant=ButtonVariant.PRIMARY,
            size=ButtonSize.MEDIUM,
            icon="reload",
            on_click=my_callback
        )
    """
    # Build CSS class list
    css_classes = [variant.value, size.value]

    # Add icon if provided
    if icon:
        kwargs['icon'] = icon

    # Create button with styling
    btn = pn.widgets.Button(
        name=name,
        button_type=button_type,
        css_classes=css_classes,
        **kwargs
    )

    # Wire callback if provided
    if on_click:
        btn.on_click(on_click)

    return btn
