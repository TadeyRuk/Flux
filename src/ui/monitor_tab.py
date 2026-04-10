"""System Monitor tab — live utilization graphs + process list with suspend/kill."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, GLib, Pango

from backend.process_monitor import (
    get_top_processes, get_system_usage,
    suspend_process, resume_process, kill_process, is_os_process
)
from backend.sensors import get_cpu_temp, get_amdgpu_temp, get_amdgpu_busy
from backend.history_db import record_snapshot


class UtilizationGraph(Gtk.DrawingArea):
    """Rolling line graph showing utilization over time."""

    def __init__(self, title, color=(0.35, 0.7, 1.0), max_val=100, unit="%"):
        super().__init__()
        self.title = title
        self.color = color
        self.max_val = max_val
        self.unit = unit
        self.data = []
        self.max_points = 60
        self.set_size_request(-1, 90)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def push(self, value):
        self.data.append(value)
        if len(self.data) > self.max_points:
            self.data.pop(0)
        self.queue_draw()

    def _draw(self, area, cr, w, h):
        cr.set_source_rgb(0.12, 0.12, 0.14)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        ml, mr, mt, mb = 45, 10, 22, 5
        gw = w - ml - mr
        gh = h - mt - mb

        # Title
        cr.set_source_rgba(0.8, 0.8, 0.85, 1)
        cr.set_font_size(11)
        cr.move_to(ml, 15)
        cr.show_text(self.title)

        # Current value
        if self.data:
            val = self.data[-1]
            cr.set_source_rgba(*self.color, 1)
            cr.move_to(w - 65, 15)
            cr.show_text(f"{val:.1f}{self.unit}")

        # Grid
        cr.set_source_rgba(0.3, 0.3, 0.35, 0.3)
        cr.set_line_width(0.5)
        for pct in (25, 50, 75):
            y = mt + gh * (1 - pct / self.max_val)
            cr.move_to(ml, y)
            cr.line_to(w - mr, y)
            cr.stroke()
            cr.set_source_rgba(0.5, 0.5, 0.55, 0.7)
            cr.set_font_size(8)
            cr.move_to(5, y + 3)
            cr.show_text(f"{pct}")
            cr.set_source_rgba(0.3, 0.3, 0.35, 0.3)

        if len(self.data) < 2:
            return

        # Line
        cr.set_source_rgba(*self.color, 0.9)
        cr.set_line_width(2)
        for i, val in enumerate(self.data):
            x = ml + (i / (self.max_points - 1)) * gw
            y = mt + gh * (1 - min(val, self.max_val) / self.max_val)
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()

        # Fill under curve
        cr.set_source_rgba(*self.color, 0.08)
        for i, val in enumerate(self.data):
            x = ml + (i / (self.max_points - 1)) * gw
            y = mt + gh * (1 - min(val, self.max_val) / self.max_val)
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        last_x = ml + ((len(self.data) - 1) / (self.max_points - 1)) * gw
        cr.line_to(last_x, mt + gh)
        cr.line_to(ml, mt + gh)
        cr.close_path()
        cr.fill()


class MonitorTab(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._timer_id = None
        self._snapshot_counter = 0
        self._suspended_pids = set()
        self._proc_rows = {}  # pid -> row widgets dict

        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)

        header_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header_card.add_css_class("dashboard-header")
        header_card.set_margin_bottom(10)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="System Monitor")
        title.add_css_class("title-3")
        title.add_css_class("panel-heading")
        title.set_halign(Gtk.Align.START)
        subtitle = Gtk.Label(label="Real-time load, temperatures, and active processes")
        subtitle.add_css_class("dim-label")
        subtitle.set_halign(Gtk.Align.START)
        title_box.append(title)
        title_box.append(subtitle)

        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        stats_box.set_hexpand(True)
        stats_box.set_halign(Gtk.Align.END)
        self.cpu_chip = Gtk.Label(label="CPU --")
        self.cpu_chip.add_css_class("subtle-chip")
        self.mem_chip = Gtk.Label(label="RAM --")
        self.mem_chip.add_css_class("subtle-chip")
        self.temp_chip = Gtk.Label(label="Temp --")
        self.temp_chip.add_css_class("subtle-chip")
        stats_box.append(self.cpu_chip)
        stats_box.append(self.mem_chip)
        stats_box.append(self.temp_chip)

        header_card.append(title_box)
        header_card.append(stats_box)
        self.append(header_card)

        # Utilization graphs
        graphs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        graphs_box.add_css_class("panel-card")
        graphs_box.set_margin_bottom(8)

        self.cpu_graph = UtilizationGraph("CPU", color=(0.35, 0.7, 1.0))
        self.mem_graph = UtilizationGraph("Memory", color=(0.9, 0.4, 0.5))
        self.gpu_graph = UtilizationGraph("iGPU (AMD)", color=(0.4, 0.9, 0.5))
        self.temp_graph = UtilizationGraph("CPU Temp", color=(1.0, 0.6, 0.2), max_val=105, unit=" C")

        graphs_box.append(self.cpu_graph)
        graphs_box.append(self.mem_graph)
        graphs_box.append(self.gpu_graph)
        graphs_box.append(self.temp_graph)

        self.append(graphs_box)

        # Separator
        sep = Gtk.Separator()
        sep.set_margin_top(8)
        sep.set_margin_bottom(4)
        self.append(sep)

        # Process header
        proc_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        proc_header.set_margin_bottom(4)
        proc_icon = Gtk.Image.new_from_icon_name("view-list-symbolic")
        proc_header.append(proc_icon)
        lbl = Gtk.Label(label="Processes")
        lbl.add_css_class("heading")
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        proc_header.append(lbl)

        self.proc_count_label = Gtk.Label()
        self.proc_count_label.add_css_class("dim-label")
        proc_header.append(self.proc_count_label)
        self.append(proc_header)

        # Column headers
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header_row.set_margin_bottom(2)
        for text, width in [("Name", 200), ("PID", 70), ("CPU %", 70), ("RAM %", 70), ("", 120)]:
            col = Gtk.Label(label=text)
            col.set_size_request(width, -1)
            col.set_halign(Gtk.Align.START)
            col.add_css_class("dim-label")
            col.set_xalign(0)
            header_row.append(col)
        self.append(header_row)

        # Scrollable process list
        scroll = Gtk.ScrolledWindow()
        scroll.add_css_class("panel-card")
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_min_content_height(200)

        self.proc_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        scroll.set_child(self.proc_list)
        self.append(scroll)

        # Start periodic updates
        self._timer_id = GLib.timeout_add(1500, self._update)

    def _update(self):
        # System usage
        usage = get_system_usage()
        self.cpu_graph.push(usage["cpu_percent"])
        self.mem_graph.push(usage["mem_percent"])
        self.cpu_chip.set_text(f"CPU {usage['cpu_percent']:.0f}%")
        self.mem_chip.set_text(f"RAM {usage['mem_percent']:.0f}%")

        gpu_busy = get_amdgpu_busy()
        self.gpu_graph.push(gpu_busy if gpu_busy is not None else 0)

        cpu_temp = get_cpu_temp()
        self.temp_graph.push(cpu_temp if cpu_temp is not None else 0)
        self.temp_chip.set_text(f"Temp {cpu_temp:.0f} C" if cpu_temp is not None else "Temp N/A")

        # Process list
        procs = get_top_processes(15)

        # Snapshot to DB every ~7.5s (5 ticks * 1.5s)
        self._snapshot_counter += 1
        if self._snapshot_counter >= 5:
            self._snapshot_counter = 0
            try:
                record_snapshot(procs[:10])
            except Exception:
                pass

        self.proc_count_label.set_text(f"{len(procs)} shown")

        # Rebuild process list
        child = self.proc_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.proc_list.remove(child)
            child = nxt

        for proc in procs:
            row = self._make_proc_row(proc)
            self.proc_list.append(row)

        return True

    def _make_proc_row(self, proc):
        pid = proc["pid"]
        is_suspended = pid in self._suspended_pids

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.set_margin_top(1)
        row.set_margin_bottom(1)
        row.add_css_class("proc-row")

        # Name
        name_lbl = Gtk.Label(label=proc["name"])
        name_lbl.set_size_request(200, -1)
        name_lbl.set_halign(Gtk.Align.START)
        name_lbl.set_xalign(0)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        if is_suspended:
            name_lbl.add_css_class("dim-label")
        row.append(name_lbl)

        # PID
        pid_lbl = Gtk.Label(label=str(pid))
        pid_lbl.set_size_request(70, -1)
        pid_lbl.set_halign(Gtk.Align.START)
        pid_lbl.set_xalign(0)
        pid_lbl.add_css_class("dim-label")
        row.append(pid_lbl)

        # CPU %
        cpu_lbl = Gtk.Label(label=f"{proc['cpu']:.1f}")
        cpu_lbl.set_size_request(70, -1)
        cpu_lbl.set_halign(Gtk.Align.START)
        cpu_lbl.set_xalign(0)
        if proc["cpu"] > 50:
            cpu_lbl.add_css_class("error")
        elif proc["cpu"] > 20:
            cpu_lbl.add_css_class("warning")
        row.append(cpu_lbl)

        # RAM %
        mem_lbl = Gtk.Label(label=f"{proc['mem']:.1f}")
        mem_lbl.set_size_request(70, -1)
        mem_lbl.set_halign(Gtk.Align.START)
        mem_lbl.set_xalign(0)
        row.append(mem_lbl)

        # Action buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_box.set_size_request(120, -1)

        if is_suspended:
            resume_btn = Gtk.Button(label="Resume")
            resume_btn.add_css_class("flat")
            resume_btn.set_size_request(65, 28)
            resume_btn.set_child(self._make_action_content("Resume", "media-playback-start-symbolic"))
            resume_btn.connect("clicked", self._on_resume, pid)
            btn_box.append(resume_btn)
        else:
            pause_btn = Gtk.Button(label="Pause")
            pause_btn.add_css_class("flat")
            pause_btn.set_size_request(55, 28)
            pause_btn.set_child(self._make_action_content("Pause", "media-playback-pause-symbolic"))
            pause_btn.connect("clicked", self._on_suspend, pid)
            btn_box.append(pause_btn)

        kill_btn = Gtk.Button(label="Kill")
        kill_btn.add_css_class("flat")
        kill_btn.add_css_class("destructive-action")
        kill_btn.set_size_request(45, 28)
        kill_btn.set_child(self._make_action_content("Kill", "process-stop-symbolic"))
        kill_btn.connect("clicked", self._on_kill, pid, proc["name"])
        btn_box.append(kill_btn)

        row.append(btn_box)
        return row

    def _on_suspend(self, button, pid):
        if is_os_process(pid):
            dialog = Adw.MessageDialog(
                heading="Warning",
                body="Suspending a system process may cause instability.",
                transient_for=self.get_root(),
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("suspend", "Suspend Anyway")
            dialog.set_response_appearance("suspend", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.connect("response", self._on_suspend_confirm, pid)
            dialog.present()
        else:
            self._do_suspend(pid)

    def _on_suspend_confirm(self, dialog, response, pid):
        if response == "suspend":
            self._do_suspend(pid)

    def _do_suspend(self, pid):
        ok, err = suspend_process(pid)
        if ok:
            self._suspended_pids.add(pid)

    def _on_resume(self, button, pid):
        ok, err = resume_process(pid)
        if ok:
            self._suspended_pids.discard(pid)

    def _on_kill(self, button, pid, name):
        warning = ""
        if is_os_process(pid):
            warning = "\n\nWarning: This is a system process. Killing it may cause system instability."

        dialog = Adw.MessageDialog(
            heading="Kill Process?",
            body=f"Kill '{name}' (PID {pid})?{warning}",
            transient_for=self.get_root(),
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("kill", "Kill")
        dialog.set_response_appearance("kill", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_kill_confirm, pid)
        dialog.present()

    def _on_kill_confirm(self, dialog, response, pid):
        if response == "kill":
            kill_process(pid)
            self._suspended_pids.discard(pid)

    def _make_action_content(self, label, icon_name):
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
