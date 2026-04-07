"""Power profile management via power-profiles-daemon DBus."""

import subprocess


PROFILES = ["power-saver", "balanced", "performance"]
PROFILE_LABELS = {
    "power-saver": "Eco",
    "balanced": "Balanced",
    "performance": "Turbo",
}
PROFILE_ICONS = {
    "power-saver": "power-profile-power-saver-symbolic",
    "balanced": "power-profile-balanced-symbolic",
    "performance": "power-profile-performance-symbolic",
}


def get_active_profile():
    """Get current active power profile."""
    try:
        result = subprocess.run(
            [
                "busctl", "get-property",
                "net.hadess.PowerProfiles",
                "/net/hadess/PowerProfiles",
                "net.hadess.PowerProfiles",
                "ActiveProfile",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            # Output: s "balanced"
            return result.stdout.strip().split('"')[1]
    except (subprocess.TimeoutExpired, IndexError, FileNotFoundError):
        pass
    return "balanced"


def set_active_profile(profile):
    """Set power profile. Returns (success, error_msg)."""
    if profile not in PROFILES:
        return False, f"Unknown profile: {profile}"
    try:
        result = subprocess.run(
            [
                "busctl", "set-property",
                "net.hadess.PowerProfiles",
                "/net/hadess/PowerProfiles",
                "net.hadess.PowerProfiles",
                "ActiveProfile", "s", profile,
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return True, ""
        return False, result.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)
