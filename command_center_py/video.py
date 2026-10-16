"""Live camera video from the ROV: H.264 in MPEG-TS over UDP, decoded with PyAV.

The Pi's camera_stream.py sends to this laptop's UDP VIDEO_PORT (5602). This
module receives and decodes it in a background thread and keeps only the newest
frame as a QImage; the console's VideoPane paints it under the HUD.

    rx = VideoReceiver(5602)      # starts listening straight away
    img, frame_id, status = rx.latest()
    rx.stop()

No numpy or Pillow needed - frames are converted to RGB by FFmpeg (inside PyAV)
and wrapped straight into a QImage. QImage (unlike QPixmap) is safe to build
outside the GUI thread.

If PyAV isn't installed the console still runs; the video area just says so.
"""

import threading
import time

from PySide6.QtGui import QImage

try:
    import av
    AV_ERROR = None
except ImportError as exc:        # e.g. venv built before av was added to py_requirements.txt
    av = None
    AV_ERROR = str(exc)

OPEN_TIMEOUT_S = 2.0    # waiting for the stream to start (Pi still booting, camera off)
READ_TIMEOUT_S = 0.5    # stream stopped mid-way -> reopen and wait again (also bounds stop())
RETRY_DELAY_S = 0.5


class VideoReceiver:
    def __init__(self, port):
        self.port = port
        self._lock = threading.Lock()
        self._image = None
        self._frame_id = 0
        self.status = "waiting for camera stream"
        self.size = None              # (w, h) of the stream once it is decoding
        self.fps = 0.0
        self._stop = threading.Event()
        self._thread = None
        if av is None:
            self.status = "PyAV not installed - run: python -m pip install -r py_requirements.txt"
            return
        self._thread = threading.Thread(target=self._run, name="video-rx", daemon=True)
        self._thread.start()

    def latest(self):
        """(QImage or None, frame counter, status text). The counter only changes on a new frame."""
        with self._lock:
            return self._image, self._frame_id, self.status

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=READ_TIMEOUT_S + 1.0)

    # ---------------- receive thread ----------------
    def _run(self):
        # overrun_nonfatal + a big fifo: if the decoder falls behind briefly, drop
        # old packets rather than erroring out. listen on all interfaces.
        url = (f"udp://0.0.0.0:{self.port}"
               f"?overrun_nonfatal=1&fifo_size=1000000&buffer_size=4194304")
        while not self._stop.is_set():
            try:
                self._receive(url)
            except Exception as exc:          # timeout, corrupt stream, port busy...
                if self._stop.is_set():
                    break
                with self._lock:
                    if self._image is None:
                        self.status = f"waiting for camera stream on UDP {self.port}"
                    else:
                        self.status = f"waiting for camera stream on UDP {self.port}"
                    if "Address already in use" in str(exc) or "bind" in str(exc).lower():
                        self.status = f"UDP {self.port} is in use by another program (ffplay/VLC?)"
                self._stop.wait(RETRY_DELAY_S)

    def _receive(self, url):
        container = av.open(
            url, format="mpegts",
            options={"fflags": "nobuffer", "probesize": "500000", "analyzeduration": "500000"},
            timeout=(OPEN_TIMEOUT_S, READ_TIMEOUT_S),
        )
        try:
            stream = container.streams.video[0]
            ctx = stream.codec_context
            try:
                ctx.options = {"flags": "low_delay"}     # output each frame as soon as it decodes
            except Exception:
                pass
            t0, n = time.monotonic(), 0
            for packet in container.demux(stream):
                if self._stop.is_set():
                    return
                for frame in packet.decode():
                    img = self._to_qimage(frame)
                    n += 1
                    now = time.monotonic()
                    with self._lock:
                        self._image = img
                        self._frame_id += 1
                        self.size = (frame.width, frame.height)
                        if now - t0 >= 1.0:
                            self.fps = n / (now - t0)
                            t0, n = now, 0
                        self.status = (f"live {frame.width}x{frame.height}"
                                       + (f" @ {self.fps:.0f} fps" if self.fps else ""))
        finally:
            container.close()

    @staticmethod
    def _to_qimage(frame):
        rgb = frame.reformat(format="rgb24")
        plane = rgb.planes[0]
        # bytes() copies out of FFmpeg's buffer; line_size includes any row padding.
        data = bytes(plane)
        img = QImage(data, rgb.width, rgb.height, plane.line_size, QImage.Format.Format_RGB888)
        return img.copy()        # deep copy so the QImage no longer points at `data`
