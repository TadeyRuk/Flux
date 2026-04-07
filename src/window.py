"""Main application window with tab navigation."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, Gio

from ui.thermal_tab import ThermalTab
from ui.monitor_tab import MonitorTab
from ui.history_tab import HistoryTab


class PowerControlWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Flux")
        self.set_default_size(900, 650)

        # Main layout
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header bar
        header = Adw.HeaderBar()
        box.append(header)

        # Tab view
        self.tab_view = Adw.TabView()
        tab_bar = Adw.TabBar()
        tab_bar.set_view(self.tab_view)
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
        page3.set_icon(Gio.ThemedIcon.new("document-open-recent-symbolic"))

        self.set_content(box)

    def do_close_request(self):
        self.monitor_tab.stop()
        self.history_tab.stop()
        return False
