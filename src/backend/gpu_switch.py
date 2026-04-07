"""GPU mode switching — iGPU (AMD) / dGPU (NVIDIA) / Hybrid."""

import shutil
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

ENVYCONTROL_INSTALL_MSG = (
    "envycontrol is not installed.\n\n"
    "Install it with:\n"
    "  pip install envycontrol\n\n"
    "Also ensure the proprietary NVIDIA driver is active.\n"
    "The open-source nouveau driver does not support mode switching."
)


def _envycontrol_available():
    return shutil.which("envycontrol") is not None


def _nouveau_active():
    """Check if open-source nouveau driver is loaded instead of nvidia."""
    try:
        with open("/proc/modules") as f:
            for line in f:
                if line.startswith("nouveau "):
                    return True
    except OSError:
        pass
    return False


def _nvidia_driver_available():
    """Check if the NVIDIA kernel module is installed (not necessarily loaded)."""
    try:
        result = subprocess.run(
            ["modinfo", "nvidia"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _nvidia_loaded():
    """Check if proprietary NVIDIA kernel module is loaded."""
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
    envycontrol_mode = _check_envycontrol()
    if envycontrol_mode:
        return envycontrol_mode

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
    if not _envycontrol_available():
        return None
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
    # Pre-flight checks before attempting pkexec
    if not _envycontrol_available():
        return False, ENVYCONTROL_INSTALL_MSG, False

    if _nouveau_active():
        return False, (
            "The open-source nouveau driver is active. "
            "envycontrol requires the proprietary NVIDIA driver.\n\n"
            "Install the NVIDIA driver and reboot, then try again."
        ), False

    if mode in (HYBRID, DEDICATED) and not _nvidia_driver_available():
        return False, (
            "The NVIDIA kernel driver is not installed.\n\n"
            "Install the proprietary NVIDIA driver and reboot, then try again.\n\n"
            "On Fedora:\n"
            "  sudo dnf install akmod-nvidia xorg-x11-drv-nvidia"
        ), False

    mode_map = {
        INTEGRATED: "integrated",
        HYBRID: "hybrid",
        DEDICATED: "nvidia",
    }
    envycontrol_mode = mode_map.get(mode)
    if not envycontrol_mode:
        return False, f"Unknown mode: {mode}", False

    try:
        result = subprocess.run(
            ["sudo", "envycontrol", "-s", envycontrol_mode],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return True, "GPU mode changed. Reboot to apply.", True
        # Surface the actual envycontrol error clearly
        stderr = result.stderr.strip()
        if "X server" in stderr or "display" in stderr.lower():
            return False, (
                "NVIDIA X server is active. Stop the display manager first:\n\n"
                "  sudo systemctl stop gdm\n"
                "  sudo envycontrol -s " + envycontrol_mode + "\n"
                "  sudo systemctl start gdm"
            ), False
        return False, stderr or "envycontrol failed with no output", False
    except FileNotFoundError:
        return False, ENVYCONTROL_INSTALL_MSG, False
    except subprocess.TimeoutExpired:
        return False, "sudo timed out.", False


def get_dgpu_power_info():
    """Get dGPU power state and driver info."""
    status = _dgpu_runtime_status()
    nvidia = _nvidia_loaded()
    nouveau = _nouveau_active()
    driver = "nouveau" if nouveau else ("nvidia" if nvidia else "none")
    return {
        "runtime_status": status,
        "nvidia_loaded": nvidia,
        "power_state": "Active" if status == "active" else "Suspended",
        "driver": driver,
        "nvidia_available": _nvidia_driver_available(),
        "envycontrol_available": _envycontrol_available(),
    }
