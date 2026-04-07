# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
./run.sh          # Run from source tree (recommended during development)
flux              # Run installed version
```

## Installing

```bash
./install.sh      # Installs to ~/.local/share/flux/, adds flux to ~/.local/bin/
```

## Dependencies (Fedora)

```bash
sudo dnf install gtk4 libadwaita python3-gobject python3-psutil
pip install envycontrol   # optional, for GPU mode switching
```

## Architecture

The app is a GTK4/libadwaita Python app (`com.flux.app`). Entry point is `src/main.py` → `src/window.py`. The window holds three tabs, each backed by a self-contained UI class.

**Backend layer** (`src/backend/`) — no GTK imports, pure logic:
- `sensors.py` — reads `/sys/class/hwmon/` for CPU (`k10temp`) and iGPU (`amdgpu`) temps, GPU utilization, and battery state
- `fan_control.py` — reads/writes 8-point fan curves via `asus_custom_fan_curve` hwmon sysfs; escalates to `pkexec tee` when write is permission-denied
- `gpu_switch.py` — detects current GPU mode by querying `envycontrol --query` and `/proc/modules`; switches mode via `pkexec envycontrol -s <mode>`; GPU modes are `integrated`, `hybrid`, `dedicated`
- `power_profile.py` — gets/sets `power-profiles-daemon` profiles via `busctl` DBus calls; profile names are `power-saver`, `balanced`, `performance`
- `process_monitor.py` — wraps `psutil` for live process listing
- `history_db.py` — SQLite at `~/.local/share/flux/history.db`; records per-process CPU/mem snapshots; queries top apps over 1h/6h/24h/7d windows

**UI layer** (`src/ui/`) — GTK widgets only, calls backend:
- `thermal_tab.py` — power profile buttons, GPU mode selector, interactive fan curve canvas (8 draggable points), live temp readout
- `monitor_tab.py` — rolling line graphs (60s window) for CPU/mem/GPU/temp; process list with pause (SIGSTOP), resume (SIGCONT), kill actions; stops polling on window close
- `history_tab.py` — horizontal bar charts of top resource consumers; stops polling on window close

**Privilege escalation**: fan curve writes and GPU mode switching trigger a Polkit dialog via `pkexec`. No persistent root access.

**Hardware assumptions**: ASUS laptop with AMD Ryzen (`k10temp`), AMD Radeon iGPU (`amdgpu`), optional NVIDIA dGPU. The dGPU PCI address is hardcoded to `0000:01:00.0` in `gpu_switch.py`. The AMD GPU busy percent path is hardcoded to `/sys/class/drm/card2/` in `sensors.py`.
