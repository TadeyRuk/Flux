# Rukkan

A GTK4/libadwaita power and thermal management app for ASUS Linux laptops with AMD + NVIDIA hybrid graphics.

## Features

### Thermal & Power
- **Power Profiles** — Switch between Eco, Balanced, and Turbo modes via `power-profiles-daemon`
- **GPU Mode Switching** — Toggle between iGPU-only (AMD), Hybrid, and dGPU-only (NVIDIA) using `envycontrol`
- **Custom Fan Curves** — Interactive 8-point drag-and-drop fan curve editor for CPU and GPU fans via the `asus_custom_fan_curve` sysfs interface
- **Live Temperatures** — Real-time CPU (`k10temp`) and iGPU (`amdgpu`) temperature readouts

### System Monitor
- **Utilization Graphs** — Rolling line charts for CPU, memory, iGPU usage, and CPU temperature
- **Process Manager** — Top processes by CPU usage with pause (SIGSTOP), resume (SIGCONT), and kill actions

### Resource History
- **Usage Tracking** — SQLite-backed historical recording of per-process CPU and memory usage
- **Top Apps Charts** — Horizontal bar charts showing top resource consumers over 1h, 6h, 24h, or 7-day windows

## Dependencies

- Python 3
- GTK 4 + libadwaita (via PyGObject)
- `psutil`
- `power-profiles-daemon` (for power profile switching)
- `envycontrol` (optional, for GPU mode switching)
- ASUS Linux kernel modules (`asus-wmi` / `asus_custom_fan_curve`) for fan control

### Install dependencies (Fedora)

```bash
sudo dnf install gtk4 libadwaita python3-gobject python3-psutil
pip install envycontrol  # optional
```

## Usage

```bash
./run.sh
```

Or run directly:

```bash
python3 src/main.py
```

A `.desktop` file is provided at `data/com.powercontrol.app.desktop` for application launcher integration.

## Hardware Support

Rukkan is built for ASUS laptops running Linux with:
- AMD Ryzen CPU (`k10temp` hwmon)
- AMD Radeon iGPU (`amdgpu` hwmon)
- NVIDIA dGPU (optional, for hybrid/dedicated switching)
- ASUS fan curve sysfs interface (`asus_custom_fan_curve` hwmon)

Fan curve and GPU mode changes require root privileges and will prompt via `pkexec`.

## Project Structure

```
src/
  main.py              # Application entry point (Adw.Application)
  window.py            # Main window with tab navigation
  backend/
    sensors.py         # Hardware sensor readings (temps, GPU, battery)
    fan_control.py     # Fan curve read/write via ASUS sysfs
    gpu_switch.py      # GPU mode switching (envycontrol)
    power_profile.py   # Power profile management (DBus)
    process_monitor.py # Process monitoring (psutil)
    history_db.py      # SQLite resource usage history
  ui/
    thermal_tab.py     # Thermal & Power tab UI
    monitor_tab.py     # System Monitor tab UI
    history_tab.py     # Resource History tab UI
data/
  com.powercontrol.app.desktop  # Desktop entry file
```

## License

This project is not yet licensed. All rights reserved.
