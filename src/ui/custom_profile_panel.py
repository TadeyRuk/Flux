"""Custom TDP profile panel — 3 sliders for CPU power limits."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from backend.tdp_control import TDP_BACKEND


class CustomProfilePanel(Gtk.Box):
    """Panel shown when the 'Custom' power profile button is active.

    Exposes three TDP sliders (SPL, SPPT, FPPT) with constraint enforcement
    and Apply / Reset buttons. Calls `on_apply(spl, sppt, fppt)` and
    `on_reset()` callbacks — validation and hardware writes happen in the
    parent (ThermalTab) so dialogs have a proper window parent.
    """

    _SPL_MIN, _SPL_MAX   = 15, 54
    _SPPT_MIN, _SPPT_MAX = 15, 54
    _FPPT_MIN, _FPPT_MAX = 15, 65

    def __init__(self, on_apply, on_reset):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._on_apply_cb = on_apply
        self._on_reset_cb = on_reset
        self._updating = False  # guard against recursive value-changed loops

        self.set_margin_top(12)
        self.set_margin_bottom(4)
        self.set_margin_start(0)
        self.set_margin_end(0)

        # --- Info banner ---
        info_lbl = Gtk.Label(
            label="Changes apply to this session only \u2014 resets automatically on reboot."
        )
        info_lbl.add_css_class("dim-label")
        info_lbl.add_css_class("sf-font")
        info_lbl.set_wrap(True)
        info_lbl.set_halign(Gtk.Align.START)
        info_lbl.set_margin_bottom(10)
        self.append(info_lbl)

        # --- Sliders ---
        self._spl_scale,  self._spl_lbl  = self._make_slider_row(
            "SPL", "Slow Package Power Tracking (STAPM)",
            self._SPL_MIN, self._SPL_MAX, 25,
            self._on_spl_changed,
        )
        self._sppt_scale, self._sppt_lbl = self._make_slider_row(
            "SPPT", "Actual Package Power Limit",
            self._SPPT_MIN, self._SPPT_MAX, 30,
            self._on_sppt_changed,
        )
        self._fppt_scale, self._fppt_lbl = self._make_slider_row(
            "FPPT", "Fast Package Power Tracking (Boost)",
            self._FPPT_MIN, self._FPPT_MAX, 35,
            self._on_fppt_changed,
        )

        # --- Backend status ---
        backend_text = {
            "asus-wmi": "Backend: asus-nb-wmi",
            "ryzenadj": "Backend: ryzenadj",
            None: "Warning: no TDP backend found \u2014 apply will have no effect",
        }[TDP_BACKEND]
        backend_lbl = Gtk.Label(label=backend_text)
        backend_lbl.add_css_class("dim-label")
        backend_lbl.add_css_class("sf-font")
        backend_lbl.set_halign(Gtk.Align.START)
        backend_lbl.set_margin_top(6)
        backend_lbl.set_margin_bottom(10)
        self.append(backend_lbl)

        # --- Buttons ---
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(4)

        reset_btn = Gtk.Button(label="Reset to Default")
        reset_btn.add_css_class("sf-font")
        reset_btn.connect("clicked", self._on_reset_clicked)
        btn_box.append(reset_btn)

        apply_btn = Gtk.Button(label="Apply Custom TDP")
        apply_btn.add_css_class("suggested-action")
        apply_btn.add_css_class("sf-font")
        apply_btn.connect("clicked", self._on_apply_clicked)
        btn_box.append(apply_btn)

        self.append(btn_box)

    # ------------------------------------------------------------------
    # Public API

    def get_values(self):
        """Return current slider values as (spl_w, sppt_w, fppt_w) ints."""
        return (
            int(self._spl_scale.get_value()),
            int(self._sppt_scale.get_value()),
            int(self._fppt_scale.get_value()),
        )

    def set_values(self, spl_w, sppt_w, fppt_w):
        """Load values into sliders without triggering constraint callbacks."""
        self._updating = True
        self._spl_scale.set_value(spl_w)
        self._sppt_scale.set_value(sppt_w)
        self._fppt_scale.set_value(fppt_w)
        self._update_labels()
        self._updating = False

    # ------------------------------------------------------------------
    # Internal helpers

    def _make_slider_row(self, short_name, description, min_w, max_w, default, handler):
        """Build a labeled slider row and append it to self."""
        row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row_box.set_margin_bottom(8)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        name_lbl = Gtk.Label(label=short_name)
        name_lbl.add_css_class("heading-md")
        name_lbl.add_css_class("sf-font")
        name_lbl.set_halign(Gtk.Align.START)

        desc_lbl = Gtk.Label(label=description)
        desc_lbl.add_css_class("dim-label")
        desc_lbl.add_css_class("sf-font")
        desc_lbl.set_halign(Gtk.Align.START)
        desc_lbl.set_hexpand(True)

        val_lbl = Gtk.Label(label=f"{default} W")
        val_lbl.add_css_class("sf-font")
        val_lbl.set_halign(Gtk.Align.END)
        val_lbl.set_width_chars(6)

        header.append(name_lbl)
        header.append(desc_lbl)
        header.append(val_lbl)
        row_box.append(header)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min_w, max_w, 1)
        scale.set_value(default)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        scale.connect("value-changed", handler)
        row_box.append(scale)

        self.append(row_box)
        return scale, val_lbl

    def _update_labels(self):
        self._spl_lbl.set_label(f"{int(self._spl_scale.get_value())} W")
        self._sppt_lbl.set_label(f"{int(self._sppt_scale.get_value())} W")
        self._fppt_lbl.set_label(f"{int(self._fppt_scale.get_value())} W")

    def _on_spl_changed(self, scale):
        if self._updating:
            return
        self._updating = True
        spl = scale.get_value()
        # SPPT must be >= SPL
        if self._sppt_scale.get_value() < spl:
            self._sppt_scale.set_value(spl)
        # FPPT must be >= SPPT
        if self._fppt_scale.get_value() < self._sppt_scale.get_value():
            self._fppt_scale.set_value(self._sppt_scale.get_value())
        self._update_labels()
        self._updating = False

    def _on_sppt_changed(self, scale):
        if self._updating:
            return
        self._updating = True
        sppt = scale.get_value()
        # SPL must be <= SPPT
        if self._spl_scale.get_value() > sppt:
            self._spl_scale.set_value(sppt)
        # FPPT must be >= SPPT
        if self._fppt_scale.get_value() < sppt:
            self._fppt_scale.set_value(sppt)
        self._update_labels()
        self._updating = False

    def _on_fppt_changed(self, scale):
        if self._updating:
            return
        self._updating = True
        fppt = scale.get_value()
        # SPPT must be <= FPPT
        if self._sppt_scale.get_value() > fppt:
            self._sppt_scale.set_value(fppt)
        # SPL must be <= SPPT
        if self._spl_scale.get_value() > self._sppt_scale.get_value():
            self._spl_scale.set_value(self._sppt_scale.get_value())
        self._update_labels()
        self._updating = False

    def _on_apply_clicked(self, button):
        spl, sppt, fppt = self.get_values()
        self._on_apply_cb(spl, sppt, fppt)

    def _on_reset_clicked(self, button):
        self._on_reset_cb()
