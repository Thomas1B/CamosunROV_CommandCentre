"""Saved vehicle profiles: one JSON file per vehicle in <top dir>/vehicle_profiles/.

File contents, e.g. vehicle_profiles/ROV-01.json:
    {"name": "ROV-01", "ip": "192.168.2.2", "cmd_port": 5600, "telem_port": 5601}
"""

import json
import re

from command_center_py.config import CMD_PORT, PROFILES_DIR, TELEM_PORT


def _file_for(name):
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "vehicle"
    return PROFILES_DIR / f"{safe}.json"


def _read(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not str(data.get("name", "")).strip() or not data.get("ip"):
        return None
    return {
        "name": str(data["name"]).strip(),
        "ip": str(data["ip"]).strip(),
        "cmd_port": int(data.get("cmd_port", CMD_PORT)),
        "telem_port": int(data.get("telem_port", TELEM_PORT)),
        "_path": path,
    }


def load_profiles():
    """All valid profiles, sorted by name. Unreadable files are skipped."""
    if not PROFILES_DIR.is_dir():
        return []
    found = {}
    for path in sorted(PROFILES_DIR.glob("*.json")):
        p = _read(path)
        if p is not None:
            found[p["name"]] = p
    return sorted(found.values(), key=lambda p: p["name"].lower())


def save_profile(name, ip, cmd_port, telem_port):
    """Create or overwrite the profile called name. Raises OSError if it can't be written."""
    delete_profile(name)                       # drop any older file holding this name
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "ip": ip, "cmd_port": int(cmd_port), "telem_port": int(telem_port)}
    _file_for(name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def delete_profile(name):
    for p in load_profiles():
        if p["name"] == name:
            try:
                p["_path"].unlink()
            except OSError:
                pass
