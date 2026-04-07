"""Thermal & Power tab — fan curves, power profiles, GPU toggle."""

import gi
import math

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, GLib, Gdk, Graphene

from backend.fan_control import (
    get_fan_curve, get_fan_speeds, get_fan_labels,
    get_fan_curve_enabled, set_fan_curve, set_fan_curve_enabled,
    get_curve_hwmon_labels,
)
from backend.fan_profiles import (
    init_defaults, get_default, get_profile_names,
    get_profile, save_profile, delete_profile,
)
from backend.power_profile import (
    PROFILES, PROFILE_LABELS, PROFILE_ICONS,
    get_active_profile, set_active_profile,
)
from backend.gpu_switch import (
    INTEGRATED, HYBRID, DEDICATED, MODE_LABELS,
    get_current_mode, set_mode, get_dgpu_power_info,
)
from backend.sensors import get_cpu_temp, get_amdgpu_temp


class FanCurveWidget(Gtk.DrawingArea):
    """Interactive fan curve graph with draggable points."""

    def __init__(self, fan_id, curve_id=None):
        super().__init__()
        self.fan_id = fan_id
        self.curve_id = curve_id if curve_id is not None else fan_id
        self.DEFAULT_POINTS = [
            (30, 0), (40, 30), (50, 60), (60, 90),
            (70, 120), (80, 160), (90, 200), (100, 255),
        ]
        self.points = get_fan_curve(self.curve_id) or list(self.DEFAULT_POINTS)
        self.dragging = -1
        self.set_size_request(400, 220)
        self.set_draw_func(self._draw)
        self.set_hexpand(True)

        # Drag handling
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        self._drag_start_x = 0
        self._drag_start_y = 0

    def _temp_to_x(self, temp, w):
        margin = 50
        return margin + (temp - 20) / 80.0 * (w - margin - 20)

    def _pwm_to_y(self, pwm, h):
        margin_top = 10
        margin_bot = 30
        return margin_top + (1.0 - pwm / 255.0) * (h - margin_top - margin_bot)

    def _x_to_temp(self, x, w):
        margin = 50
        return 20 + (x - margin) / (w - margin - 20) * 80.0

    def _y_to_pwm(self, y, h):
        margin_top = 10
        margin_bot = 30
        return (1.0 - (y - margin_top) / (h - margin_top - margin_bot)) * 255.0

    def _draw(self, area, cr, w, h):
        # Background
        cr.set_source_rgb(0.12, 0.12, 0.14)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        margin_l = 50
        margin_r = 20
        margin_t = 10
        margin_b = 30
        gw = w - margin_l - margin_r
        gh = h - margin_t - margin_b

        # Grid lines
        cr.set_source_rgba(0.3, 0.3, 0.35, 0.5)
        cr.set_line_width(0.5)
        for temp in range(20, 101, 10):
            x = self._temp_to_x(temp, w)
            cr.move_to(x, margin_t)
            cr.line_to(x, h - margin_b)
            cr.stroke()
            # Label
            cr.set_source_rgba(0.6, 0.6, 0.65, 1)
            cr.set_font_size(9)
            cr.move_to(x - 8, h - 10)
            cr.show_text(f"{temp}")
            cr.set_source_rgba(0.3, 0.3, 0.35, 0.5)

        for pwm_pct in range(0, 101, 25):
            pwm = pwm_pct / 100.0 * 255
            y = self._pwm_to_y(pwm, h)
            cr.move_to(margin_l, y)
            cr.line_to(w - margin_r, y)
            cr.stroke()
            cr.set_source_rgba(0.6, 0.6, 0.65, 1)
            cr.set_font_size(9)
            cr.move_to(5, y + 3)
            cr.show_text(f"{pwm_pct}%")
            cr.set_source_rgba(0.3, 0.3, 0.35, 0.5)

        # Curve line
        cr.set_source_rgba(0.35, 0.7, 1.0, 0.9)
        cr.set_line_width(2.5)
        for i, (temp, pwm) in enumerate(self.points):
            x = self._temp_to_x(temp, w)
            y = self._pwm_to_y(pwm, h)
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()

        # Fill under curve
        cr.set_source_rgba(0.35, 0.7, 1.0, 0.08)
        for i, (temp, pwm) in enumerate(self.points):
            x = self._temp_to_x(temp, w)
            y = self._pwm_to_y(pwm, h)
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        last_x = self._temp_to_x(self.points[-1][0], w)
        first_x = self._temp_to_x(self.points[0][0], w)
        cr.line_to(last_x, h - margin_b)
        cr.line_to(first_x, h - margin_b)
        cr.close_path()
        cr.fill()

        # Points
        for i, (temp, pwm) in enumerate(self.points):
            x = self._temp_to_x(temp, w)
            y = self._pwm_to_y(pwm, h)
            if i == self.dragging:
                cr.set_source_rgba(1.0, 0.6, 0.2, 1)
                radius = 7
            else:
                cr.set_source_rgba(0.35, 0.7, 1.0, 1)
                radius = 5
            cr.arc(x, y, radius, 0, 2 * math.pi)
            cr.fill()

            # White border
            cr.set_source_rgba(1, 1, 1, 0.8)
            cr.set_line_width(1.5)
            cr.arc(x, y, radius, 0, 2 * math.pi)
            cr.stroke()

    def _find_point(self, x, y):
        w = self.get_width()
        h = self.get_height()
        for i, (temp, pwm) in enumerate(self.points):
            px = self._temp_to_x(temp, w)
            py = self._pwm_to_y(pwm, h)
            if (x - px) ** 2 + (y - py) ** 2 < 225:  # 15px radius
                return i
        return -1

    def _on_drag_begin(self, gesture, start_x, start_y):
        self._drag_start_x = start_x
        self._drag_start_y = start_y
        self.dragging = self._find_point(start_x, start_y)
        self.queue_draw()

    def _on_drag_update(self, gesture, offset_x, offset_y):
        if self.dragging < 0:
            return
        w = self.get_width()
        h = self.get_height()
        x = self._drag_start_x + offset_x
        y = self._drag_start_y + offset_y

        temp = max(20, min(100, self._x_to_temp(x, w)))
        pwm = max(0, min(255, self._y_to_pwm(y, h)))

        # Enforce ordering: can't cross neighbors
        if self.dragging > 0:
            temp = max(temp, self.points[self.dragging - 1][0] + 1)
        if self.dragging < len(self.points) - 1:
            temp = min(temp, self.points[self.dragging + 1][0] - 1)

        self.points[self.dragging] = (int(temp), int(pwm))
        self.queue_draw()

    def _on_drag_end(self, gesture, offset_x, offset_y):
        self.dragging = -1
        self.queue_draw()


class ThermalTab(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.append(scroll)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(4)
        scroll.set_child(content)

        # --- Power Profile Section ---
        profile_group = Adw.PreferencesGroup(title="Power Profile")
        content.append(profile_group)

        self.profile_buttons = {}
        profile_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        profile_box.set_halign(Gtk.Align.CENTER)
        profile_box.set_margin_top(8)
        profile_box.set_margin_bottom(8)

        current = get_active_profile()
        for profile in PROFILES:
            btn = Gtk.ToggleButton(label=PROFILE_LABELS[profile])
            btn.set_size_request(130, 45)
            if profile == current:
                btn.set_active(True)
            btn.connect("toggled", self._on_profile_toggled, profile)
            btn.add_css_class("pill")
            self.profile_buttons[profile] = btn
            profile_box.append(btn)

        row = Adw.ActionRow(title="Active Profile")
        row.set_subtitle(f"Current: {PROFILE_LABELS.get(current, current)}")
        self.profile_status_row = row
        profile_group.add(row)

        wrapper = Adw.ActionRow()
        wrapper.set_child(profile_box)
        profile_group.add(wrapper)

        # --- GPU Mode Section ---
        gpu_group = Adw.PreferencesGroup(title="GPU Mode")
        content.append(gpu_group)

        gpu_mode = get_current_mode()
        dgpu_info = get_dgpu_power_info()

        self.gpu_buttons = {}
        gpu_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        gpu_box.set_halign(Gtk.Align.CENTER)
        gpu_box.set_margin_top(8)
        gpu_box.set_margin_bottom(8)

        nvidia_usable = dgpu_info["nvidia_available"] or dgpu_info["driver"] in ("nvidia", "nouveau")
        for mode in [INTEGRATED, HYBRID, DEDICATED]:
            btn = Gtk.ToggleButton(label=MODE_LABELS[mode])
            btn.set_size_request(160, 45)
            if mode == gpu_mode:
                btn.set_active(True)
            if mode in (HYBRID, DEDICATED) and not nvidia_usable:
                btn.set_sensitive(False)
                btn.set_tooltip_text("NVIDIA kernel driver not installed")
            btn.connect("toggled", self._on_gpu_toggled, mode)
            btn.add_css_class("pill")
            self.gpu_buttons[mode] = btn
            gpu_box.append(btn)

        def _gpu_subtitle(info):
            parts = [
                f"Power: {info['power_state']}",
                f"Driver: {info['driver']}",
                f"envycontrol: {'available' if info['envycontrol_available'] else 'not installed'}",
            ]
            return " | ".join(parts)

        status_row = Adw.ActionRow(
            title="dGPU (NVIDIA RTX)",
            subtitle=_gpu_subtitle(dgpu_info),
        )
        if not dgpu_info["envycontrol_available"]:
            status_row.set_subtitle(
                "envycontrol not installed — GPU switching unavailable. "
                "Run: pip install envycontrol"
            )
        elif not dgpu_info["nvidia_available"]:
            status_row.set_subtitle(
                "NVIDIA kernel driver not installed — "
                "Hybrid and dGPU modes unavailable."
            )
        self.gpu_status_row = status_row
        gpu_group.add(status_row)

        gpu_wrapper = Adw.ActionRow()
        gpu_wrapper.set_child(gpu_box)
        gpu_group.add(gpu_wrapper)

        # --- Fan Curves Section ---
        fan_group = Adw.PreferencesGroup(title="Fan Curves")
        content.append(fan_group)

        # Profile selector row
        profile_row = Adw.ActionRow(title="Profile")
        self._profile_model = Gtk.StringList()
        self._rebuild_profile_model()
        self._profile_dropdown = Gtk.DropDown(model=self._profile_model)
        self._profile_dropdown.set_valign(Gtk.Align.CENTER)
        self._profile_dropdown.connect("notify::selected", self._on_profile_selected)
        profile_row.add_suffix(self._profile_dropdown)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_valign(Gtk.Align.CENTER)
        add_btn.set_tooltip_text("Save current curves as a new profile")
        add_btn.connect("clicked", self._on_add_profile)
        profile_row.add_suffix(add_btn)

        self._delete_btn = Gtk.Button(icon_name="user-trash-symbolic")
        self._delete_btn.set_valign(Gtk.Align.CENTER)
        self._delete_btn.set_tooltip_text("Delete selected profile")
        self._delete_btn.set_sensitive(False)
        self._delete_btn.connect("clicked", self._on_delete_profile)
        profile_row.add_suffix(self._delete_btn)

        fan_group.add(profile_row)

        # Build curve_id mapping: fan labels from asus hwmon may not match
        # the pwm indices in asus_custom_fan_curve hwmon.
        # On this hardware, cpu_fan (fan1 label) is controlled by pwm2 and vice versa.
        labels = get_fan_labels()
        curve_labels = get_curve_hwmon_labels()
        if curve_labels:
            # Use labels from curve hwmon to build correct mapping
            self._curve_id_map = {}
            for fan_id, fan_label in labels.items():
                for pwm_id, curve_label in curve_labels.items():
                    if curve_label == fan_label:
                        self._curve_id_map[fan_id] = pwm_id
                        break
                else:
                    self._curve_id_map[fan_id] = fan_id
        else:
            # No curve hwmon labels: swap mapping (confirmed on ASUS hardware)
            self._curve_id_map = {1: 2, 2: 1}

        speeds = get_fan_speeds()

        self.fan_curves = {}
        self.fan_toggles = {}
        self.fan_rpm_labels = {}
        for fan_id in (1, 2):
            label = labels.get(fan_id, f"Fan {fan_id}")
            rpm = speeds.get(fan_id, 0)
            curve_id = self._curve_id_map.get(fan_id, fan_id)

            frame = Gtk.Frame()
            frame.set_margin_top(4)
            frame.set_margin_bottom(4)
            frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            frame_box.set_margin_top(8)
            frame_box.set_margin_bottom(8)
            frame_box.set_margin_start(8)
            frame_box.set_margin_end(8)

            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            title = Gtk.Label(label=f"{label} — {rpm} RPM")
            title.add_css_class("heading")
            title.set_halign(Gtk.Align.START)
            self.fan_rpm_labels[fan_id] = (title, label)
            header.append(title)

            enabled = get_fan_curve_enabled(curve_id)
            toggle = Gtk.Switch()
            toggle.set_active(enabled)
            toggle.set_valign(Gtk.Align.CENTER)
            toggle.set_halign(Gtk.Align.END)
            toggle.set_hexpand(True)
            toggle.set_tooltip_text("Enable custom fan curve")
            toggle.connect("state-set", self._on_fan_enable_toggled, fan_id)
            self.fan_toggles[fan_id] = toggle
            header.append(toggle)

            frame_box.append(header)

            curve = FanCurveWidget(fan_id, curve_id=curve_id)
            self.fan_curves[fan_id] = curve
            frame_box.append(curve)

            frame.set_child(frame_box)

            row = Adw.ActionRow()
            row.set_child(frame)
            fan_group.add(row)

        # Store defaults on first launch
        init_defaults(self.fan_curves[1].points, self.fan_curves[2].points)

        # Apply button for fan curves
        apply_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        apply_box.set_halign(Gtk.Align.END)
        apply_box.set_margin_top(4)

        apply_btn = Gtk.Button(label="Apply Fan Curves")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply_fan_curves)
        apply_box.append(apply_btn)

        reset_btn = Gtk.Button(label="Reset to Default")
        reset_btn.add_css_class("flat")
        reset_btn.connect("clicked", self._on_reset_fan_curves)
        apply_box.append(reset_btn)

        content.append(apply_box)

        # Temp display at bottom
        temp_group = Adw.PreferencesGroup(title="Temperatures")
        content.append(temp_group)

        cpu_temp = get_cpu_temp()
        gpu_temp = get_amdgpu_temp()
        self.cpu_temp_row = Adw.ActionRow(
            title="CPU (k10temp)",
            subtitle=f"{cpu_temp:.1f} C" if cpu_temp else "N/A",
        )
        self.gpu_temp_row = Adw.ActionRow(
            title="iGPU (amdgpu)",
            subtitle=f"{gpu_temp:.1f} C" if gpu_temp else "N/A",
        )
        temp_group.add(self.cpu_temp_row)
        temp_group.add(self.gpu_temp_row)

        # Update temps periodically
        GLib.timeout_add_seconds(2, self._update_temps)

    def _on_profile_toggled(self, button, profile):
        if not button.get_active():
            return
        # Unset others
        for p, btn in self.profile_buttons.items():
            if p != profile:
                btn.handler_block_by_func(self._on_profile_toggled)
                btn.set_active(False)
                btn.handler_unblock_by_func(self._on_profile_toggled)
        ok, err = set_active_profile(profile)
        if ok:
            self.profile_status_row.set_subtitle(f"Current: {PROFILE_LABELS[profile]}")
        else:
            self.profile_status_row.set_subtitle(f"Error: {err}")

    def _on_gpu_toggled(self, button, mode):
        if not button.get_active():
            return
        prev_mode = next((m for m, b in self.gpu_buttons.items() if b.get_active() and m != mode), None)
        for m, btn in self.gpu_buttons.items():
            if m != mode:
                btn.handler_block_by_func(self._on_gpu_toggled)
                btn.set_active(False)
                btn.handler_unblock_by_func(self._on_gpu_toggled)

        ok, msg, needs_reboot = set_mode(mode)
        if needs_reboot:
            dialog = Adw.MessageDialog(
                heading="Reboot Required",
                body=msg,
                transient_for=self.get_root(),
            )
            dialog.add_response("ok", "OK")
            dialog.present()
        elif not ok:
            # Revert button to previous mode
            button.handler_block_by_func(self._on_gpu_toggled)
            button.set_active(False)
            button.handler_unblock_by_func(self._on_gpu_toggled)
            if prev_mode and prev_mode in self.gpu_buttons:
                self.gpu_buttons[prev_mode].handler_block_by_func(self._on_gpu_toggled)
                self.gpu_buttons[prev_mode].set_active(True)
                self.gpu_buttons[prev_mode].handler_unblock_by_func(self._on_gpu_toggled)
            dialog = Adw.MessageDialog(
                heading="GPU Switch Failed",
                body=msg,
                transient_for=self.get_root(),
            )
            dialog.add_response("ok", "OK")
            dialog.present()

    def _on_fan_enable_toggled(self, switch, state, fan_id):
        curve_id = self._curve_id_map.get(fan_id, fan_id)
        ok, err = set_fan_curve_enabled(curve_id, state)
        if not ok:
            # Revert toggle without re-triggering signal
            GLib.idle_add(lambda: switch.set_active(not state))
            if err:
                dialog = Adw.MessageDialog(
                    heading="Fan Curve Error",
                    body=f"Could not {'enable' if state else 'disable'} fan curve: {err}",
                    transient_for=self.get_root(),
                )
                dialog.add_response("ok", "OK")
                dialog.present()
        return True  # Prevent default handler

    def _on_apply_fan_curves(self, button):
        for fan_id, curve in self.fan_curves.items():
            ok, err = set_fan_curve_enabled(curve.curve_id, True)
            if not ok:
                dialog = Adw.MessageDialog(
                    heading="Fan Curve Error",
                    body=f"Fan {fan_id} enable: {err}",
                    transient_for=self.get_root(),
                )
                dialog.add_response("ok", "OK")
                dialog.present()
                return
            ok, err = set_fan_curve(curve.curve_id, curve.points)
            if not ok:
                dialog = Adw.MessageDialog(
                    heading="Fan Curve Error",
                    body=f"Fan {fan_id}: {err}",
                    transient_for=self.get_root(),
                )
                dialog.add_response("ok", "OK")
                dialog.present()
                return

    def _on_reset_fan_curves(self, button):
        defaults = get_default()
        for fan_id, curve in self.fan_curves.items():
            set_fan_curve_enabled(curve.curve_id, False)
            toggle = self.fan_toggles[fan_id]
            toggle.handler_block_by_func(self._on_fan_enable_toggled)
            toggle.set_active(False)
            toggle.handler_unblock_by_func(self._on_fan_enable_toggled)
            if defaults:
                curve.points = list(defaults[f"fan{fan_id}"])
            else:
                curve.points = list(curve.DEFAULT_POINTS)
            curve.dragging = -1
            curve.queue_draw()
        # Select "Default" in dropdown
        self._profile_dropdown.set_selected(0)

    # --- Profile management ---

    def _rebuild_profile_model(self):
        """Rebuild the dropdown string list from stored profiles."""
        while self._profile_model.get_n_items() > 0:
            self._profile_model.remove(0)
        self._profile_model.append("Default")
        for name in get_profile_names():
            self._profile_model.append(name)

    def _on_profile_selected(self, dropdown, _pspec):
        idx = dropdown.get_selected()
        if idx == 0:
            # Default selected
            self._delete_btn.set_sensitive(False)
            defaults = get_default()
            if defaults:
                self._load_points(defaults)
        elif idx != Gtk.INVALID_LIST_POSITION:
            name = self._profile_model.get_string(idx)
            self._delete_btn.set_sensitive(True)
            prof = get_profile(name)
            if prof:
                self._load_points(prof)

    def _load_points(self, data):
        """Load fan curve points from a profile dict into the widgets."""
        for fan_id, curve in self.fan_curves.items():
            key = f"fan{fan_id}"
            if key in data:
                curve.points = list(data[key])
                curve.dragging = -1
                curve.queue_draw()

    def _on_add_profile(self, button):
        dialog = Adw.MessageDialog(
            heading="Save Fan Curve Profile",
            body="Enter a name for this fan curve profile:",
            transient_for=self.get_root(),
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("Profile name")
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        def on_response(dlg, response):
            if response != "save":
                return
            name = entry.get_text().strip()
            if not name:
                return
            save_profile(
                name,
                self.fan_curves[1].points,
                self.fan_curves[2].points,
            )
            self._rebuild_profile_model()
            # Select the newly added profile
            for i in range(self._profile_model.get_n_items()):
                if self._profile_model.get_string(i) == name:
                    self._profile_dropdown.set_selected(i)
                    break

        dialog.connect("response", on_response)
        dialog.present()

    def _on_delete_profile(self, button):
        idx = self._profile_dropdown.get_selected()
        if idx == 0 or idx == Gtk.INVALID_LIST_POSITION:
            return
        name = self._profile_model.get_string(idx)
        dialog = Adw.MessageDialog(
            heading="Delete Profile",
            body=f'Delete the profile "{name}"?',
            transient_for=self.get_root(),
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(dlg, response):
            if response != "delete":
                return
            delete_profile(name)
            self._rebuild_profile_model()
            self._profile_dropdown.set_selected(0)

        dialog.connect("response", on_response)
        dialog.present()

    def _update_temps(self):
        cpu_temp = get_cpu_temp()
        gpu_temp = get_amdgpu_temp()
        if cpu_temp is not None:
            self.cpu_temp_row.set_subtitle(f"{cpu_temp:.1f} C")
        if gpu_temp is not None:
            self.gpu_temp_row.set_subtitle(f"{gpu_temp:.1f} C")

        speeds = get_fan_speeds()
        for fan_id, (title_lbl, base_label) in self.fan_rpm_labels.items():
            rpm = speeds.get(fan_id, 0)
            title_lbl.set_text(f"{base_label} — {rpm} RPM")

        return True  # Keep timer alive
