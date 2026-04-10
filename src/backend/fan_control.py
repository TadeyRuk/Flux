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


def _read_pwm_enable_mode(path):
    """Read pwmX_enable mode as string, or None on failure."""
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _preferred_disable_mode(path):
    """Pick a disable/auto mode compatible with the current driver.

    Some ASUS platforms expose pwmX_enable values where custom curve is `1`
    and firmware/auto mode is `2` (not `0`). If current mode already looks
    like this scheme, prefer `2` for disabling.
    """
    current = _read_pwm_enable_mode(path)
    if current in ("1", "2"):
        return "2"
    return "0"


def get_curve_hwmon_labels():
    """Check if asus_custom_fan_curve hwmon has its own pwm label files.

    Returns {pwm_id: label} if labels exist, else empty dict.
    """
    if not CURVE_HWMON:
        return {}
    labels = {}
    for i in (1, 2):
        path = os.path.join(CURVE_HWMON, f"pwm{i}_label")
        try:
            with open(path) as f:
                labels[i] = f.read().strip()
        except OSError:
            continue
    return labels


def _write_sysfs_batch(writes):
    """Write multiple values to sysfs files in a single pkexec call.
    writes = list of (path, value) tuples.
    Returns (success, error_msg).
    """
    if not writes:
        return True, ""

    # Try writing directly first (if running as root or files are writable)
    try:
        failed_writes = []
        for path, value in writes:
            try:
                with open(path, "w") as f:
                    f.write(str(value))
            except PermissionError:
                failed_writes.append((path, value))
            except OSError as e:
                return False, f"Error writing {path}: {e}"
        
        if not failed_writes:
            return True, ""
        
        # Some or all writes failed with PermissionError, use pkexec for the rest
        # Build a single shell command to perform all writes
        cmds = []
        for path, value in failed_writes:
            # Use printf to avoid issues with echo and special characters, though values are just ints
            cmds.append(f"printf '%s' '{value}' | tee '{path}'")
        
        full_cmd = " && ".join(cmds) + " > /dev/null"
        
        result = subprocess.run(
            ["pkexec", "sh", "-c", full_cmd],
            capture_output=True, text=True, timeout=30,
        )
        
        if result.returncode == 0:
            return True, ""
        return False, result.stderr.strip() or f"pkexec failed with code {result.returncode}"
        
    except FileNotFoundError:
        return False, "pkexec not found"
    except subprocess.TimeoutExpired:
        return False, "Timeout waiting for authentication"
    except Exception as e:
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
            if not os.path.exists(temp_path) or not os.path.exists(pwm_path):
                break
            with open(temp_path) as f:
                temp = int(f.read().strip())
            with open(pwm_path) as f:
                pwm = int(f.read().strip())
            points.append((temp, pwm))
        except (OSError, ValueError):
            break
    return points


def apply_fan_curve(fan_id, points, enabled=True):
    """Write fan curve points and enable state in a single operation.
    points = list of (temp, pwm).
    Returns (success, error_msg).
    """
    if not CURVE_HWMON:
        return False, "asus_custom_fan_curve hwmon not found"
    
    writes = []
    # 1. Add all points to the batch
    for i, (temp, pwm) in enumerate(points, 1):
        temp_path = os.path.join(CURVE_HWMON, f"pwm{fan_id}_auto_point{i}_temp")
        pwm_path = os.path.join(CURVE_HWMON, f"pwm{fan_id}_auto_point{i}_pwm")
        
        # Verify these files exist before adding to batch
        if os.path.exists(temp_path):
            writes.append((temp_path, int(temp)))
        if os.path.exists(pwm_path):
            writes.append((pwm_path, int(pwm)))
            
    # 2. Force controller re-evaluation and then set final enable state.
    # Writing 1 when already enabled may not immediately re-apply the new
    # curve on some ASUS EC implementations.
    enable_path = os.path.join(CURVE_HWMON, f"pwm{fan_id}_enable")
    disable_mode = _preferred_disable_mode(enable_path)
    if enabled:
        writes.append((enable_path, disable_mode))
        writes.append((enable_path, "1"))
    else:
        writes.append((enable_path, disable_mode))
    
    return _write_sysfs_batch(writes)


def set_fan_curve(fan_id, points):
    """Write 8-point fan curve. points = list of (temp, pwm).
    Returns (success, error_msg).
    Note: Usually you should use apply_fan_curve instead.
    """
    writes = []
    for i, (temp, pwm) in enumerate(points, 1):
        temp_path = os.path.join(CURVE_HWMON, f"pwm{fan_id}_auto_point{i}_temp")
        pwm_path = os.path.join(CURVE_HWMON, f"pwm{fan_id}_auto_point{i}_pwm")
        writes.append((temp_path, int(temp)))
        writes.append((pwm_path, int(pwm)))
    return _write_sysfs_batch(writes)


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
    if enabled:
        return _write_sysfs_batch([(path, "1")])

    preferred = _preferred_disable_mode(path)
    ok, err = _write_sysfs_batch([(path, preferred)])
    if ok:
        return True, ""

    # Some devices accept only one of {0,2}; retry the alternative when the
    # kernel reports EINVAL.
    if "Invalid argument" in (err or ""):
        fallback = "2" if preferred == "0" else "0"
        return _write_sysfs_batch([(path, fallback)])

    return False, err
