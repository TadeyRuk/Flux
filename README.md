# Flux

A GTK4/libadwaita power and thermal management app for ASUS Linux laptops with AMD + NVIDIA hybrid graphics.

## Features

### Thermal & Power
- **Power Profiles** — Switch between Eco, Balanced, and Turbo modes via `power-profiles-daemon`
- **GPU Mode Switching** — Toggle between iGPU-only (AMD), Hybrid, and dGPU-only (NVIDIA) using `envycontrol`
- **Custom Fan Curves** — Interactive 8-point drag-and-drop fan curve editor for CPU and GPU fans via the `asus_custom_fan_curve` sysfs interface
- **Live Temperatures** — Real-time CPU (`k10temp`) and iGPU (`amdgpu`) temperature readouts, updated every 2s

### System Monitor
- **Utilization Graphs** — Rolling line charts for CPU, memory, iGPU usage, and CPU temperature (60s window)
- **Process Manager** — Top userspace processes by CPU usage with pause (SIGSTOP), resume (SIGCONT), and kill actions

### Resource History
- **Usage Tracking** — SQLite-backed historical recording of per-process CPU and memory usage
- **Top Apps Charts** — Horizontal bar charts showing top resource consumers over 1h, 6h, 24h, or 7-day windows

## Install

```bash
./install.sh
```

This copies the app to `~/.local/share/flux/`, installs the `flux` binary to `~/.local/bin/`, registers the icon, and adds a `.desktop` entry for the GNOME app grid.

## Launch

```bash
flux
```

Or search **Flux** in the GNOME app grid.

To run directly from the source tree:

```bash
./run.sh
```

## Dependencies

- Python 3
- GTK 4 + libadwaita (via PyGObject)
- `psutil`
- `power-profiles-daemon` (for power profile switching)
- `envycontrol` (optional, for GPU mode switching: `pip install envycontrol`)
- ASUS Linux kernel modules (`asus-wmi` / `asus_custom_fan_curve`) for fan control

### Fedora

```bash
sudo dnf install gtk4 libadwaita python3-gobject python3-psutil
pip install envycontrol   # optional
```

## Permissions

Fan curve writes and GPU mode switching require elevated privileges. Flux uses `pkexec` — a Polkit authentication dialog will appear when needed. No password stored, no persistent root access.

## Hardware

Built for ASUS laptops running Linux with:
- AMD Ryzen CPU (`k10temp` hwmon)
- AMD Radeon iGPU (`amdgpu` hwmon)
- NVIDIA dGPU (optional, hybrid/dedicated switching)
- ASUS fan curve sysfs interface (`asus_custom_fan_curve` hwmon)

## Project Structure

```
flux.svg             # App icon (SVG)
install.sh           # User-level installer
run.sh               # Run from source tree
src/
  main.py            # Application entry (Adw.Application, com.flux.app)
  window.py          # Main window, 3-tab layout
  backend/
    sensors.py       # Hardware sensor readings (temps, GPU, battery)
    fan_control.py   # Fan curve read/write via ASUS sysfs + pkexec
    gpu_switch.py    # GPU mode switching (envycontrol)
    power_profile.py # Power profile management (DBus)
    process_monitor.py  # Process monitoring (psutil)
    history_db.py    # SQLite resource usage history (~/.local/share/flux/)
  ui/
    thermal_tab.py   # Thermal & Power tab
    monitor_tab.py   # System Monitor tab
    history_tab.py   # Resource History tab
data/
  com.flux.app.desktop  # Desktop entry
```
