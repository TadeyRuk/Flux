"""Fan curve read/write via ASUS hwmon sysfs interface."""

import glob
import os
import subprocess


def _find_hwmon(name):
    """Find hwmon path by name."""
    for path in glob.glob("/sys/class/hwmon/hwmon*/name"):
        try:
            with open(path) as f:
                if f.read().strip() == name:
                    return os.path.dirname(path)
        except OSError:
            continue
    return None


CURVE_HWMON = _find_hwmon("asus_custom_fan_curve")
ASUS_HWMON = _find_hwmon("asus")
NUM_POINTS = 8


def _write_sysfs(path, value):
    """Write a value to a sysfs file, using tee via pkexec if permission denied."""
    try:
        with open(path, "w") as f:
            f.write(str(value))
        return True, ""
    except PermissionError:
        try:
            result = subprocess.run(
                ["pkexec", "tee", path],
                input=str(value), capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr.strip() or "pkexec tee failed"
        except FileNotFoundError:
            return False, "pkexec not found"
        except subprocess.TimeoutExpired:
            return False, "Timeout waiting for authentication"
    except OSError as e:
        return False, str(e)


def get_fan_speeds():
    """Return current fan RPMs as dict {1: rpm, 2: rpm}."""
    if not ASUS_HWMON:
        return {}
    result = {}
    for i in (1, 2):
        path = os.path.join(ASUS_HWMON, f"fan{i}_input")
        try:
            with open(path) as f:
                result[i] = int(f.read().strip())
        except (OSError, ValueError):
            result[i] = 0
    return result


def get_fan_labels():
    """Return fan labels as dict {1: 'cpu', 2: 'gpu'}."""
    if not ASUS_HWMON:
        return {1: "Fan 1", 2: "Fan 2"}
    result = {}
    for i in (1, 2):
        path = os.path.join(ASUS_HWMON, f"fan{i}_label")
        try:
            with open(path) as f:
                result[i] = f.read().strip()
        except OSError:
            result[i] = f"Fan {i}"
    return result


def get_fan_curve(fan_id):
    """Read 8-point fan curve. Returns list of (temp, pwm) tuples."""
    if not CURVE_HWMON:
        return []
    points = []
    for i in range(1, NUM_POINTS + 1):
        try:
            temp_path = os.path.join(CURVE_HWMON, f"pwm{fan_id}_auto_point{i}_temp")
            pwm_path = os.path.join(CURVE_HWMON, f"pwm{fan_id}_auto_point{i}_pwm")
            with open(temp_path) as f:
                temp = int(f.read().strip())
            with open(pwm_path) as f:
                pwm = int(f.read().strip())
            points.append((temp, pwm))
        except (OSError, ValueError):
            break
    return points


def set_fan_curve(fan_id, points):
    """Write 8-point fan curve. points = list of (temp, pwm).
    Returns (success, error_msg).
    Uses pkexec for privilege escalation if needed.
    """
    if not CURVE_HWMON:
        return False, "asus_custom_fan_curve hwmon not found"
    for i, (temp, pwm) in enumerate(points, 1):
        temp_path = os.path.join(CURVE_HWMON, f"pwm{fan_id}_auto_point{i}_temp")
        pwm_path = os.path.join(CURVE_HWMON, f"pwm{fan_id}_auto_point{i}_pwm")
        ok, err = _write_sysfs(temp_path, int(temp))
        if not ok:
            return False, f"Point {i} temp: {err}"
        ok, err = _write_sysfs(pwm_path, int(pwm))
        if not ok:
            return False, f"Point {i} pwm: {err}"
    return True, ""


def get_fan_curve_enabled(fan_id):
    """Check if custom fan curve is enabled for this fan."""
    if not CURVE_HWMON:
        return False
    path = os.path.join(CURVE_HWMON, f"pwm{fan_id}_enable")
    try:
        with open(path) as f:
            return f.read().strip() == "1"
    except OSError:
        return False


def set_fan_curve_enabled(fan_id, enabled):
    """Enable/disable custom fan curve. Uses pkexec if needed."""
    if not CURVE_HWMON:
        return False, "hwmon not found"
    path = os.path.join(CURVE_HWMON, f"pwm{fan_id}_enable")
    return _write_sysfs(path, "1" if enabled else "2")
