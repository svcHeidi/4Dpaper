"""Tests for the unified controls strip snippet."""
from __future__ import annotations
import importlib.util
from pathlib import Path


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestControlsStripExists:
    def test_function_exists(self):
        mod = _load_4dpaper()
        assert hasattr(mod, "_controls_strip_snippet")

    def test_returns_string(self):
        mod = _load_4dpaper()
        result = mod._controls_strip_snippet("fig-vm")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_empty_when_all_hidden(self):
        mod = _load_4dpaper()
        result = mod._controls_strip_snippet(
            "fig-vm", show_lock_btn=False, show_orientation=False
        )
        assert result == ""


class TestControlsStripHtml:
    def test_strip_div_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", show_lock_btn=True,
            fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0, 1], "at": [0, 1]},
        )
        assert 'id="cs-topbar-fig_vm"' in html

    def test_lock_button_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert 'id="cs-btn-lock-fig_vm"' not in html

    def test_axes_button_absent_when_show_orientation(self):
        """The corner cube replaces the axes strip button."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-btn-axes-fig_vm"' not in html

    def test_axes_button_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert 'id="cs-btn-axes-fig_vm"' not in html

    def test_field_selector_present_when_multiple_fields(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert 'id="cs-field-sel-fig_vm"' in html

    def test_field_selector_absent_when_single_field(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm"], active_field="Vm",
            field_data_b64={"Vm": "AA=="}, field_ranges={"Vm": [0,1]},
        )
        assert 'id="cs-field-sel-fig_vm"' not in html

    def test_time_slider_present_when_time_data(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.0", "0.5"], time_data_b64={"Vm": ["AA==", "BB=="]},
            time_global_range={"Vm": [0.0, 1.0]}, time_field="Vm",
        )
        assert 'id="cs-time-slider-fig_vm"' in html

    def test_time_slider_absent_when_no_time(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert 'id="cs-time-slider-fig_vm"' not in html

    def test_popup_panels_present_for_active_features(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True, show_orientation=True)
        assert 'id="cs-pop-axes-fig_vm"' not in html
        assert 'id="cs-pop-lock-fig_vm"' not in html
        assert 'id="cs-corner-fig_vm"' in html

    def test_axis_widget_svg_present_when_show_orientation(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-svg-axes-fig_vm"' in html
        assert 'width="56"' in html
        assert 'height="56"' in html

    def test_cube_svg_size(self):
        """The corner widget stays pinned to the lower-left corner."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        corner_pos = html.find('id="cs-corner-fig_vm"')
        assert corner_pos != -1, "cs-corner div not found"
        region = html[corner_pos:corner_pos + 200]
        assert "bottom:4px" in region
        assert "left:4px" in region

    def test_axes_popup_absent(self):
        """The axes popup is not emitted when orientation is enabled."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-pop-axes-fig_vm"' not in html

    def test_corner_cube_absent_when_orientation_hidden(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert 'id="cs-svg-axes-fig_vm"' not in html
        assert 'id="cs-corner-fig_vm"' not in html

    def test_lock_widget_present_when_show_lock(self):
        """cs-lock-widget present when show_lock_btn=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        widget_pos = html.find('id="cs-lock-widget-fig_vm"')
        assert widget_pos != -1, "cs-lock-widget element not found"

    def test_camera_sync_badge_present_when_show_lock(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'id="cs-cam-sync-fig_vm"' in html
        assert "static PDF screenshots" in html

    def test_lock_widget_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert 'id="cs-lock-widget-fig_vm"' not in html
        assert 'id="cs-cam-sync-fig_vm"' not in html

    def test_lock_widget_absent_show_lock_false_orientation_true(self):
        """No lock widget when show_lock_btn=False, even with orientation."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False, show_orientation=True)
        assert 'id="cs-lock-widget-fig_vm"' not in html

    def test_snippet_not_empty_when_only_orientation(self):
        """Corner cube alone is enough — snippet must not return '' when
        show_lock_btn=False and no fields/time but show_orientation=True."""
        mod = _load_4dpaper()
        result = mod._controls_strip_snippet("fig-vm", show_lock_btn=False, show_orientation=True)
        assert result != ""
        assert 'id="cs-svg-axes-fig_vm"' in result





class TestControlsStripCameraLogic:
    def test_camera_apply_listener_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert "4dpaper-camera-apply" in html

    def test_camera_sets_position_focal_viewup(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "setPosition" in html
        assert "setFocalPoint" in html
        assert "setViewUp" in html

    def test_send_camera_on_pointerup(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "pointerup" in html

    def test_camera_sync_posts_without_debounce_timer(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "_postCam" in html
        assert "_camLastSent" in html
        assert "_camTimer" not in html

    def test_lock_toggle_sends_postmessage(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert "4dpaper-lock-toggle" in html

    def test_camera_ack_updates_sync_badge(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert "_setCamSyncStatus" in html
        assert 'd.type==="4dpaper-camera-ack"' in html
        assert 'd.fig_id==="*"' in html
        assert "Camera synced" in html


class TestControlsStripOrientationLogic:
    def test_axes_svg_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-svg-axes-fig_vm"' in html

    def test_axis_flash_present(self):
        """Axis helper flash span remains present with the orientation widget."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-iso-flash-fig_vm"' in html

    def test_axis_flash_absent_when_orientation_hidden(self):
        """Axis flash span is omitted when orientation is hidden."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert 'cs-iso-flash-' not in html


class TestControlsStripFieldLogic:
    def test_field_select_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert 'id="cs-field-sel-fig_vm"' in html

    def test_field_data_embedded(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AABB", "at": "CCDD"}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert "AABB" in html
        assert "CCDD" in html

    def test_field_setdata_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert "setData" in html
        assert "setScalarRange" in html


class TestControlsStripTimeLogic:
    def test_time_slider_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.0", "0.5", "1.0"], time_data_b64={"Vm": ["AA==", "BB==", "CC=="]},
            time_global_range={"Vm": [0.0, 1.0]}, time_field="Vm",
        )
        assert 'id="cs-time-slider-fig_vm"' in html

    def test_time_labels_embedded(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.001", "0.005"], time_data_b64={"Vm": ["AA==", "BB=="]},
            time_global_range={"Vm": [0.0, 1.0]}, time_field="Vm",
        )
        assert "0.001" in html
        assert "0.005" in html
