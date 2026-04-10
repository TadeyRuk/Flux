"""Thermal & Power tab — fan curves, power profiles, GPU toggle."""

import gi
import math

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, GLib, Gdk, Graphene

from backend.fan_control import (
    get_fan_curve, get_fan_speeds, get_fan_labels,
    get_fan_curve_enabled, set_fan_curve, set_fan_curve_enabled,
    get_curve_hwmon_labels, apply_fan_curve,
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

        # Quick status header
        header_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header_card.add_css_class("dashboard-header")

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Thermal and Power")
        title.add_css_class("title-3")
        title.add_css_class("panel-heading")
        title.set_halign(Gtk.Align.START)
        subtitle = Gtk.Label(label="Tune profiles, GPU mode, and fan curves from one place")
        subtitle.add_css_class("dim-label")
        subtitle.set_halign(Gtk.Align.START)
        title_box.append(title)
        title_box.append(subtitle)

        chip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chip_box.set_halign(Gtk.Align.END)
        chip_box.set_hexpand(True)
        self.profile_chip_label = Gtk.Label()
        self.profile_chip_label.add_css_class("subtle-chip")
        self.gpu_chip_label = Gtk.Label()
        self.gpu_chip_label.add_css_class("subtle-chip")
        chip_box.append(self.profile_chip_label)
        chip_box.append(self.gpu_chip_label)

        header_card.append(title_box)
        header_card.append(chip_box)
        content.append(header_card)

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
            btn.add_css_class("icon-pill")
            btn.set_child(self._make_button_content(
                PROFILE_LABELS[profile],
                PROFILE_ICONS.get(profile, "power-profile-balanced-symbolic"),
            ))
            if profile == current:
                btn.set_active(True)
            btn.connect("toggled", self._on_profile_toggled, profile)
            btn.add_css_class("pill")
            self.profile_buttons[profile] = btn
            profile_box.append(btn)

        row = Adw.ActionRow(title="Active Profile")
        row.set_subtitle(f"Current: {PROFILE_LABELS.get(current, current)}")
        row.add_prefix(Gtk.Image.new_from_icon_name("power-profile-performance-symbolic"))
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

        nouveau_active = dgpu_info["driver"] == "nouveau"
        nvidia_usable = dgpu_info["nvidia_available"] or dgpu_info["driver"] in ("nvidia", "nouveau")
        for mode in [INTEGRATED, HYBRID, DEDICATED]:
            btn = Gtk.ToggleButton(label=MODE_LABELS[mode])
            btn.set_size_request(160, 45)
            icon_name = {
                INTEGRATED: "computer-symbolic",
                HYBRID: "video-display-symbolic",
                DEDICATED: "video-card-symbolic",
            }.get(mode, "video-display-symbolic")
            btn.set_child(self._make_button_content(MODE_LABELS[mode], icon_name))
            btn.add_css_class("icon-pill")
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
        status_row.add_prefix(Gtk.Image.new_from_icon_name("video-card-symbolic"))
        if not dgpu_info["envycontrol_available"]:
            status_row.set_subtitle(
                "envycontrol not installed — GPU switching unavailable. "
                "Run: pip install envycontrol"
            )
        elif nouveau_active:
            status_row.set_subtitle(
                "nouveau driver active — GPU switching may require a reboot "
                "after applying to take full effect."
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
        profile_row.add_prefix(Gtk.Image.new_from_icon_name("document-properties-symbolic"))
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

        # Fan mapping swap setting
        swap_row = Adw.ActionRow(
            title="Swap Fan Mapping",
            subtitle="Switch which physical fan corresponds to which control curve",
        )
        swap_row.add_prefix(Gtk.Image.new_from_icon_name("object-flip-horizontal-symbolic"))
        self._swap_switch = Gtk.Switch()
        self._swap_switch.set_valign(Gtk.Align.CENTER)
        # Prefer native fan_id->pwm_id mapping by default; users can enable swap
        # for devices where firmware wiring is reversed.
        self._swap_switch.set_active(False)
        self._swap_switch.connect("state-set", self._on_swap_toggled)
        swap_row.add_suffix(self._swap_switch)
        fan_group.add(swap_row)

        self._update_curve_id_map()

        speeds = get_fan_speeds()
        labels = get_fan_labels()

        self.fan_curves = {}
        self.fan_toggles = {}
        self.fan_rpm_labels = {}
        for fan_id in (1, 2):
            label = labels.get(fan_id, f"Fan {fan_id}")
            rpm = speeds.get(fan_id, 0)
            curve_id = self._curve_id_map.get(fan_id, fan_id)

            frame = Gtk.Frame()
            frame.add_css_class("panel-card")
            frame.set_margin_top(4)
            frame.set_margin_bottom(4)
            frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            frame_box.set_margin_top(8)
            frame_box.set_margin_bottom(8)
            frame_box.set_margin_start(8)
            frame_box.set_margin_end(8)

            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            fan_icon = Gtk.Image.new_from_icon_name("preferences-system-symbolic")
            header.append(fan_icon)
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
        apply_btn.set_child(self._make_button_content("Apply Fan Curves", "object-select-symbolic"))
        apply_btn.connect("clicked", self._on_apply_fan_curves)
        apply_box.append(apply_btn)

        reset_btn = Gtk.Button(label="Reset to Default")
        reset_btn.add_css_class("flat")
        reset_btn.set_child(self._make_button_content("Reset to Default", "edit-undo-symbolic"))
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
        self.cpu_temp_row.add_prefix(Gtk.Image.new_from_icon_name("utilities-system-monitor-symbolic"))
        self.gpu_temp_row = Adw.ActionRow(
            title="iGPU (amdgpu)",
            subtitle=f"{gpu_temp:.1f} C" if gpu_temp else "N/A",
        )
        self.gpu_temp_row.add_prefix(Gtk.Image.new_from_icon_name("video-card-symbolic"))
        temp_group.add(self.cpu_temp_row)
        temp_group.add(self.gpu_temp_row)

        self.profile_chip_label.set_text(f"Profile: {PROFILE_LABELS.get(current, current)}")
        self.gpu_chip_label.set_text(f"GPU: {MODE_LABELS.get(gpu_mode, gpu_mode)}")

        # Update temps periodically
        GLib.timeout_add_seconds(2, self._update_temps)

    def _make_button_content(self, label, icon_name):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_halign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_valign(Gtk.Align.CENTER)
        text = Gtk.Label(label=label)
        text.add_css_class("metric-label")
        text.set_valign(Gtk.Align.CENTER)
        box.append(icon)
        box.append(text)
        return box

    def _update_curve_id_map(self):
        """Build curve_id mapping based on hardware labels or user swap setting."""
        labels = get_fan_labels()
        curve_labels = get_curve_hwmon_labels()
        self._curve_id_map = {}
        
        if curve_labels:
            # Use labels from curve hwmon to build correct mapping
            for fan_id, fan_label in labels.items():
                for pwm_id, curve_label in curve_labels.items():
                    if curve_label == fan_label:
                        self._curve_id_map[fan_id] = pwm_id
                        break
                else:
                    self._curve_id_map[fan_id] = fan_id
        else:
            # No curve hwmon labels: use user preference
            if self._swap_switch.get_active():
                self._curve_id_map = {1: 2, 2: 1}
            else:
                self._curve_id_map = {1: 1, 2: 2}
        
        # Update widget curve_ids if they exist
        if hasattr(self, "fan_curves"):
            for fan_id, curve in self.fan_curves.items():
                curve.curve_id = self._curve_id_map.get(fan_id, fan_id)

    def _on_swap_toggled(self, switch, state):
        self._update_curve_id_map()
        # Refresh current curve data from hardware with new mapping
        self._ignore_fan_toggles = getattr(self, "_ignore_fan_toggles", False)
        self._ignore_fan_toggles = True
        try:
            for fan_id, curve in self.fan_curves.items():
                curve.points = get_fan_curve(curve.curve_id) or list(curve.DEFAULT_POINTS)
                curve.queue_draw()
                # Keep switch state aligned with the newly mapped curve id.
                self.fan_toggles[fan_id].set_active(get_fan_curve_enabled(curve.curve_id))
        finally:
            self._ignore_fan_toggles = False
        return False

    def _on_profile_toggled(self, button, profile):
        if getattr(self, "_ignore_profile_toggles", False):
            return
        if not button.get_active():
            return
        self._ignore_profile_toggles = True
        try:
            # Unset others
            for p, btn in self.profile_buttons.items():
                if p != profile:
                    btn.set_active(False)
            ok, err = set_active_profile(profile)
            if ok:
                self.profile_status_row.set_subtitle(f"Current: {PROFILE_LABELS[profile]}")
                self.profile_chip_label.set_text(f"Profile: {PROFILE_LABELS[profile]}")
            else:
                self.profile_status_row.set_subtitle(f"Error: {err}")
        finally:
            self._ignore_profile_toggles = False

    def _on_gpu_toggled(self, button, mode):
        if getattr(self, "_ignore_gpu_toggles", False):
            return
        if not button.get_active():
            return
        
        self._ignore_gpu_toggles = True
        try:
            prev_mode = next((m for m, b in self.gpu_buttons.items() if b.get_active() and m != mode), None)
            for m, btn in self.gpu_buttons.items():
                if m != mode:
                    btn.set_active(False)

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
                button.set_active(False)
                if prev_mode and prev_mode in self.gpu_buttons:
                    self.gpu_buttons[prev_mode].set_active(True)
                dialog = Adw.MessageDialog(
                    heading="GPU Switch Failed",
                    body=msg,
                    transient_for=self.get_root(),
                )
                dialog.add_response("ok", "OK")
                dialog.present()
            else:
                self.gpu_chip_label.set_text(f"GPU: {MODE_LABELS.get(mode, mode)}")
        finally:
            self._ignore_gpu_toggles = False

    def _on_fan_enable_toggled(self, switch, state, fan_id):
        if getattr(self, "_ignore_fan_toggles", False):
            return False

        curve = self.fan_curves.get(fan_id)
        if not curve:
            return False
        
        # If enabling, use apply_fan_curve to write current widget points.
        # If disabling, switch controller out of custom curve mode.
        if state:
            ok, err = apply_fan_curve(curve.curve_id, curve.points, enabled=True)
        else:
            ok, err = set_fan_curve_enabled(curve.curve_id, False)
            
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
            return True  # Block state change on failure.

        return False  # Allow default handler on success.

    def _notify(self, message):
        root = self.get_root()
        if root and hasattr(root, "show_notification"):
            root.show_notification(message)

    def _on_apply_fan_curves(self, button):
        for fan_id, curve in self.fan_curves.items():
            # Use the new batched apply function which writes points THEN enables
            ok, err = apply_fan_curve(curve.curve_id, curve.points, enabled=True)
            if not ok:
                dialog = Adw.MessageDialog(
                    heading="Fan Curve Error",
                    body=f"Fan {fan_id} ({curve.curve_id}): {err}",
                    transient_for=self.get_root(),
                )
                dialog.add_response("ok", "OK")
                dialog.present()
                return

            # Verify values were persisted by reading them back from sysfs.
            readback = get_fan_curve(curve.curve_id)
            expected = [(int(t), int(p)) for t, p in curve.points]
            if readback[:len(expected)] != expected:
                dialog = Adw.MessageDialog(
                    heading="Fan Curve Verification Failed",
                    body=(
                        f"Fan {fan_id} ({curve.curve_id}) was applied but readback "
                        "does not match requested values."
                    ),
                    transient_for=self.get_root(),
                )
                dialog.add_response("ok", "OK")
                dialog.present()
                return

            if not get_fan_curve_enabled(curve.curve_id):
                dialog = Adw.MessageDialog(
                    heading="Fan Curve Verification Failed",
                    body=f"Fan {fan_id} ({curve.curve_id}) is not enabled after apply.",
                    transient_for=self.get_root(),
                )
                dialog.add_response("ok", "OK")
                dialog.present()
                return

        # Applying curves always enables them; keep switches in sync.
        self._ignore_fan_toggles = getattr(self, "_ignore_fan_toggles", False)
        self._ignore_fan_toggles = True
        try:
            for fan_id, toggle in self.fan_toggles.items():
                toggle.set_active(True)
        finally:
            self._ignore_fan_toggles = False

        self._notify("Fan curve configuration applied")

    def _on_reset_fan_curves(self, button):
        defaults = get_default()
        
        self._ignore_fan_toggles = getattr(self, "_ignore_fan_toggles", False)
        self._ignore_fan_toggles = True
        try:
            for fan_id, curve in self.fan_curves.items():
                set_fan_curve_enabled(curve.curve_id, False)
                toggle = self.fan_toggles[fan_id]
                toggle.set_active(False)
                if defaults and defaults.get(f"fan{fan_id}"):
                    curve.points = list(defaults[f"fan{fan_id}"])
                else:
                    curve.points = list(curve.DEFAULT_POINTS)
                curve.dragging = -1
                curve.queue_draw()
        finally:
            self._ignore_fan_toggles = False
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
            self._load_default_points()
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

    def _load_default_points(self):
        """Load per-fan default curves into the fan widgets."""
        defaults = get_default()
        for fan_id, curve in self.fan_curves.items():
            if defaults and defaults.get(f"fan{fan_id}"):
                curve.points = list(defaults[f"fan{fan_id}"])
            else:
                curve.points = list(curve.DEFAULT_POINTS)
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
