"""Fan curve profile storage via JSON."""

import json
import os
import tempfile

PROFILES_PATH = os.path.expanduser("~/.local/share/flux/fan_profiles.json")


def _load_data():
    """Load profiles JSON. Returns empty structure if missing/corrupt."""
    try:
        with open(PROFILES_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"default": None, "profiles": {}}


def _save_data(data):
    """Write profiles JSON atomically."""
    dirpath = os.path.dirname(PROFILES_PATH)
    os.makedirs(dirpath, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dirpath, suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, PROFILES_PATH)
    except Exception:
        os.unlink(tmp)
        raise


def _points_to_list(points):
    """Convert [(temp, pwm), ...] to [[temp, pwm], ...] for JSON."""
    return [[int(t), int(p)] for t, p in points]


def _list_to_points(lst):
    """Convert [[temp, pwm], ...] back to [(temp, pwm), ...]."""
    return [(t, p) for t, p in lst]


def init_defaults(fan1_points, fan2_points):
    """Store the default fan curves on first launch. No-op if already stored."""
    data = _load_data()
    if data.get("default") is not None:
        return
    data["default"] = {
        "fan1": _points_to_list(fan1_points),
        "fan2": _points_to_list(fan2_points),
    }
    _save_data(data)


def get_default():
    """Return stored default curves as {fan1: [(t,p),...], fan2: [(t,p),...]}."""
    data = _load_data()
    default = data.get("default")
    if default is None:
        return None
    return {
        "fan1": _list_to_points(default["fan1"]),
        "fan2": _list_to_points(default["fan2"]),
    }


def get_profile_names():
    """Return sorted list of user profile names."""
    data = _load_data()
    return sorted(data.get("profiles", {}).keys())


def get_profile(name):
    """Load a profile by name. Returns {fan1: [...], fan2: [...]} or None."""
    data = _load_data()
    prof = data.get("profiles", {}).get(name)
    if prof is None:
        return None
    return {
        "fan1": _list_to_points(prof["fan1"]),
        "fan2": _list_to_points(prof["fan2"]),
    }


def save_profile(name, fan1_points, fan2_points):
    """Save or update a user profile."""
    data = _load_data()
    if "profiles" not in data:
        data["profiles"] = {}
    data["profiles"][name] = {
        "fan1": _points_to_list(fan1_points),
        "fan2": _points_to_list(fan2_points),
    }
    _save_data(data)


def delete_profile(name):
    """Delete a user profile. Returns True if it existed."""
    data = _load_data()
    profiles = data.get("profiles", {})
    if name not in profiles:
        return False
    del profiles[name]
    _save_data(data)
    return True
