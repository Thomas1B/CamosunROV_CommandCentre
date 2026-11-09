"""PyAV (FFmpeg), loaded on first use instead of at program start.

PyAV pulls in the FFmpeg libraries, which are big and slow to load (most of all on
Windows), and only the console's camera, REC and VIEW RECORDINGS need them. So the
main menu opens without them; app.py calls prewarm() once the menu is on screen, which
loads PyAV in a background thread while the operator is still picking an option.

    av = avlib.get()      # the av module, or None if PyAV isn't installed (avlib.error says why)
"""

import threading

_lock = threading.Lock()
_av = None
_tried = False
error = None


def get():
    """The av module (imports it the first time; waits if prewarm() is still loading it)."""
    global _av, _tried, error
    with _lock:
        if not _tried:
            _tried = True
            try:
                import av
                _av = av
            except ImportError as exc:      # e.g. venv built before av was added to py_requirements.txt
                error = str(exc)
        return _av


def prewarm():
    """Start loading PyAV in the background (returns at once)."""
    threading.Thread(target=get, name="load-pyav", daemon=True).start()
