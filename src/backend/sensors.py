"""Hardware sensor readings — temps, GPU utilization, etc."""

import glob
import os


def _find_hwmon(name):
    for path in glob.glob("/sys/class/hwmon/hwmon*/name"):
        try:
            with open(path) as f:
                if f.read().strip() == name:
                    return os.path.dirname(path)
        except OSError:
            continue
    return None


K10TEMP = _find_hwmon("k10temp")
AMDGPU_HWMON = _find_hwmon("amdgpu")


def get_cpu_temp():
    """CPU temp in Celsius from k10temp."""
    if not K10TEMP:
        return None
    try:
        with open(os.path.join(K10TEMP, "temp1_input")) as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def get_amdgpu_temp():
    """AMD iGPU temp in Celsius."""
    if not AMDGPU_HWMON:
        return None
    try:
        with open(os.path.join(AMDGPU_HWMON, "temp1_input")) as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def get_amdgpu_busy():
    """AMD iGPU utilization percent."""
    path = "/sys/class/drm/card2/device/gpu_busy_percent"
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def get_amdgpu_power():
    """AMD iGPU power draw in watts."""
    if not AMDGPU_HWMON:
        return None
    try:
        with open(os.path.join(AMDGPU_HWMON, "power1_input")) as f:
            return int(f.read().strip()) / 1_000_000.0
    except (OSError, ValueError):
        return None


def get_amdgpu_freq():
    """AMD iGPU clock frequency in MHz."""
    if not AMDGPU_HWMON:
        return None
    try:
        with open(os.path.join(AMDGPU_HWMON, "freq1_input")) as f:
            return int(f.read().strip()) / 1_000_000.0
    except (OSError, ValueError):
        return None


def get_battery_percent():
    """Battery charge percent."""
    path = "/sys/class/power_supply/BAT1/capacity"
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def get_battery_status():
    """Battery status: Charging, Discharging, Full, etc."""
    path = "/sys/class/power_supply/BAT1/status"
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None
