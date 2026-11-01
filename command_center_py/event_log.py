"""
Event log file: every line of the console's EVENT LOG, saved to a CSV file.

One file per console session in LOGS_DIR (config.py), named by the local start time and
the vehicle, e.g. logs/2026-10-31_23-44-18_DEMO.csv. Opens in Excel (UTF-8 with BOM, so
°, — and · show correctly).

Columns, one row per event, SI units:
    local_time        2026-10-31 23:44:18.123   (this laptop's clock and time zone)
    utc_offset        -07:00                    (local_time minus UTC)
    utc_time          2026-11-01 06:44:18.123
    tag               SYS, CFG, LINK, MARK, ...  (same as the on-screen log)
    message           the on-screen text
    depth_m ... leak  telemetry snapshot - only filled on MARK (operator mark) rows,
                      empty where the value was not available (sensor faulted, link down)

Each row is written straight to disk (flushed), so the file is complete up to the last
event even if the program or laptop crashes.
"""

import csv
import re
from datetime import datetime, timezone

from command_center_py.config import LOGS_DIR

SNAPSHOT_FIELDS = ["depth_m", "rel_depth_m", "pressure_kpa", "water_temp_c", "internal_temp_c",
                   "roll_deg", "pitch_deg", "yaw_deg", "heading_deg", "heading_cardinal",
                   "battery_v", "leak"]
FIELDS = ["local_time", "utc_offset", "utc_time", "tag", "message"] + SNAPSHOT_FIELDS

# Column headings (SI units) for the exit preview, Excel and PDF exports.
LABELS = {"local_time": "Local time", "utc_offset": "UTC offset", "utc_time": "UTC time",
          "tag": "Tag", "message": "Message", "depth_m": "Depth (m)", "rel_depth_m": "Rel. depth (m)",
          "pressure_kpa": "Pressure (kPa)", "water_temp_c": "Water (°C)", "internal_temp_c": "Internal (°C)",
          "roll_deg": "Roll (°)", "pitch_deg": "Pitch (°)", "yaw_deg": "Yaw (°)",
          "heading_deg": "Heading (°)", "heading_cardinal": "Compass", "battery_v": "Battery (V)",
          "leak": "Leak"}
EVENT_COLS = ["local_time", "utc_time", "tag", "message"]
MARK_COLS = ["local_time", "utc_time"] + SNAPSHOT_FIELDS


def _offset(dt):
    """UTC offset of an aware datetime as +HH:MM / -HH:MM."""
    mins = round(dt.utcoffset().total_seconds() / 60)
    sign = "-" if mins < 0 else "+"
    return f"{sign}{abs(mins) // 60:02d}:{abs(mins) % 60:02d}"


def _stamp(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


class EventLogFile:
    """Writes event-log rows to a new CSV file. Never raises: if the file can't be
    opened or written, `error` says why and the console carries on without it."""

    def __init__(self, vehicle):
        self.vehicle = vehicle or "ROV"
        self.rows = []          # every row also kept in memory: exit preview and exports
        self.path = None
        self.error = None
        self._f = None
        self._w = None
        start = datetime.now().astimezone()
        name = re.sub(r"[^A-Za-z0-9_-]+", "_", vehicle or "").strip("_") or "ROV"
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            self.path = LOGS_DIR / f"{start:%Y-%m-%d_%H-%M-%S}_{name}.csv"
            n = 2
            while self.path.exists():   # two consoles opened in the same second
                self.path = LOGS_DIR / f"{start:%Y-%m-%d_%H-%M-%S}_{name}_{n}.csv"
                n += 1
            self._f = open(self.path, "w", newline="", encoding="utf-8-sig")
            self._w = csv.DictWriter(self._f, fieldnames=FIELDS, extrasaction="ignore")
            self._w.writeheader()
            self._f.flush()
        except OSError as e:
            self.error = f"Event log file not saved — {e}"
            self._f = None

    def write(self, when_utc, tag, msg, snapshot=None):
        """when_utc: aware datetime in UTC. snapshot: dict of SNAPSHOT_FIELDS (MARK rows)."""
        local = when_utc.astimezone()
        row = {"local_time": _stamp(local), "utc_offset": _offset(local),
               "utc_time": _stamp(when_utc.astimezone(timezone.utc)), "tag": tag, "message": msg}
        for k, v in (snapshot or {}).items():
            row[k] = "" if v is None else v
        self.rows.append(row)
        if self._f is None:
            return
        try:
            self._w.writerow(row)
            self._f.flush()
        except OSError as e:
            self.error = f"Event log file stopped — {e}"
            self.close()

    def close(self):
        if self._f is not None:
            try:
                self._f.close()
            except OSError:
                pass
            self._f = None

    def marks(self):
        return [r for r in self.rows if r["tag"] == "MARK"]

    def discard(self):
        """Deletes this session's file from logs/. Returns an error message, or None."""
        self.close()
        if self.path is None or not self.path.exists():
            return None
        try:
            self.path.unlink()
            return None
        except OSError as e:
            return f"Could not delete {self.path.name} — {e}"


def export_csv(rows, path):
    """Same columns as the session file."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def export_xlsx(rows, path, vehicle=""):
    """Excel workbook: a 'Marks' sheet (one column per telemetry value) and an 'Events' sheet.
    Times are real Excel date-times, numbers are numbers. Needs openpyxl."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    def when(s):
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f") if s else None

    wb = Workbook()
    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F2933")
    for title, cols, data in (("Marks", MARK_COLS, [r for r in rows if r["tag"] == "MARK"]),
                              ("Events", ["local_time", "utc_offset", "utc_time", "tag", "message"], rows)):
        ws = wb.active if title == "Marks" else wb.create_sheet(title)
        ws.title = title
        ws.append([LABELS[c] for c in cols])
        for cell in ws[1]:
            cell.font, cell.fill = head_font, head_fill
            cell.alignment = Alignment(horizontal="center")
        for r in data:
            ws.append([when(r.get(c)) if c in ("local_time", "utc_time")
                       else (None if r.get(c, "") == "" else r.get(c)) for c in cols])
        for i, c in enumerate(cols, 1):
            letter = get_column_letter(i)
            if c in ("local_time", "utc_time"):
                for cell in ws[letter][1:]:
                    cell.number_format = "yyyy-mm-dd hh:mm:ss.000"
                width = 24
            elif c == "message":
                width = 90
            else:
                width = max(10, len(LABELS[c]) + 2)
            ws.column_dimensions[letter].width = width
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    wb.properties.title = f"Camosun ROV event log {vehicle}".strip()
    wb.save(path)
