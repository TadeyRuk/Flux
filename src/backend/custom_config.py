"""Persistence for the Custom TDP power profile."""

import json
import os
import tempfile
from datetime import datetime, timezone

CUSTOM_PROFILE_PATH = os.path.expanduser("~/.local/share/flux/custom_profile.json")

DEFAULT_CONFIG = {
    "version": 1,
    "tdp": {"spl_w": 25, "sppt_w": 30, "fppt_w": 35},
    "last_applied": None,
    "notes": "Custom TDP profile — not auto-applied on boot",
}


def load_custom_config():
    """Load custom profile config. Returns DEFAULT_CONFIG on missing or corrupt file."""
    try:
        with open(CUSTOM_PROFILE_PATH) as f:
            data = json.load(f)
        # Ensure expected keys are present
        if "tdp" not in data or not all(k in data["tdp"] for k in ("spl_w", "sppt_w", "fppt_w")):
            return dict(DEFAULT_CONFIG)
        return data
    except (OSError, json.JSONDecodeError, KeyError):
        return dict(DEFAULT_CONFIG)


def save_custom_config(spl_w, sppt_w, fppt_w, mark_applied=False):
    """Atomically save custom TDP config."""
    data = {
        "version": 1,
        "tdp": {"spl_w": int(spl_w), "sppt_w": int(sppt_w), "fppt_w": int(fppt_w)},
        "last_applied": datetime.now(timezone.utc).isoformat() if mark_applied else None,
        "notes": "Custom TDP profile — not auto-applied on boot",
    }
    dirpath = os.path.dirname(CUSTOM_PROFILE_PATH)
    os.makedirs(dirpath, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dirpath, suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, CUSTOM_PROFILE_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
