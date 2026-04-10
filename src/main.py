#!/usr/bin/env python3
"""Flux — ASUS Linux laptop power/thermal management."""

import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk, Gdk

from app_meta import APP_ID
from window import PowerControlWindow

CSS = b"""
.app-badge {
    padding: 4px 10px;
    border-radius: 999px;
    background-color: #3a7bd5;
}

.dashboard-header {
    border-radius: 12px;
    padding: 12px;
    background-color: #2d4f83;
    border: 1px solid #3a7bd5;
}

.panel-card {
    border-radius: 12px;
    padding: 8px;
    background-color: #2a2a2d;
    border: 1px solid #4a4a4a;
}

.panel-heading {
    font-weight: 700;
    letter-spacing: 0.02em;
}

.icon-pill {
    border-radius: 999px;
    padding: 4px 10px;
}

.subtle-chip {
    border-radius: 8px;
    padding: 2px 8px;
    background-color: #4a4a4a;
}

.metric-label {
    font-weight: 600;
}

.proc-row {
    padding: 6px 8px;
    border-radius: 8px;
}

.proc-row:hover {
    background-color: #3a7bd5;
}

.danger-flat {
    color: #ef4444;
}
"""


class PowerControlApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.style_manager = Adw.StyleManager.get_default()
        self.style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

    def do_activate(self):
        # Load CSS
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        win = self.props.active_window
        if not win:
            win = PowerControlWindow(application=self)
        win.present()


def main():
    app = PowerControlApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
