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

        # Tab view
        self.tab_view = Adw.TabView()
        tab_bar = Adw.TabBar()
        tab_bar.set_view(self.tab_view)
        tab_bar.add_css_class("flat")
        box.append(tab_bar)
        box.append(self.tab_view)

        # Add tabs
        self.thermal_tab = ThermalTab()
        page1 = self.tab_view.append(self.thermal_tab)
        page1.set_title("Thermal & Power")
        page1.set_icon(Gio.ThemedIcon.new("power-profile-performance-symbolic"))

        self.monitor_tab = MonitorTab()
        page2 = self.tab_view.append(self.monitor_tab)
        page2.set_title("System Monitor")
        page2.set_icon(Gio.ThemedIcon.new("utilities-system-monitor-symbolic"))

        self.history_tab = HistoryTab()
        page3 = self.tab_view.append(self.history_tab)
        page3.set_title("Resource History")
        page3.set_icon(Gio.ThemedIcon.new("view-statistics-symbolic"))

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(box)
        self.set_content(self.toast_overlay)

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
