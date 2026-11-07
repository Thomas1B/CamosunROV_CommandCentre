"""Camera recordings (console REC button) read back for the main menu's VIEW RECORDINGS page.

    list_recordings()        every recordings/*.mkv, newest first (start time, vehicle, size, length)
    events_for(recording)    every event logged while that file was recording, from logs/*.csv
                             (the "video_time" / "video_file" columns written by the console)
    marks_for(recording)     just the operator marks (MARK rows) of those
"""

import csv

from command_center_py import filenames
from command_center_py.config import LOGS_DIR, RECORDINGS_DIR

try:
    import av
except ImportError:             # the page still lists files; playing needs PyAV
    av = None



def parse_clock(text):
    """'02:14' / '1:02:14' -> seconds (float), or None."""
    try:
        parts = [float(p) for p in str(text).strip().split(":")]
    except ValueError:
        return None
    if not parts or len(parts) > 3:
        return None
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def clock(seconds):
    """seconds -> 'mm:ss' (or 'h:mm:ss')."""
    s = max(0, int(seconds))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def probe_length(path):
    """Length of a recording in seconds, or None. Uses the file's own duration when it was
    closed normally; after a crash (no duration written) it reads the packet times instead."""
    if av is None:
        return None
    try:
        with av.open(str(path)) as c:
            if c.duration:
                return c.duration / 1_000_000
            s = c.streams.video[0]
            last = None
            for pk in c.demux(s):
                if pk.pts is not None:
                    last = pk.pts
            return float(last * s.time_base) if last is not None else None
    except Exception:
        return None


class Recording:
    def __init__(self, path):
        self.path = path
        self.started, self.vehicle, _ = filenames.parse(path.stem)     # new or old file-name layout
        try:
            self.size = path.stat().st_size
        except OSError:
            self.size = 0
        self.length = probe_length(path)

    def size_text(self):
        mb = self.size / 1e6
        return f"{mb:.1f} MB" if mb >= 1 else f"{self.size / 1e3:.0f} kB"

    def delete(self):
        """Deletes the file. Returns an error message, or None."""
        try:
            self.path.unlink()
            return None
        except FileNotFoundError:
            return None
        except OSError as e:
            return f"Could not delete {self.path.name} — {e}"


def list_recordings():
    if not RECORDINGS_DIR.is_dir():
        return []
    return [Recording(p) for p in filenames.newest_first(RECORDINGS_DIR.glob("*.mkv"))]


def _mark_summary(r):
    bits = []
    if r.get("depth_m"):
        bits.append(f"depth {float(r['depth_m']):.1f} m")
    if r.get("heading_deg"):
        bits.append(f"heading {float(r['heading_deg']):03.0f}° {r.get('heading_cardinal', '')}".strip())
    if r.get("water_temp_c"):
        bits.append(f"water {float(r['water_temp_c']):.1f} °C")
    if r.get("leak") == "LEAK":
        bits.append("LEAK")
    return " · ".join(bits) or "operator mark"


def events_for(recording):
    """[(seconds, local_time, tag, text)] for every log row whose video_file is this recording,
    by video time. MARK rows get a short telemetry summary; other rows their message.
    (Logs from before this was added only stamped MARK rows, so older recordings show marks only.)"""
    out = []
    if not LOGS_DIR.is_dir():
        return out
    name = recording.path.name
    for log in LOGS_DIR.glob("*.csv"):
        try:
            with open(log, newline="", encoding="utf-8-sig") as f:
                for n, r in enumerate(csv.DictReader(f)):
                    if r.get("video_file") != name:
                        continue
                    t = parse_clock(r.get("video_time", ""))
                    if t is None:
                        continue
                    tag = r.get("tag", "")
                    text = _mark_summary(r) if tag == "MARK" else r.get("message", "")
                    out.append((t, r.get("local_time", ""), n, tag, text))
        except (OSError, csv.Error, UnicodeDecodeError, ValueError):
            continue
    out.sort()                                  # by video time, then log time, then file order
    return [(t, local[11:19], tag, text) for t, local, _, tag, text in out]


def marks_for(recording):
    """[(seconds, local_time, summary)] for the MARK rows of events_for(recording)."""
    return [(t, local, text) for t, local, tag, text in events_for(recording) if tag == "MARK"]
