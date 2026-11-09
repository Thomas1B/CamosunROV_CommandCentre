"""File names for saved session logs (logs/) and camera recordings (recordings/).

New files start with the vehicle name, then the local start time:

    ROV-01_2026-11-01_22-36-54.csv      (a second file in the same second gets _2, _3, ...)
    ROV-01_2026-11-01_22-36-54.mkv

Exports and saved frames are named after these files, so they start with the vehicle too.
"""

import re

_STEM = re.compile(r"^(?P<v>.+?)_(?P<d>\d{4}-\d{2}-\d{2})_(?P<H>\d{2})-(?P<M>\d{2})-(?P<S>\d{2})(?:_(?P<n>\d+))?$")


def safe_vehicle(vehicle):
    """Vehicle name as it goes in a file name: letters, digits, - and _ only."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", vehicle or "").strip("_") or "ROV"


def stem(vehicle, start, n=1):
    """'ROV-01_2026-11-01_22-36-54' (n > 1 adds '_n'). start: a datetime (local time)."""
    s = f"{safe_vehicle(vehicle)}_{start:%Y-%m-%d_%H-%M-%S}"
    return s if n <= 1 else f"{s}_{n}"


def parse(file_stem):
    """(started 'YYYY-MM-DD HH:MM:SS', vehicle, sort key) from a file name without its
    extension. Unrecognised names: (stem, '?', key that sorts last)."""
    m = _STEM.match(file_stem)
    if m:
        started = f"{m['d']} {m['H']}:{m['M']}:{m['S']}"
        return started, m["v"], (started, int(m["n"] or 1))
    return file_stem, "?", ("", 0)


def newest_first(paths):
    """Paths sorted by the start time in their names, newest first (whatever the vehicle)."""
    return sorted(paths, key=lambda p: (parse(p.stem)[2], p.name), reverse=True)
