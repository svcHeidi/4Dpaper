"""
Centralized asset path and versioning for the 4Dpapers dashboard.

Single source of truth for all CSS/JS references, versions, and paths.
When you need to change a version, update it here — it affects everywhere.
"""


class AssetVersion:
    """Version numbers for cache-busting and tracking."""
    THEME_TOKENS = "1"
    LAYOUT = "2"
    COMPONENTS = "1"
    OVERRIDES = "1"
    SPLIT_PANE = "6"
    CAMERA_SYNC = "1"
    ACTIVITY_BAR = "1"
    TAB_ALIGN = "1"
    INSERT_FIGURE = "1"
    SYNC_RECEIVER = "1"


class Assets:
    """
    Centralized registry of all CSS and JavaScript assets.

    CSS files are loaded in order: tokens → layout → components → overrides
    JS files are loaded asynchronously.
    """

    # CSS files (order matters: design tokens first, then layout, then components)
    CSS = {
        "theme_tokens": f"/assets/css/theme-tokens.css?v={AssetVersion.THEME_TOKENS}",
        "layout": f"/assets/css/layout.css?v={AssetVersion.LAYOUT}",
        "components": f"/assets/css/components.css?v={AssetVersion.COMPONENTS}",
        "overrides": f"/assets/css/overrides.css?v={AssetVersion.OVERRIDES}",
    }

    # JavaScript files (loaded asynchronously, order independent)
    JS = {
        "split_pane": f"/assets/js/split-pane.js?v={AssetVersion.SPLIT_PANE}",
        "camera_sync": f"/assets/js/camera-sync.js?v={AssetVersion.CAMERA_SYNC}",
        "activity_bar": f"/assets/js/activity-bar.js?v={AssetVersion.ACTIVITY_BAR}",
        "tab_align": f"/assets/js/tab-align.js?v={AssetVersion.TAB_ALIGN}",
        "insert_figure": f"/assets/js/insert-figure-overlay.js?v={AssetVersion.INSERT_FIGURE}",
        "sync_receiver": f"/assets/js/sync-receiver.js?v={AssetVersion.SYNC_RECEIVER}",
    }

    @staticmethod
    def css_list() -> list[str]:
        """Returns ordered CSS files for pn.extension()."""
        return list(Assets.CSS.values())

    @staticmethod
    def js_dict() -> dict[str, str]:
        """Returns JS files dict for pn.extension()."""
        return Assets.JS


# Legacy: backwards-compatible function names
def get_css_files():
    """Backwards-compatible accessor for CSS files."""
    return Assets.css_list()


def get_js_files():
    """Backwards-compatible accessor for JS files."""
    return Assets.js_dict()
