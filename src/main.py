#!/usr/bin/env python3
"""Flux — ASUS Linux laptop power/thermal management."""

import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk, Gdk

from window import PowerControlWindow

CSS = b"""
.graph-frame {
    background: #1e1e22;
    border-radius: 8px;
    padding: 4px;
}
.proc-row {
    padding: 4px 8px;
    border-radius: 4px;
}
.proc-row:hover {
    background: alpha(@accent_color, 0.08);
}
"""


class PowerControlApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.flux.app",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.style_manager = Adw.StyleManager.get_default()
        self.style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

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
