"""Thermal & Power tab — fan curves, power profiles, GPU toggle."""

import gi
import math

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, GLib, Gdk, Graphene

from backend.fan_control import (
    get_fan_curve, get_fan_speeds, get_fan_labels,
    get_fan_curve_enabled, set_fan_curve, set_fan_curve_enabled,
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

    def __init__(self, fan_id):
        super().__init__()
        self.fan_id = fan_id
        self.points = get_fan_curve(fan_id) or [
            (30, 0), (40, 30), (50, 60), (60, 90),
            (70, 120), (80, 160), (90, 200), (100, 255),
        ]
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

        for mode in [INTEGRATED, HYBRID, DEDICATED]:
            btn = Gtk.ToggleButton(label=MODE_LABELS[mode])
            btn.set_size_request(160, 45)
            if mode == gpu_mode:
                btn.set_active(True)
            btn.connect("toggled", self._on_gpu_toggled, mode)
            btn.add_css_class("pill")
            self.gpu_buttons[mode] = btn
            gpu_box.append(btn)

        status_row = Adw.ActionRow(
            title="dGPU Status",
            subtitle=f"NVIDIA: {dgpu_info['power_state']} | Driver loaded: {dgpu_info['nvidia_loaded']}",
        )
        self.gpu_status_row = status_row
        gpu_group.add(status_row)

        gpu_wrapper = Adw.ActionRow()
        gpu_wrapper.set_child(gpu_box)
        gpu_group.add(gpu_wrapper)

        # --- Fan Curves Section ---
        fan_group = Adw.PreferencesGroup(title="Fan Curves")
        content.append(fan_group)

        labels = get_fan_labels()
        speeds = get_fan_speeds()

        self.fan_curves = {}
        self.fan_rpm_labels = {}
        for fan_id in (1, 2):
            label = labels.get(fan_id, f"Fan {fan_id}")
            rpm = speeds.get(fan_id, 0)

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

            enabled = get_fan_curve_enabled(fan_id)
            toggle = Gtk.Switch()
            toggle.set_active(enabled)
            toggle.set_valign(Gtk.Align.CENTER)
            toggle.set_halign(Gtk.Align.END)
            toggle.set_hexpand(True)
            toggle.set_tooltip_text("Enable custom fan curve")
            toggle.connect("state-set", self._on_fan_enable_toggled, fan_id)
            header.append(toggle)

            frame_box.append(header)

            curve = FanCurveWidget(fan_id)
            self.fan_curves[fan_id] = curve
            frame_box.append(curve)

            frame.set_child(frame_box)

            row = Adw.ActionRow()
            row.set_child(frame)
            fan_group.add(row)

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
            self.gpu_status_row.set_subtitle(f"Error: {msg}")

    def _on_fan_enable_toggled(self, switch, state, fan_id):
        ok, err = set_fan_curve_enabled(fan_id, state)
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
            ok, err = set_fan_curve(fan_id, curve.points)
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
        for fan_id, curve in self.fan_curves.items():
            curve.points = get_fan_curve(fan_id) or curve.points
            curve.queue_draw()

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
