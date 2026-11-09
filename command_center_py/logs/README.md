# logs

The session event log: writing it to disk, reading saved logs back, and exporting them.

| File | What it does |
|---|---|
| `event_log.py` | `EventLogFile` writes every line of the console's EVENT LOG to a CSV file in `logs/` as it happens. `SavedLog` and `list_logs()` read saved logs back for VIEW LOGS. `export_csv()` and `export_xlsx()` save copies. |
| `filenames.py` | The shared file-name format for logs and recordings: `<vehicle>_<YYYY-MM-DD_HH-MM-SS>` (for example `ROV-01_2026-11-01_22-36-54.csv`), plus reading the vehicle and start time back out of a name and sorting newest first. |

**Used by:** the console (writes the log), the exit dialogs, the VIEW LOGS card, and `video/recordings.py` (events shown with a recording).

**Related settings in `config.py`:** `LOGS_DIR`.

This folder holds code only. The saved log files go in the `logs/` folder at the top of the repo.
