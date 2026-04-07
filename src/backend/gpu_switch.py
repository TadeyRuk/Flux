"""GPU mode switching — iGPU (AMD) / dGPU (NVIDIA) / Hybrid."""

import os
import subprocess

# GPU modes
INTEGRATED = "integrated"
HYBRID = "hybrid"
DEDICATED = "dedicated"

MODE_LABELS = {
    INTEGRATED: "iGPU Only (AMD)",
    HYBRID: "Hybrid (Auto)",
    DEDICATED: "dGPU Only (NVIDIA)",
}


def _nvidia_loaded():
    """Check if NVIDIA kernel module is loaded."""
    try:
        with open("/proc/modules") as f:
            for line in f:
                if line.startswith("nvidia "):
                    return True
    except OSError:
        pass
    return False


def _dgpu_runtime_status():
    """Check dGPU PCI runtime power status."""
    path = "/sys/bus/pci/devices/0000:01:00.0/power/runtime_status"
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return "unknown"


def get_current_mode():
    """Detect current GPU mode."""
    # Check if envycontrol left a marker
    envycontrol_mode = _check_envycontrol()
    if envycontrol_mode:
        return envycontrol_mode

    # Heuristic: if nvidia module loaded and GPU active
    nvidia = _nvidia_loaded()
    dgpu_status = _dgpu_runtime_status()

    if not nvidia and dgpu_status == "suspended":
        return INTEGRATED
    elif nvidia and dgpu_status == "active":
        return DEDICATED
    else:
        return HYBRID


def _check_envycontrol():
    """Check envycontrol's saved mode if available."""
    try:
        result = subprocess.run(
            ["envycontrol", "--query"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            out = result.stdout.strip().lower()
            if "integrated" in out:
                return INTEGRATED
            elif "hybrid" in out:
                return HYBRID
            elif "nvidia" in out:
                return DEDICATED
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def set_mode(mode):
    """Switch GPU mode using envycontrol. Needs reboot after.
    Returns (success, error_msg, needs_reboot).
    """
    mode_map = {
        INTEGRATED: "integrated",
        HYBRID: "hybrid",
        DEDICATED: "nvidia",
    }
    envycontrol_mode = mode_map.get(mode)
    if not envycontrol_mode:
        return False, f"Unknown mode: {mode}", False

    # Check if envycontrol is available
    try:
        result = subprocess.run(
            ["pkexec", "envycontrol", "-s", envycontrol_mode],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return True, "Reboot required to apply changes.", True
        return False, result.stderr.strip() or "envycontrol failed", False
    except FileNotFoundError:
        return False, "envycontrol not installed. Install: pip install envycontrol", False
    except subprocess.TimeoutExpired:
        return False, "Timeout waiting for envycontrol", False


def get_dgpu_power_info():
    """Get dGPU power state info."""
    status = _dgpu_runtime_status()
    nvidia = _nvidia_loaded()
    return {
        "runtime_status": status,
        "nvidia_loaded": nvidia,
        "power_state": "Active" if status == "active" else "Suspended",
    }
