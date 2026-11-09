"""Camera recordings (console REC button) read back for the main menu's VIEW RECORDINGS page.

    list_recordings()        every recordings/*.mkv, newest first (start time, vehicle, size, length)
    events_for(recording)    every event logged while that file was recording, from logs/*.csv
                             (the "video_time" / "video_file" columns written by the console)
    marks_for(recording)     just the operator marks (MARK rows) of those
    event_rows(recording)    the same events as full log rows (all columns), for EXPORT
    export_mp4(rec, path)    copy the video into an .mp4 (no re-encoding; see below)
    export_events(rec, path) the recording's events as .csv or .xlsx, with video times
"""

import csv
from pathlib import Path

from command_center_py import filenames
from command_center_py.config import LOGS_DIR, RECORDINGS_DIR

from command_center_py import avlib       # PyAV, loaded on first use; without it the page still lists files



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
    av = avlib.get()
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


def event_rows(recording):
    """Full log rows (dicts with every event-log column) recorded while this file was
    recording, sorted by video time. Telemetry numbers are converted back to numbers."""
    from command_center_py.event_log import SNAPSHOT_FIELDS
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
                    for k in SNAPSHOT_FIELDS:
                        v = r.get(k)
                        if v not in (None, "") and k not in ("heading_cardinal", "leak", "video_time", "video_file"):
                            try:
                                r[k] = float(v)
                            except ValueError:
                                pass
                    out.append((t, r.get("local_time", ""), n, r))
        except (OSError, csv.Error, UnicodeDecodeError, ValueError):
            continue
    out.sort(key=lambda x: x[:3])
    return [r for *_, r in out]


def export_mp4(recording, path, progress=None):
    """Copy a recording into an .mp4 that plays anywhere (phones, PowerPoint, Teams, browsers).
    The H.264 packets are copied as they are - no decoding or re-encoding - so it takes
    seconds and keeps full quality. Written to "<path>.part" first and renamed at the end,
    so a cancelled or failed export never leaves a half-written .mp4 behind.
    progress(fraction 0..1) is called as it goes (from the calling thread). Raises on error."""
    av = avlib.get()
    if av is None:
        raise RuntimeError("PyAV not installed — run: python -m pip install -r py_requirements.txt")
    path = Path(path)
    tmp = path.with_name(path.name + ".part")
    length = recording.length or probe_length(recording.path) or 0.0
    try:
        with av.open(str(recording.path)) as src:
            ist = src.streams.video[0]
            # faststart: the index goes at the front, so the file starts playing before it has
            # fully downloaded (Teams, browsers, phones)
            with av.open(str(tmp), mode="w", format="mp4", options={"movflags": "+faststart"}) as dst:
                ost = dst.add_stream_from_template(ist)
                last = -1.0
                for pkt in src.demux(ist):
                    if pkt.dts is None:            # flush packet at the end of the file
                        continue
                    if progress and length and pkt.pts is not None:
                        f = min(1.0, float(pkt.pts * ist.time_base) / length)
                        if f - last >= 0.01:
                            last = f
                            progress(f)
                    pkt.stream = ost
                    dst.mux(pkt)
        tmp.replace(path)                          # overwrites an existing file of that name
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    if progress:
        progress(1.0)
    return path


def export_events(recording, path):
    """The recording's events with their video times, as .csv or .xlsx (by the extension).
    Same columns as the session log, with VIDEO TIME first. Returns the number of events."""
    from command_center_py.event_log import FIELDS, MARK_COLS, export_xlsx
    rows = event_rows(recording)
    lead = ["video_time"]
    if str(path).lower().endswith(".xlsx"):
        export_xlsx(rows, str(path), recording.vehicle,
                    mark_cols=lead + [c for c in MARK_COLS if c not in ("video_time", "video_file")],
                    event_cols=lead + ["local_time", "utc_offset", "utc_time", "tag", "message"],
                    title=f"Camosun ROV recording events {recording.path.name}")
    else:
        cols = lead + [c for c in FIELDS if c not in ("video_time", "video_file")]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:   # BOM: Excel shows ° and — right
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return len(rows)


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
