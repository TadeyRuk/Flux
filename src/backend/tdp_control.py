"""CPU TDP control via asus-nb-wmi sysfs or ryzenadj."""

import os
import shutil
import subprocess

_ASUS_WMI_BASE = "/sys/devices/platform/asus-nb-wmi"
_PPT_SPL  = _ASUS_WMI_BASE + "/ppt_pl1_spl"   # sustained / STAPM
_PPT_SPPT = _ASUS_WMI_BASE + "/ppt_pl2_sppt"  # slow package
_PPT_FPPT = _ASUS_WMI_BASE + "/ppt_fppt"      # fast / boost


def _write_sysfs_batch(writes):
    """Write multiple values to sysfs files in a single pkexec call.
    writes = list of (path, value) tuples.
    Returns (success, error_msg).
    Copied from fan_control.py — same privilege-escalation pattern.
    """
    if not writes:
        return True, ""

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

        cmds = []
        for path, value in failed_writes:
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


def detect_backend():
    """Detect available TDP backend.
    Returns 'asus-wmi', 'ryzenadj', or None.
    """
    if all(os.path.exists(p) for p in (_PPT_SPL, _PPT_SPPT, _PPT_FPPT)):
        return "asus-wmi"
    if shutil.which("ryzenadj"):
        return "ryzenadj"
    return None


TDP_BACKEND = detect_backend()


def get_current_tdp():
    """Read current TDP values in watts.
    Returns dict{'spl': int, 'sppt': int, 'fppt': int} or None on failure.
    """
    if TDP_BACKEND == "asus-wmi":
        try:
            result = {}
            for key, path in (("spl", _PPT_SPL), ("sppt", _PPT_SPPT), ("fppt", _PPT_FPPT)):
                with open(path) as f:
                    result[key] = int(f.read().strip())
            return result
        except (OSError, ValueError):
            return None

    if TDP_BACKEND == "ryzenadj":
        try:
            out = subprocess.run(
                ["ryzenadj", "--info"],
                capture_output=True, text=True, timeout=5,
            )
            lines = out.stdout.splitlines()
            vals = {}
            for line in lines:
                if "STAPM LIMIT" in line:
                    vals["spl"] = int(float(line.split("|")[2].strip()) / 1000)
                elif "PPT LIMIT SLOW" in line:
                    vals["sppt"] = int(float(line.split("|")[2].strip()) / 1000)
                elif "PPT LIMIT FAST" in line:
                    vals["fppt"] = int(float(line.split("|")[2].strip()) / 1000)
            if len(vals) == 3:
                return vals
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass

    return None


def apply_tdp(spl_w, sppt_w, fppt_w):
    """Apply TDP values (in watts). Returns (success, error_msg)."""
    if TDP_BACKEND == "asus-wmi":
        writes = [
            (_PPT_SPL,  spl_w),
            (_PPT_SPPT, sppt_w),
            (_PPT_FPPT, fppt_w),
        ]
        return _write_sysfs_batch(writes)

    if TDP_BACKEND == "ryzenadj":
        try:
            result = subprocess.run(
                [
                    "pkexec", "ryzenadj",
                    f"--stapm-limit={spl_w * 1000}",
                    f"--slow-limit={sppt_w * 1000}",
                    f"--fast-limit={fppt_w * 1000}",
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr.strip() or f"ryzenadj failed with code {result.returncode}"
        except FileNotFoundError:
            return False, "pkexec not found"
        except subprocess.TimeoutExpired:
            return False, "Timeout waiting for authentication"
        except Exception as e:
            return False, str(e)

    return False, "No TDP backend available (asus-nb-wmi not found, ryzenadj not installed)"


def reset_tdp():
    """Reset TDP to firmware defaults. Returns (success, error_msg).
    For asus-wmi: writes 0 to all three files (firmware takes over).
    For ryzenadj: no reliable reset mechanism — returns success no-op.
    """
    if TDP_BACKEND == "asus-wmi":
        writes = [(_PPT_SPL, 0), (_PPT_SPPT, 0), (_PPT_FPPT, 0)]
        return _write_sysfs_batch(writes)

    if TDP_BACKEND == "ryzenadj":
        return True, ""  # ryzenadj has no reset; values are volatile anyway

    return False, "No TDP backend available"
