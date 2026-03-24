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
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'id="cs-strip-fig_vm"' in html

    def test_lock_button_in_strip_when_show_lock(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'id="cs-btn-lock-fig_vm"' in html

    def test_lock_button_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert 'id="cs-btn-lock-fig_vm"' not in html

    def test_axes_button_present_when_show_orientation(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-btn-axes-fig_vm"' in html

    def test_axes_button_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert 'id="cs-btn-axes-fig_vm"' not in html

    def test_field_button_present_when_multiple_fields(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert 'id="cs-btn-field-fig_vm"' in html

    def test_field_button_absent_when_single_field(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm"], active_field="Vm",
            field_data_b64={"Vm": "AA=="}, field_ranges={"Vm": [0,1]},
        )
        assert 'id="cs-btn-field-fig_vm"' not in html

    def test_time_button_present_when_time_data(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.0", "0.5"], time_data_b64=["AA==", "BB=="],
            time_global_range=[0.0, 1.0], time_field="Vm",
        )
        assert 'id="cs-btn-time-fig_vm"' in html

    def test_time_button_absent_when_no_time(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert 'id="cs-btn-time-fig_vm"' not in html

    def test_popup_panels_present_for_active_features(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True, show_orientation=True)
        assert 'id="cs-pop-lock-fig_vm"' in html
        assert 'id="cs-pop-axes-fig_vm"' in html


class TestControlsStripJs:
    def test_toggle_function_defined(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "csToggle_fig_vm" in html

    def test_toggle_references_popup_ids(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "cs-pop-" in html

    def test_hyphens_replaced_in_js_identifier(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("ts-vm-0")
        assert "csToggle_ts_vm_0" in html
        assert "csToggle_ts-vm-0" not in html

    def test_locked_always_declared(self):
        """_locked must be declared even when show_lock_btn=False (used by _sendCam)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert "var _locked=false" in html or "var _locked = false" in html

    def test_show_badge_always_declared(self):
        """_showBadge must exist even when show_lock_btn=False (called by camera-ack handler)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert "_showBadge" in html


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

    def test_wildcard_ack_accepted(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'fig_id!=="*"' in html or 'fig_id !== "*"' in html

    def test_send_camera_on_pointerup(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "pointerup" in html

    def test_lock_toggle_sends_postmessage(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert "4dpaper-lock-toggle" in html


class TestControlsStripOrientationLogic:
    def test_axes_svg_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-svg-axes-fig_vm"' in html

    def test_preset_view_function_defined(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "csSetView_fig_vm" in html

    def test_preset_buttons_call_set_view(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "csSetView_fig_vm('iso')" in html or 'csSetView_fig_vm("iso")' in html

    def test_axes_raf_loop_present(self):
        """Axes rAF loop (_axLoop) must exist when show_orientation=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "_axLoop" in html

    def test_axes_raf_loop_absent_when_hidden(self):
        """When show_orientation=False, _axLoop must not be emitted."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert "_axLoop" not in html


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
            time_labels=["0.0", "0.5", "1.0"], time_data_b64=["AA==", "BB==", "CC=="],
            time_global_range=[0.0, 1.0], time_field="Vm",
        )
        assert 'id="cs-time-slider-fig_vm"' in html

    def test_time_labels_embedded(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.001", "0.005"], time_data_b64=["AA==", "BB=="],
            time_global_range=[0.0, 1.0], time_field="Vm",
        )
        assert "0.001" in html
        assert "0.005" in html
