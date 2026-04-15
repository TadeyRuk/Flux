"""Main application window with tab navigation."""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, Gio

from app_meta import (
    APP_ID,
    APP_NAME,
    APP_TAGLINE,
    APP_VERSION,
    APP_CREATOR,
    APP_COPYRIGHT,
    APP_DESCRIPTION,
)
from ui.thermal_tab import ThermalTab
from ui.monitor_tab import MonitorTab
from ui.history_tab import HistoryTab


class PowerControlWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title(APP_NAME)
        self.set_default_size(980, 700)

        # Main layout
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Header bar
        header = Adw.HeaderBar()
        title = Adw.WindowTitle(title=APP_NAME, subtitle=APP_TAGLINE)
        header.set_title_widget(title)

        logo_path = Path(__file__).resolve().parent.parent / "flux.svg"
        logo = Gtk.Picture.new_for_filename(str(logo_path))
        logo.set_size_request(24, 24)
        logo.set_can_shrink(True)
        logo.set_content_fit(Gtk.ContentFit.CONTAIN)
        logo.set_valign(Gtk.Align.CENTER)

        about_button = Gtk.Button()
        about_button.add_css_class("flat")
        about_button.set_has_frame(False)
        about_button.set_tooltip_text("About Flux")
        about_button.set_child(logo)
        about_button.connect("clicked", self._on_about_clicked)
        header.pack_start(about_button)

        box.append(header)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # Add tabs
        self.thermal_tab = ThermalTab()
        self.stack.add_named(self.thermal_tab, "thermal")

        self.monitor_tab = MonitorTab()
        self.stack.add_named(self.monitor_tab, "monitor")

        self.history_tab = HistoryTab()
        self.stack.add_named(self.history_tab, "history")

        self.overlay = Gtk.Overlay()
        self.overlay.set_child(self.stack)

        # Nav bar
        self.nav_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.nav_bar.add_css_class("bottom-nav")
        self.nav_bar.set_halign(Gtk.Align.CENTER)
        self.nav_bar.set_valign(Gtk.Align.END)
        self.nav_bar.set_margin_bottom(24)

        # Create buttons
        self.nav_buttons = {}
        for name, icon in [
            ("thermal", "temperature-symbolic"),
            ("monitor", "system-run-symbolic"),
            ("history", "office-calendar-symbolic"),
        ]:
            btn = Gtk.ToggleButton(icon_name=icon)
            btn.add_css_class("nav-btn")
            btn.connect("toggled", self._on_nav_toggled, name)
            self.nav_bar.append(btn)
            self.nav_buttons[name] = btn

        self.nav_buttons["thermal"].set_active(True)
        self.overlay.add_overlay(self.nav_bar)

        box.append(self.overlay)
        box.set_vexpand(True)
        self.overlay.set_vexpand(True)

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(box)
        self.set_content(self.toast_overlay)

    def _on_nav_toggled(self, button, name):
        if button.get_active():
            self.stack.set_visible_child_name(name)
            for other_name, other_btn in self.nav_buttons.items():
                if other_name != name and other_btn.get_active():
                    other_btn.set_active(False)

    def show_notification(self, message, timeout=3):
        toast = Adw.Toast.new(message)
        toast.set_timeout(timeout)
        self.toast_overlay.add_toast(toast)

    def _on_about_clicked(self, _button):
        about = Adw.AboutWindow(
            transient_for=self,
            application_name=APP_NAME,
            application_icon="flux",
            developer_name=APP_CREATOR,
            version=f"v{APP_VERSION}",
            comments=APP_DESCRIPTION,
            copyright=APP_COPYRIGHT,
        )
        about.set_release_notes_version(f"v{APP_VERSION}")
        about.add_credit_section(
            "Production Features",
            [
                "Power profile switching",
                "GPU mode switching",
                "Custom fan curve control",
                "Live monitor and resource history",
            ],
        )
        about.set_debug_info(
            f"Creator: {APP_CREATOR}\n"
            f"Version: v{APP_VERSION}\n"
            f"Application ID: {APP_ID}"
        )
        about.present()

    def do_close_request(self):
        self.monitor_tab.stop()
        self.history_tab.stop()
        return False
