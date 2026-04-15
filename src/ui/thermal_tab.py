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
    CUSTOM_LABEL, CUSTOM_ICON,
    get_active_profile, set_active_profile,
)
from backend.gpu_switch import (
    INTEGRATED, HYBRID, DEDICATED, MODE_LABELS,
    get_current_mode, set_mode, get_dgpu_power_info,
)
from backend.sensors import get_cpu_temp, get_amdgpu_temp, get_battery_status
from backend.tdp_control import apply_tdp, reset_tdp
from backend.custom_config import load_custom_config, save_custom_config
from ui.custom_profile_panel import CustomProfilePanel


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
        import cairo

        # Rounded background with subtle gradient
        cr.save()
        radius = 14
        cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
        cr.arc(w - radius, radius, radius, 3 * math.pi / 2, 0)
        cr.arc(w - radius, h - radius, radius, 0, math.pi / 2)
        cr.arc(radius, h - radius, radius, math.pi / 2, math.pi)
        cr.close_path()
        cr.set_source_rgb(0.1, 0.1, 0.1)
        cr.fill()
        cr.restore()

        margin_l = 50
        margin_r = 20
        margin_t = 14
        margin_b = 30
        gw = w - margin_l - margin_r
        gh = h - margin_t - margin_b

        # Grid lines
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.08)
        cr.set_line_width(1)
        for temp in range(20, 101, 10):
            x = self._temp_to_x(temp, w)
            cr.move_to(x, margin_t)
            cr.line_to(x, h - margin_b)
            cr.stroke()
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.4)
            cr.set_font_size(9)
            cr.move_to(x - 8, h - 10)
            cr.show_text(f"{temp}")
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.08)

        for pwm_pct in range(0, 101, 25):
            pwm = pwm_pct / 100.0 * 255
            y = self._pwm_to_y(pwm, h)
            cr.move_to(margin_l, y)
            cr.line_to(w - margin_r, y)
            cr.stroke()
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.4)
            cr.set_font_size(9)
            cr.move_to(5, y + 3)
            cr.show_text(f"{pwm_pct}%")
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.08)

        # Fill under curve
        cr.save()
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
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.06)
        cr.fill()
        cr.restore()

        # Curve line — white
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.9)
        cr.set_line_width(2.5)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        for i, (temp, pwm) in enumerate(self.points):
            x = self._temp_to_x(temp, w)
            y = self._pwm_to_y(pwm, h)
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()

        # Points
        for i, (temp, pwm) in enumerate(self.points):
            x = self._temp_to_x(temp, w)
            y = self._pwm_to_y(pwm, h)
            if i == self.dragging:
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.2)
                cr.arc(x, y, 10, 0, 2 * math.pi)
                cr.fill()
                cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
                radius = 6
            else:
                cr.set_source_rgba(0.6, 0.6, 0.6, 1.0)
                radius = 5
            cr.arc(x, y, radius, 0, 2 * math.pi)
            cr.fill()

            cr.set_source_rgba(1, 1, 1, 0.9)
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
        profile_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        profile_card.add_css_class("card-white")
        profile_card.set_margin_bottom(16)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title_box.set_margin_top(8)
        title_box.set_margin_start(8)

        title_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        title_hbox.set_halign(Gtk.Align.START)
        title_icon = Gtk.Image.new_from_icon_name("power-profile-balanced-symbolic")
        title_icon.set_pixel_size(16)
        title_hbox.append(title_icon)
        title_lbl = Gtk.Label(label="Power Profile")
        title_lbl.add_css_class("heading-md")
        title_hbox.append(title_lbl)
        title_box.append(title_hbox)

        self.profile_status_lbl = Gtk.Label(label=f"Current: {PROFILE_LABELS.get(get_active_profile(), get_active_profile())}")
        self.profile_status_lbl.set_halign(Gtk.Align.START)
        self.profile_status_lbl.add_css_class("heading-sm")
        title_box.append(self.profile_status_lbl)
        
        profile_card.append(title_box)
        content.append(profile_card)

        self.profile_buttons = {}
        profile_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        profile_box.set_halign(Gtk.Align.CENTER)
        profile_box.set_margin_bottom(8)

        current = get_active_profile()
        for profile in PROFILES:
            btn = Gtk.ToggleButton(label=PROFILE_LABELS[profile])
            btn.set_size_request(130, 45)
            btn.add_css_class("pill-toggle")
            if profile == current:
                btn.set_active(True)
            btn.connect("toggled", self._on_profile_toggled, profile)
            self.profile_buttons[profile] = btn
            profile_box.append(btn)

        # 4th button: Custom TDP
        custom_btn = Gtk.ToggleButton(label=CUSTOM_LABEL)
        custom_btn.set_size_request(130, 45)
        custom_btn.add_css_class("sf-font")
        custom_btn.add_css_class("pill")
        custom_btn.connect("toggled", self._on_custom_profile_toggled)
        self.profile_buttons["custom"] = custom_btn
        profile_box.append(custom_btn)

        profile_card.append(profile_box)

        # Custom TDP panel (hidden until "Custom" is toggled on)
        cfg = load_custom_config()
        self.custom_panel = CustomProfilePanel(
            on_apply=self._on_apply_custom_tdp,
            on_reset=self._on_reset_custom_tdp,
        )
        self.custom_panel.set_values(
            cfg["tdp"]["spl_w"],
            cfg["tdp"]["sppt_w"],
            cfg["tdp"]["fppt_w"],
        )
        self.custom_panel.set_visible(False)
        self.custom_panel.set_margin_top(4)
        self.custom_panel.set_margin_start(8)
        self.custom_panel.set_margin_end(8)
        profile_card.append(self.custom_panel)

        # --- GPU Mode Section ---
        gpu_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        gpu_card.add_css_class("card-white")
        gpu_card.set_margin_bottom(16)
        content.append(gpu_card)

        gpu_mode = get_current_mode()
        dgpu_info = get_dgpu_power_info()

        gpu_title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        gpu_title_box.set_margin_top(8)
        gpu_title_box.set_margin_start(8)
        
        gpu_title_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        gpu_title_hbox.set_halign(Gtk.Align.START)
        gpu_title_icon = Gtk.Image.new_from_icon_name("computer-symbolic")
        gpu_title_icon.set_pixel_size(16)
        gpu_title_hbox.append(gpu_title_icon)
        gpu_title_lbl = Gtk.Label(label="GPU Mode")
        gpu_title_lbl.add_css_class("heading-md")
        gpu_title_hbox.append(gpu_title_lbl)
        gpu_title_box.append(gpu_title_hbox)

        def _gpu_subtitle(info):
            parts = [
                f"Power: {info['power_state']}",
                f"Driver: {info['driver']}",
                f"envycontrol: {'available' if info['envycontrol_available'] else 'not installed'}",
            ]
            return " | ".join(parts)

        sub_text = _gpu_subtitle(dgpu_info)
        if not dgpu_info["envycontrol_available"]:
            sub_text = "envycontrol not installed — GPU switching unavailable. Run: pip install envycontrol"
        elif dgpu_info["driver"] == "nouveau":
            sub_text = "nouveau driver active — GPU switching may require a reboot after applying to take full effect."
        elif not dgpu_info["nvidia_available"]:
            sub_text = "NVIDIA kernel driver not installed — Hybrid and dGPU modes unavailable."

        self.gpu_status_lbl = Gtk.Label(label=sub_text)
        self.gpu_status_lbl.set_halign(Gtk.Align.START)
        self.gpu_status_lbl.add_css_class("heading-sm")
        self.gpu_status_lbl.set_wrap(True)
        gpu_title_box.append(self.gpu_status_lbl)
        
        gpu_card.append(gpu_title_box)

        self.gpu_buttons = {}
        gpu_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        gpu_box.set_halign(Gtk.Align.CENTER)
        gpu_box.set_margin_bottom(8)

        nouveau_active = dgpu_info["driver"] == "nouveau"
        nvidia_usable = dgpu_info["nvidia_available"] or dgpu_info["driver"] in ("nvidia", "nouveau")
        for mode in [INTEGRATED, HYBRID, DEDICATED]:
            btn = Gtk.ToggleButton(label=MODE_LABELS[mode])
            btn.set_size_request(160, 45)
            btn.add_css_class("pill-toggle")
            if mode == gpu_mode:
                btn.set_active(True)
            if mode in (HYBRID, DEDICATED) and not nvidia_usable:
                btn.set_sensitive(False)
                btn.set_tooltip_text("NVIDIA kernel driver not installed")
            btn.connect("toggled", self._on_gpu_toggled, mode)
            self.gpu_buttons[mode] = btn
            gpu_box.append(btn)

        gpu_card.append(gpu_box)

        # --- Fan Curves Section ---
        fan_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        fan_card.add_css_class("card-white")
        fan_card.set_margin_bottom(16)
        content.append(fan_card)

        fan_title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        fan_title_box.set_margin_top(8)
        fan_title_box.set_margin_start(8)
        
        fan_title_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fan_title_hbox.set_halign(Gtk.Align.START)
        fan_title_icon = Gtk.Image.new_from_icon_name("weather-windy-symbolic")
        fan_title_icon.set_pixel_size(16)
        fan_title_hbox.append(fan_title_icon)
        fan_title_lbl = Gtk.Label(label="Fan Curves")
        fan_title_lbl.add_css_class("heading-md")
        fan_title_hbox.append(fan_title_lbl)
        fan_title_box.append(fan_title_hbox)
        fan_card.append(fan_title_box)

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

        fan_card.append(profile_row)

        # Fan mapping swap setting
        swap_row = Adw.ActionRow(
            title="Swap Fan Mapping",
            subtitle="Switch which physical fan corresponds to which control curve",
        )
        self._swap_switch = Gtk.Switch()
        self._swap_switch.set_valign(Gtk.Align.CENTER)
        self._swap_switch.set_active(True)  # Default to True as it was hardcoded before
        self._swap_switch.connect("state-set", self._on_swap_toggled)
        swap_row.add_suffix(self._swap_switch)
        fan_card.append(swap_row)

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
            frame.set_margin_top(4)
            frame.set_margin_bottom(4)
            frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            frame_box.set_margin_top(8)
            frame_box.set_margin_bottom(8)
            frame_box.set_margin_start(8)
            frame_box.set_margin_end(8)

            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            title = Gtk.Label(label=f"{label} — {rpm} RPM")
            title.add_css_class("heading-sm")
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
            fan_card.append(row)

        # Store defaults on first launch
        init_defaults(self.fan_curves[1].points, self.fan_curves[2].points)

        # Apply button for fan curves
        apply_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        apply_box.set_halign(Gtk.Align.END)
        apply_box.set_margin_top(4)
        apply_box.set_margin_bottom(8)
        apply_box.set_margin_end(8)

        apply_btn = Gtk.Button(label="Apply Fan Curves")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply_fan_curves)
        apply_box.append(apply_btn)

        reset_btn = Gtk.Button(label="Reset to Default")
        reset_btn.add_css_class("flat")
        reset_btn.connect("clicked", self._on_reset_fan_curves)
        apply_box.append(reset_btn)

        fan_card.append(apply_box)

        # Temp display at bottom
        temp_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        temp_card.add_css_class("card-white")
        temp_card.set_margin_bottom(16)
        content.append(temp_card)
        
        temp_title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        temp_title_box.set_margin_top(8)
        temp_title_box.set_margin_start(8)
        
        temp_title_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        temp_title_hbox.set_halign(Gtk.Align.START)
        temp_title_icon = Gtk.Image.new_from_icon_name("temperature-symbolic")
        temp_title_icon.set_pixel_size(16)
        temp_title_hbox.append(temp_title_icon)
        temp_title_lbl = Gtk.Label(label="Temperatures")
        temp_title_lbl.add_css_class("heading-md")
        temp_title_hbox.append(temp_title_lbl)
        temp_title_box.append(temp_title_hbox)
        temp_card.append(temp_title_box)

        cpu_temp = get_cpu_temp()
        gpu_temp = get_amdgpu_temp()
        self.cpu_temp_row = Adw.ActionRow(
            title="CPU (k10temp)",
            subtitle=f"{cpu_temp:.1f} C" if cpu_temp else "N/A",
        )
        self.cpu_temp_row.add_prefix(Gtk.Image.new_from_icon_name("applications-system-symbolic"))
        self.gpu_temp_row = Adw.ActionRow(
            title="iGPU (amdgpu)",
            subtitle=f"{gpu_temp:.1f} C" if gpu_temp else "N/A",
        )
        self.gpu_temp_row.add_prefix(Gtk.Image.new_from_icon_name("display-brightness-symbolic"))
        temp_card.append(self.cpu_temp_row)
        temp_card.append(self.gpu_temp_row)

        # Update temps periodically
        GLib.timeout_add_seconds(2, self._update_temps)

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
        for fan_id, curve in self.fan_curves.items():
            curve.points = get_fan_curve(curve.curve_id) or list(curve.DEFAULT_POINTS)
            curve.queue_draw()
        return False

    def _on_profile_toggled(self, button, profile):
        if getattr(self, "_ignore_profile_toggles", False):
            return
        if not button.get_active():
            return
        self._ignore_profile_toggles = True
        try:
            # Hide custom panel when switching to a standard profile
            if hasattr(self, "custom_panel"):
                self.custom_panel.set_visible(False)
            # Unset others
            for p, btn in self.profile_buttons.items():
                if p != profile:
                    btn.set_active(False)
            ok, err = set_active_profile(profile)
            if ok:
                self.profile_status_lbl.set_label(f"Current: {PROFILE_LABELS[profile]}")
            else:
                self.profile_status_lbl.set_label(f"Error: {err}")
        finally:
            self._ignore_profile_toggles = False

    def _on_custom_profile_toggled(self, button):
        if getattr(self, "_ignore_profile_toggles", False):
            return
        self._ignore_profile_toggles = True
        try:
            # Deactivate standard profile buttons
            for key, btn in self.profile_buttons.items():
                if key != "custom":
                    btn.set_active(False)
        finally:
            self._ignore_profile_toggles = False

        if button.get_active():
            self.custom_panel.set_visible(True)
            self.profile_status_lbl.set_label("Profile: Custom")
        else:
            self.custom_panel.set_visible(False)

    def _on_apply_custom_tdp(self, spl, sppt, fppt):
        warnings = []
        if spl > 45:
            warnings.append(
                "Sustained TDP above 45 W may cause thermal throttling on extended workloads."
            )
        bat = get_battery_status()
        if bat == "Discharging" and spl > 20:
            warnings.append(
                "On battery, sustained TDP above 20 W will significantly reduce battery life."
            )

        if warnings:
            dialog = Adw.AlertDialog(
                heading="Confirm High TDP Settings",
                body="\n\n".join(warnings) + "\n\nProceed with applying?",
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("apply", "Apply Anyway")
            dialog.set_response_appearance("apply", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")
            dialog.choose(self.get_root(), None, self._on_tdp_dialog_response, (spl, sppt, fppt))
        else:
            self._do_apply_tdp(spl, sppt, fppt)

    def _on_tdp_dialog_response(self, dialog, result, user_data):
        response = dialog.choose_finish(result)
        if response == "apply":
            spl, sppt, fppt = user_data
            self._do_apply_tdp(spl, sppt, fppt)

    def _do_apply_tdp(self, spl, sppt, fppt):
        save_custom_config(spl, sppt, fppt, mark_applied=True)
        ok, err = apply_tdp(spl, sppt, fppt)
        root = self.get_root()
        if ok:
            root.show_notification(f"Custom TDP applied: {spl}/{sppt}/{fppt} W")
        else:
            dialog = Adw.AlertDialog(
                heading="TDP Apply Failed",
                body=err or "Unknown error applying TDP settings.",
            )
            dialog.add_response("ok", "OK")
            dialog.present(root)

    def _on_reset_custom_tdp(self):
        ok, err = reset_tdp()
        root = self.get_root()
        if ok:
            root.show_notification("TDP reset to firmware defaults")
        else:
            dialog = Adw.AlertDialog(
                heading="TDP Reset Failed",
                body=err or "Unknown error resetting TDP.",
            )
            dialog.add_response("ok", "OK")
            dialog.present(root)

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
        finally:
            self._ignore_gpu_toggles = False
            dialog = Adw.MessageDialog(
                heading="GPU Switch Failed",
                body=msg,
                transient_for=self.get_root(),
            )
            dialog.add_response("ok", "OK")
            dialog.present()

    def _on_fan_enable_toggled(self, switch, state, fan_id):
        if getattr(self, "_ignore_fan_toggles", False):
            return False

        curve = self.fan_curves.get(fan_id)
        if not curve:
            return True
        
        # If enabling, use apply_fan_curve to write current widget points
        # If disabling, just set enable to 0
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
        return True  # Prevent default handler

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
        canonical_points = self._get_default_mirrored_points()
        
        self._ignore_fan_toggles = getattr(self, "_ignore_fan_toggles", False)
        self._ignore_fan_toggles = True
        try:
            for fan_id, curve in self.fan_curves.items():
                set_fan_curve_enabled(curve.curve_id, False)
                toggle = self.fan_toggles[fan_id]
                toggle.set_active(False)
                curve.points = list(canonical_points)
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
            self._load_mirrored_default_points()
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

    def _load_mirrored_default_points(self):
        """Load the default curve into both fan widgets."""
        points = self._get_default_mirrored_points()
        for curve in self.fan_curves.values():
            curve.points = list(points)
            curve.dragging = -1
            curve.queue_draw()

    def _get_default_mirrored_points(self):
        """Return one default curve to apply to both fans.

        The first fan's default is treated as the canonical reset curve so
        resetting to Default mirrors the same config across both fans.
        """
        defaults = get_default()
        if defaults and defaults.get("fan1"):
            return list(defaults["fan1"])
        return list(self.fan_curves[1].DEFAULT_POINTS)

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
