"""Resource History tab — bar graphs of top resource-consuming apps."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, GLib

from backend.history_db import get_top_apps, cleanup_old


COLORS = [
    (0.35, 0.7, 1.0),
    (0.9, 0.4, 0.5),
    (0.4, 0.9, 0.5),
    (1.0, 0.6, 0.2),
    (0.7, 0.5, 1.0),
    (0.2, 0.8, 0.8),
    (1.0, 0.85, 0.3),
    (0.6, 0.6, 0.7),
    (1.0, 0.5, 0.7),
    (0.5, 0.7, 0.4),
]


class BarChart(Gtk.DrawingArea):
    """Horizontal bar chart for top apps."""

    def __init__(self, title, value_key="avg_cpu", suffix="%"):
        super().__init__()
        self.title = title
        self.value_key = value_key
        self.suffix = suffix
        self.data = []  # list of {name, avg_cpu, avg_mem, samples}
        self.set_size_request(-1, 280)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_draw_func(self._draw)

    def set_data(self, data):
        self.data = data
        self.queue_draw()

    def _draw(self, area, cr, w, h):
        # Background
        cr.set_source_rgb(0.12, 0.12, 0.14)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        margin_l = 120
        margin_r = 60
        margin_t = 30
        margin_b = 10
        gw = w - margin_l - margin_r
        gh = h - margin_t - margin_b

        # Title
        cr.set_source_rgba(0.8, 0.8, 0.85, 1)
        cr.set_font_size(12)
        cr.move_to(margin_l, 18)
        cr.show_text(self.title)

        if not self.data:
            cr.set_source_rgba(0.5, 0.5, 0.55, 0.7)
            cr.set_font_size(11)
            cr.move_to(w / 2 - 60, h / 2)
            cr.show_text("No data yet. Check back soon.")
            return

        max_val = max((d[self.value_key] for d in self.data), default=1)
        if max_val <= 0:
            max_val = 1

        bar_count = min(len(self.data), 10)
        bar_height = min(22, (gh - 4 * bar_count) / max(bar_count, 1))
        gap = 4

        for i in range(bar_count):
            d = self.data[i]
            val = d[self.value_key]
            bar_w = (val / max_val) * gw if max_val > 0 else 0

            y = margin_t + i * (bar_height + gap)
            color = COLORS[i % len(COLORS)]

            # Bar
            cr.set_source_rgba(*color, 0.8)
            cr.rectangle(margin_l, y, max(bar_w, 2), bar_height)
            cr.fill()

            # Bar glow
            cr.set_source_rgba(*color, 0.15)
            cr.rectangle(margin_l, y, gw, bar_height)
            cr.fill()

            # App name
            cr.set_source_rgba(0.8, 0.8, 0.85, 1)
            cr.set_font_size(10)
            name = d["name"][:18]
            cr.move_to(5, y + bar_height - 5)
            cr.show_text(name)

            # Value
            cr.set_source_rgba(*color, 1)
            cr.move_to(margin_l + bar_w + 6, y + bar_height - 5)
            cr.show_text(f"{val:.1f}{self.suffix}")


class HistoryTab(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._timer_id = None

        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)

        header_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header_card.add_css_class("dashboard-header")

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Resource History")
        title.add_css_class("title-3")
        title.add_css_class("panel-heading")
        title.set_halign(Gtk.Align.START)
        subtitle = Gtk.Label(label="See which apps used the most CPU and memory over time")
        subtitle.add_css_class("dim-label")
        subtitle.set_halign(Gtk.Align.START)
        title_box.append(title)
        title_box.append(subtitle)
        header_card.append(title_box)
        self.append(header_card)

        # Time range selector
        range_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        range_box.set_halign(Gtk.Align.CENTER)
        range_box.set_margin_bottom(4)
        range_box.add_css_class("panel-card")

        self.range_buttons = {}
        self._hours = 1
        for hours, label, icon in [
            (1, "1h", "preferences-system-time-symbolic"),
            (6, "6h", "preferences-system-time-symbolic"),
            (24, "24h", "x-office-calendar-symbolic"),
            (168, "7d", "x-office-calendar-symbolic"),
        ]:
            btn = Gtk.ToggleButton(label=label)
            btn.set_size_request(60, 32)
            btn.add_css_class("pill")
            btn.add_css_class("icon-pill")
            btn.set_child(self._make_range_content(label, icon))
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

        self.cpu_chart = BarChart("Top CPU Usage", value_key="avg_cpu", suffix="%")
        self.mem_chart = BarChart("Top Memory Usage", value_key="avg_mem", suffix="%")

        self.cpu_chart.add_css_class("panel-card")
        self.mem_chart.add_css_class("panel-card")

        charts_box.append(self.cpu_chart)
        charts_box.append(self.mem_chart)
        scroll.set_child(charts_box)
        self.append(scroll)

        # Cleanup button
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bottom.set_halign(Gtk.Align.END)
        bottom.set_margin_top(4)

        cleanup_btn = Gtk.Button(label="Clear History")
        cleanup_btn.add_css_class("flat")
        cleanup_btn.add_css_class("danger-flat")
        cleanup_btn.set_child(self._make_range_content("Clear History", "edit-delete-symbolic"))
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
            # Sort by mem for mem chart
            mem_data = sorted(cpu_data, key=lambda d: d["avg_mem"], reverse=True)

            self.cpu_chart.set_data(cpu_data)
            self.mem_chart.set_data(mem_data)
        except Exception:
            pass
        return True

    def _on_cleanup(self, button):
        cleanup_old(days=0)
        self._refresh()

    def _make_range_content(self, label, icon_name):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.set_halign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_valign(Gtk.Align.CENTER)
        text = Gtk.Label(label=label)
        text.set_valign(Gtk.Align.CENTER)
        box.append(icon)
        box.append(text)
        return box

    def stop(self):
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
