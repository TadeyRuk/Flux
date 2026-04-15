"""Resource History tab — bar graphs of top resource-consuming apps."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, GLib

from backend.history_db import get_top_apps, cleanup_old


COLORS = [
    (0.36, 0.72, 1.0),    # blue
    (0.55, 0.85, 0.55),   # green
    (1.0,  0.42, 0.35),   # red-orange
    (0.75, 0.45, 1.0),    # violet
    (1.0,  0.78, 0.25),   # amber
    (0.25, 0.82, 0.78),   # teal
    (1.0,  0.50, 0.70),   # pink
    (0.50, 0.80, 0.40),   # lime
    (0.90, 0.60, 0.30),   # orange
    (0.55, 0.65, 0.85),   # slate blue
]


class BarChart(Gtk.DrawingArea):
    """Horizontal bar chart for top apps."""

    def __init__(self, title, value_key="avg_cpu", suffix="%"):
        super().__init__()
        self.title = title
        self.value_key = value_key
        self.suffix = suffix
        self.data = []  # list of {name, avg_cpu, avg_mem, samples}
        self.set_size_request(-1, 240)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_draw_func(self._draw)

    def set_data(self, data):
        self.data = data
        self.queue_draw()

    def _draw(self, area, cr, w, h):
        import cairo
        cr.set_source_rgba(1, 1, 1, 0)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        margin_l = 124
        margin_r = 68
        margin_t = 10
        margin_b = 12
        gw = w - margin_l - margin_r
        gh = h - margin_t - margin_b

        if not self.data:
            cr.set_source_rgba(0.91, 0.90, 0.95, 0.35)
            cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(12)
            cr.move_to(w / 2 - 90, h / 2)
            cr.show_text("No data yet — check back soon.")
            return

        max_val = max((d[self.value_key] for d in self.data), default=1)
        if max_val <= 0:
            max_val = 1

        bar_count = min(len(self.data), 10)
        bar_height = min(20, (gh - 6 * bar_count) / max(bar_count, 1))
        gap = 6

        for i in range(bar_count):
            d = self.data[i]
            val = d[self.value_key]
            bar_w = (val / max_val) * gw if max_val > 0 else 0

            y = margin_t + i * (bar_height + gap)
            r, g, b = COLORS[i % len(COLORS)]

            # Track (dim background bar)
            cr.set_source_rgba(r, g, b, 0.1)
            cr.set_line_width(bar_height)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.move_to(margin_l + bar_height / 2, y + bar_height / 2)
            cr.line_to(margin_l + gw - bar_height / 2, y + bar_height / 2)
            cr.stroke()

            # Filled bar
            cr.set_source_rgba(r, g, b, 0.9)
            cr.set_line_width(bar_height)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.move_to(margin_l + bar_height / 2, y + bar_height / 2)
            cr.line_to(margin_l + max(bar_w, bar_height) - bar_height / 2, y + bar_height / 2)
            cr.stroke()

            # Rank number
            cr.set_source_rgba(r, g, b, 0.8)
            cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(10)
            cr.move_to(4, y + bar_height - 2)
            cr.show_text(f"#{i+1}")

            # App name
            cr.set_source_rgba(0.91, 0.90, 0.95, 0.85)
            cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(11)
            name = d["name"][:16]
            cr.move_to(22, y + bar_height - 2)
            cr.show_text(name)

            # Value label
            cr.set_source_rgba(r, g, b, 1)
            cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(11)
            label = f"{val:.1f}{self.suffix}"
            cr.move_to(margin_l + bar_w + 8, y + bar_height - 2)
            cr.show_text(label)


class HistoryTab(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._timer_id = None

        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)

        # Time range selector
        range_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        range_box.set_halign(Gtk.Align.CENTER)
        range_box.set_margin_bottom(4)
        range_icon = Gtk.Image.new_from_icon_name("document-open-recent-symbolic")
        range_icon.set_pixel_size(14)
        range_box.append(range_icon)

        self.range_buttons = {}
        self._hours = 1
        for hours, label in [(1, "1h"), (6, "6h"), (24, "24h"), (168, "7d")]:
            btn = Gtk.ToggleButton(label=label)
            btn.set_size_request(68, 36)
            btn.add_css_class("pill-toggle")
            if hours == 1:
                btn.set_active(True)
            btn.connect("toggled", self._on_range_changed, hours)
            self.range_buttons[hours] = btn
            range_box.append(btn)

        self.append(range_box)

        # Charts
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        charts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        charts_box.add_css_class("card-white")
        charts_box.set_margin_top(8)

        for icon_name, chart_attr, title, key, suffix in [
            ("view-statistics-symbolic",   "cpu_chart", "Top CPU Usage",     "avg_cpu", "%"),
            ("drive-harddisk-symbolic",    "mem_chart", "Top Memory Usage",  "avg_mem", "%"),
            ("battery-symbolic",           "bat_chart", "Top Battery Drain", "avg_cpu", "%"),
        ]:
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hdr.set_margin_start(8)
            hdr.set_margin_top(4)
            ico = Gtk.Image.new_from_icon_name(icon_name)
            ico.set_pixel_size(14)
            hdr.append(ico)
            hdr_lbl = Gtk.Label(label=title)
            hdr_lbl.add_css_class("heading-sm")
            hdr.append(hdr_lbl)
            section.append(hdr)
            chart = BarChart(title, value_key=key, suffix=suffix)
            section.append(chart)
            setattr(self, chart_attr, chart)
            charts_box.append(section)
        scroll.set_child(charts_box)
        self.append(scroll)

        # Cleanup button
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bottom.set_halign(Gtk.Align.END)
        bottom.set_margin_top(4)

        cleanup_btn = Gtk.Button(label="Clear History")
        cleanup_btn.add_css_class("flat")
        cleanup_btn.connect("clicked", self._on_cleanup)
        bottom.append(cleanup_btn)
        self.append(bottom)

        # Refresh periodically
        self._refresh()
        self._timer_id = GLib.timeout_add_seconds(10, self._refresh)

    def _on_range_changed(self, button, hours):
        if getattr(self, "_ignore_range_toggles", False):
            return
        if not button.get_active():
            return
        self._ignore_range_toggles = True
        try:
            for h, btn in self.range_buttons.items():
                if h != hours:
                    btn.set_active(False)
            self._hours = hours
            self._refresh()
        finally:
            self._ignore_range_toggles = False

    def _refresh(self):
        try:
            cpu_data = get_top_apps(hours=self._hours, limit=10)
            mem_data = sorted(cpu_data, key=lambda d: d["avg_mem"], reverse=True)
            # Battery drain = CPU-intensive processes (highest energy impact)
            bat_data = sorted(cpu_data, key=lambda d: d["avg_cpu"], reverse=True)

            self.cpu_chart.set_data(cpu_data)
            self.mem_chart.set_data(mem_data)
            self.bat_chart.set_data(bat_data)
        except Exception:
            pass
        return True

    def _on_cleanup(self, button):
        cleanup_old(days=0)
        self._refresh()

    def stop(self):
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
