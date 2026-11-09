# video

The camera: the live feed from the ROV, REC, and playing recordings back.

| File | What it does |
|---|---|
| `avlib.py` | Loads PyAV (FFmpeg) in the background after the main menu appears, so the program starts faster. |
| `receiver.py` | `VideoReceiver` receives and decodes the live H.264 stream from the Pi in its own thread, and saves it to `recordings/` while REC is on. |
| `player.py` | `VideoPlayer` plays a saved recording for VIEW RECORDINGS (play, pause, seek). |
| `recordings.py` | Lists the files in `recordings/`, finds the events logged during each one, and exports a recording as MP4 or its events as CSV / Excel. |

**Used by:** the console (live feed and REC) and the VIEW RECORDINGS card.

**Related settings in `config.py`:** `VIDEO_PORT`, `VIDEO_STALE_S`, `RECORDINGS_DIR`.

This folder holds code only. The recordings go in the `recordings/` folder at the top of the repo.
