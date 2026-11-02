"""Plays a recording (.mkv from the console's REC button) for the VIEW RECORDINGS page.

    p = VideoPlayer()
    p.open("recordings/....mkv")     # shows the first frame, paused
    p.play() / p.pause() / p.toggle()
    p.seek(73.5)                     # seconds; lands on the exact frame (decodes from the key frame before)
    img, pos, length, playing = p.state()
    p.close()                        # releases the file (Windows can't delete an open file)

Decoding runs in a background thread with PyAV (already used for the live camera), so
nothing extra has to be installed. Frames are shown at the speed they were recorded:
each frame waits for its own timestamp. Playback stops at the end, on the last frame.
"""

import threading
import time

from PySide6.QtGui import QImage

try:
    import av
except ImportError:
    av = None


def _to_qimage(frame):
    rgb = frame.reformat(format="rgb24")
    plane = rgb.planes[0]
    data = bytes(plane)
    return QImage(data, rgb.width, rgb.height, plane.line_size, QImage.Format.Format_RGB888).copy()


class VideoPlayer:
    def __init__(self):
        self._lock = threading.Lock()
        self._cmd = threading.Condition(self._lock)
        self._thread = None
        self._path = None
        self._image = None
        self._pos = 0.0
        self._length = None
        self._playing = False
        self._seek_to = None
        self._stop = False
        self._at_end = False
        self.error = None

    # ---------------- control (GUI thread) ----------------
    def open(self, path, length=None):
        """Open a file and show its first frame (paused). length: known length in s, if any."""
        self.close()
        if av is None:
            self.error = "PyAV not installed — run: python -m pip install -r py_requirements.txt"
            return
        with self._lock:
            self._path, self._length, self._image = str(path), length, None
            self._pos, self._playing, self._seek_to, self._stop, self._at_end = 0.0, False, 0.0, False, False
            self.error = None
        self._thread = threading.Thread(target=self._run, name="video-player", daemon=True)
        self._thread.start()

    def close(self):
        with self._cmd:
            self._stop = True
            self._cmd.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._thread = None
        with self._lock:
            self._path, self._image, self._playing = None, None, False

    def play(self):
        with self._cmd:
            if self._path is None:
                return
            if self._at_end:                         # at the end: play again from the start
                self._seek_to, self._at_end = 0.0, False
            self._playing = True
            self._cmd.notify_all()

    def pause(self):
        with self._cmd:
            self._playing = False
            self._cmd.notify_all()

    def toggle(self):
        with self._lock:
            playing = self._playing
        self.pause() if playing else self.play()

    def seek(self, seconds):
        with self._cmd:
            if self._path is None:
                return
            hi = self._length if self._length else seconds
            self._seek_to = max(0.0, min(seconds, hi))
            self._at_end = False
            self._cmd.notify_all()

    def state(self):
        """(QImage or None, position s, length s or None, playing)."""
        with self._lock:
            return self._image, self._pos, self._length, self._playing

    # ---------------- decode thread ----------------
    def _show(self, frame, t):
        img = _to_qimage(frame)
        with self._lock:
            self._image, self._pos = img, t

    def _run(self):
        try:
            container = av.open(self._path)
        except Exception as e:
            with self._lock:
                self.error = f"Can't open {self._path} — {e}"
            return
        try:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            tb = float(stream.time_base)
            frames = None
            clock0 = None                       # (wall time, video time) when playing (re)started
            while True:
                with self._cmd:
                    while not self._stop and self._seek_to is None and not self._playing:
                        self._cmd.wait()
                    if self._stop:
                        return
                    seek_to, self._seek_to = self._seek_to, None
                    playing = self._playing
                if seek_to is not None:
                    # jump to the key frame before seek_to, then decode up to the exact frame
                    container.seek(int(seek_to / tb), stream=stream, backward=True, any_frame=False)
                    frames = container.decode(stream)
                    shown = None
                    for f in frames:
                        t = float(f.pts * tb) if f.pts is not None else 0.0
                        shown = (f, t)
                        if t >= seek_to - 0.5 * (1 / 30):
                            break
                    if shown:
                        self._show(*shown)
                    clock0 = None
                    continue
                if not playing:
                    clock0 = None
                    continue
                if frames is None:
                    frames = container.decode(stream)
                try:
                    f = next(frames)
                except StopIteration:            # end of file: stop on the last frame
                    with self._lock:
                        self._playing, self._at_end = False, True
                        if not self._length:
                            self._length = self._pos
                    frames = None
                    continue
                t = float(f.pts * tb) if f.pts is not None else self._pos
                if clock0 is None:
                    clock0 = (time.monotonic(), t)
                wait = clock0[0] + (t - clock0[1]) - time.monotonic()
                if wait > 0:
                    with self._cmd:                # wait for the frame's time, but react to pause / seek
                        self._cmd.wait_for(lambda: self._stop or self._seek_to is not None or not self._playing,
                                           timeout=wait)
                self._show(f, t)
        except Exception as e:
            with self._lock:
                self.error = f"Playback stopped — {e}"
                self._playing = False
        finally:
            container.close()
