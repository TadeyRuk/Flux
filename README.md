# Flux

<p align="center">
  <img src="flux.svg" alt="Flux logo" width="120" height="120">
</p>

Flux is a GTK4/libadwaita power and thermal control app for Linux laptops, focused on ASUS AMD systems with optional NVIDIA hybrid graphics.

It provides power profile control, GPU mode switching, fan curve editing, live monitoring, and historical process usage in one desktop app.

## Highlights

- Thermal and power management:
  - Switch between power profiles (`power-saver`, `balanced`, `performance`)
  - Switch GPU mode (`integrated`, `hybrid`, `dedicated`) through `envycontrol`
  - Edit 8-point CPU/GPU fan curves through ASUS `asus_custom_fan_curve`
  - Live CPU and iGPU temperature readouts
- Live system monitor:
  - Rolling 60-second graphs for CPU, memory, iGPU utilization, and temperature
  - Process list with pause (`SIGSTOP`), resume (`SIGCONT`), and kill actions
- Historical usage insights:
  - SQLite-backed process CPU/memory samples
  - Top consumer charts for 1h, 6h, 24h, and 7d windows

## Requirements

- Linux desktop with GTK4/libadwaita support
- Python 3
- PyGObject (`python3-gobject`)
- `psutil`
- `power-profiles-daemon` (required for power profile switching)
- `envycontrol` (optional, required for GPU mode switching)
- ASUS kernel support for fan curves (`asus_wmi` / `asus_custom_fan_curve`)

### Fedora Packages

```bash
sudo dnf install gtk4 libadwaita python3-gobject python3-psutil
pip install envycontrol  # optional
```

## Quick Start

### Run from Source

```bash
./run.sh
```

### Install for Current User

```bash
./install.sh
```

`install.sh` performs a user-local install and does not require system-wide packaging:

- App files: `~/.local/share/flux/`
- Launcher binary: `~/.local/bin/flux`
- Desktop entry: `~/.local/share/applications/com.flux.app.desktop`
- Icon: `~/.local/share/icons/hicolor/scalable/apps/flux.svg`

Launch after install:

```bash
flux
```

Or open it from your desktop app grid as **Flux**.

## Security and Privileges

Flux runs as a regular user process by default.

Only operations that require elevated permissions trigger Polkit authentication via `pkexec`:

- Writing fan curves
- Switching GPU mode

Flux does not keep persistent root privileges.

## Hardware Compatibility

Designed primarily for ASUS Linux laptops, with these expected interfaces:

- CPU temperature via `k10temp`
- AMD iGPU temperature/utilization via `amdgpu`
- Optional NVIDIA dGPU for hybrid/dedicated switching
- ASUS fan curve hwmon interface (`asus_custom_fan_curve`)

If your hardware paths differ, some controls may be unavailable.

## Project Layout

```text
flux.svg
install.sh
run.sh
src/
  main.py
  window.py
  backend/
    sensors.py
    fan_control.py
    fan_profiles.py
    gpu_switch.py
    power_profile.py
    process_monitor.py
    history_db.py
  ui/
    thermal_tab.py
    monitor_tab.py
    history_tab.py
data/
  com.flux.app.desktop
```

## Troubleshooting

- `flux: command not found` after install:
  - Ensure `~/.local/bin` is in your `PATH`
- Power profile actions fail:
  - Verify `power-profiles-daemon` is installed and running
- GPU switching unavailable:
  - Install `envycontrol` and confirm supported hybrid graphics setup
- Fan controls unavailable:
  - Confirm ASUS fan curve sysfs interface is present and writable (with Polkit when prompted)

## License

No license file is currently included in this repository.
Add a `LICENSE` file to define redistribution and usage terms for production distribution.
