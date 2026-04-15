#!/usr/bin/env python3
"""Flux — ASUS Linux laptop power/thermal management."""

import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk, Gdk

from window import PowerControlWindow

CSS = """
/* === Global === */
window {
    background-color: #0a0a0a;
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #e0e0e0;
}

headerbar {
    background-color: #111111;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    color: #e0e0e0;
}

headerbar title,
headerbar subtitle,
headerbar label {
    color: #e0e0e0;
}

/* === Bottom Nav === */
.bottom-nav {
    background-color: rgba(20, 20, 20, 0.97);
    border-radius: 999px;
    padding: 6px 10px;
    margin-bottom: 24px;
    border: 1px solid rgba(255, 255, 255, 0.08);
}

.nav-btn {
    border-radius: 999px;
    padding: 10px 14px;
    margin: 0 4px;
    background-color: transparent;
    color: rgba(255, 255, 255, 0.35);
    border: none;
    min-width: 44px;
    min-height: 44px;
}

.nav-btn:hover {
    background-color: rgba(255, 255, 255, 0.07);
    color: rgba(255, 255, 255, 0.75);
}

.nav-btn:checked {
    background-color: rgba(255, 255, 255, 0.14);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.15);
}

/* === Cards === */
.card,
.card-white {
    background-color: #1a1a1a;
    color: #e0e0e0;
    border-radius: 20px;
    padding: 20px;
    border: 1px solid rgba(255, 255, 255, 0.06);
}

.card-white label,
.card-white image,
.card-white .title {
    color: #e0e0e0;
}

.card-white button.destructive-action label,
.card-white button.destructive-action image {
    color: #ffffff;
}

.card-white .subtitle,
.card-white label.dim-label {
    color: rgba(224, 224, 224, 0.4);
}

/* === Typography === */
.heading-lg {
    font-size: 28px;
    font-weight: 800;
    letter-spacing: -0.025em;
    color: #ffffff;
}

.heading-md {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: #e0e0e0;
}

.heading-sm {
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.01em;
    color: rgba(224, 224, 224, 0.4);
}

.stat-number {
    font-size: 32px;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: #ffffff;
}

.stat-unit {
    font-size: 14px;
    font-weight: 600;
    color: rgba(224, 224, 224, 0.4);
}

/* === Toggle Pill Buttons === */
.pill-toggle {
    border-radius: 14px;
    padding: 8px 18px;
    background-color: rgba(255, 255, 255, 0.05);
    color: rgba(224, 224, 224, 0.5);
    font-weight: 600;
    font-size: 13px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    min-height: 40px;
}

.pill-toggle:hover {
    background-color: rgba(255, 255, 255, 0.09);
    color: #e0e0e0;
    border-color: rgba(255, 255, 255, 0.15);
}

.pill-toggle:checked {
    background-color: #333333;
    color: #ffffff;
    border-color: rgba(255, 255, 255, 0.2);
}

/* === Action Buttons === */
button.suggested-action {
    background-color: #2e2e2e;
    color: #ffffff;
    border-radius: 12px;
    padding: 8px 20px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    font-weight: 600;
    font-size: 13px;
}

button.suggested-action:hover {
    background-color: #3a3a3a;
}

button.flat {
    border-radius: 12px;
    color: rgba(224, 224, 224, 0.5);
    font-weight: 500;
    font-size: 13px;
    border: none;
    padding: 8px 16px;
    background-color: transparent;
}

button.flat:hover {
    background-color: rgba(255, 255, 255, 0.07);
    color: #e0e0e0;
}

button.flat.destructive-action {
    color: #ff6b6b;
}

button.flat.destructive-action:hover {
    background-color: rgba(255, 107, 107, 0.1);
}

/* === Process rows === */
.proc-row {
    padding: 8px 12px;
    border-radius: 12px;
    background-color: transparent;
    font-size: 13px;
}

.proc-row:hover {
    background-color: rgba(255, 255, 255, 0.05);
}

/* === Labels === */
.dim-label {
    color: rgba(224, 224, 224, 0.35);
    font-size: 12px;
}

label {
    color: #e0e0e0;
}

label.error {
    color: #ff6b6b;
    font-weight: 600;
}

label.warning {
    color: #ffab6b;
    font-weight: 600;
}

/* === Adw rows === */
row {
    background-color: transparent;
    border-radius: 12px;
    padding: 2px 0;
    color: #e0e0e0;
}

row:hover {
    background-color: rgba(255, 255, 255, 0.04);
}

row > box > label,
row label {
    color: #e0e0e0;
}

row .subtitle {
    color: rgba(224, 224, 224, 0.4);
}

/* === Scrolled windows === */
scrolledwindow,
scrolledwindow > viewport {
    background-color: transparent;
}

/* === Switches === */
switch:checked {
    background-color: #555555;
}

switch {
    background-color: rgba(255, 255, 255, 0.12);
}

/* === Dropdowns === */
dropdown button {
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    background-color: rgba(255, 255, 255, 0.05);
    color: #e0e0e0;
    font-size: 13px;
    padding: 4px 10px;
}

dropdown button label {
    color: #e0e0e0;
}

popover {
    background-color: #1e1e1e;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
}

popover label {
    color: #e0e0e0;
}

/* === Frames === */
frame {
    border-radius: 16px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    background-color: rgba(255, 255, 255, 0.02);
}

frame > border {
    border-radius: 16px;
    border: none;
}

/* === Separators === */
separator {
    background-color: rgba(255, 255, 255, 0.06);
    min-height: 1px;
}

/* === Entries === */
entry {
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    color: #e0e0e0;
    padding: 6px 10px;
}

entry:focus {
    border-color: rgba(255, 255, 255, 0.3);
}

/* === Message dialogs === */
messagedialog {
    background-color: #1e1e1e;
}

messagedialog .message-area label {
    color: #e0e0e0;
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
        provider.load_from_data(CSS.encode("utf-8"))
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
