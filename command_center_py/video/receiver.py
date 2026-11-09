"""Live camera video from the ROV: H.264 in MPEG-TS over UDP, decoded with PyAV.

The Pi's camera_stream.py sends to this laptop's UDP VIDEO_PORT (5602). This
module receives and decodes it in a background thread and keeps only the newest
frame as a QImage; the console's VideoPane paints it under the HUD.

    rx = VideoReceiver(5602)      # starts listening straight away
    img, frame_id, status = rx.latest()
    rx.stop()

No numpy or Pillow needed. Each frame is scaled to the size it is shown at and
converted to Qt's native 32-bit format by FFmpeg (inside PyAV), in this thread, and
wrapped in a QImage without copying, so the console only has to copy it to the screen.
QImage (unlike QPixmap) is safe to build outside the GUI thread.

Low latency: the console sets on_frame, which is called (from this thread) as soon as a
frame is ready, so it is drawn straight away instead of on the next UI timer tick. It
also calls set_view_size() whenever the video area changes size.

Recording (console REC button):
    rx.start_recording("recordings/ROV-01_2026-11-01_18-40-05.mkv")
    rx.recording()        # {"state": "off" | "waiting" | "rec", "path", "seconds", "bytes", "error"}
    rx.stop_recording()
The H.264 packets exactly as they arrive from the Pi are written to a Matroska (.mkv)
file - no decoding or re-encoding, so it costs almost no CPU and keeps full quality
(~30 MB per minute at the Pi's 4 Mbit/s). Writing starts at the next key frame
(<= 0.5 s with the Pi's IPERIOD), so the file never begins with a broken picture. If
the stream drops out and comes back, the same file continues (the gap is cut out, so
"seconds" is time of video in the file, not wall-clock time). The file is created
only once video arrives. Matroska stays playable even if the program crashes before
the file is closed: everything up to about the last second is kept (seeking in such a
file may be slower, as its index is only written on a normal stop).

If PyAV isn't installed the console still runs; the video area just says so.
"""

import threading
import time

from PySide6.QtGui import QImage

from command_center_py.video import avlib  # PyAV, loaded on first use (see video/avlib.py)

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
        self.on_frame = None          # called from the receive thread after each new frame
        self._view = None             # (w, h, dpr) of the video area, in device pixels; None = full size
        self._stop = threading.Event()
        self._thread = None
        # recording (written by the receive thread; requested from the GUI thread)
        self._rec_want = None         # path asked for, or None = not recording
        self._rec_out = None          # open output container
        self._rec_ost = None          # its video stream
        self._rec_path = None
        self._rec_open_path = None    # path of the file that is actually open (may lag _rec_want)
        self._rec_src = None          # input stream being copied (changes after a dropout)
        self._rec_shift = 0           # input ts -> file ts, in the input time base
        self._rec_last = None         # last dts written (file time base = input time base)
        self._rec_tb = None
        self._rec_frame = 3000        # one frame in time-base ticks (90 kHz / 30 fps), updated per stream
        self._rec_seconds = 0.0
        self._rec_bytes = 0
        self.rec_error = None
        if avlib.get() is None:
            self.status = "PyAV not installed - run: python -m pip install -r py_requirements.txt"
            return
        self._thread = threading.Thread(target=self._run, name="video-rx", daemon=True)
        self._thread.start()

    def latest(self):
        """(QImage or None, frame counter, status text). The counter only changes on a new frame."""
        with self._lock:
            return self._image, self._frame_id, self.status

    def set_view_size(self, width, height, dpr=1.0):
        """Size of the video area in device pixels (from the GUI thread). Frames are scaled
        to fit it here, in the receive thread, so drawing them is a straight copy."""
        with self._lock:
            self._view = (int(width), int(height), float(dpr)) if width > 1 and height > 1 else None

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=OPEN_TIMEOUT_S + 1.0)
        self._rec_close()             # in case the thread never started or is still blocked

    # ---------------- recording (called from the GUI thread) ----------------
    def start_recording(self, path):
        """Ask the receive thread to record to path (.mkv). False if already recording / no PyAV."""
        with self._lock:
            if avlib.get() is None or self._rec_want is not None:
                return False          # (a just-stopped file still closing is fine: it's closed first)
            self._rec_want, self._rec_path = str(path), str(path)
            self._rec_seconds, self._rec_bytes, self.rec_error = 0.0, 0, None
            return True

    def stop_recording(self):
        """Stop recording; the file is closed by the receive thread (or by stop())."""
        with self._lock:
            self._rec_want = None
        if self._thread is None or not self._thread.is_alive():
            self._rec_close()

    def recording(self):
        """Current recording state for the console's REC button and the operator marks."""
        with self._lock:
            if self._rec_want is None:
                state = "off"           # stopped (the file may still be closing in the background)
            elif self._rec_out is None or self._rec_open_path != self._rec_want:
                state = "waiting"       # asked to record, no key frame yet
            else:
                state = "rec"
            return {"state": state, "path": self._rec_path, "seconds": self._rec_seconds,
                    "bytes": self._rec_bytes, "error": self.rec_error}

    # ---------------- recording (receive thread) ----------------
    def _rec_packet(self, packet, stream):
        """Copy one demuxed (already decoded) packet into the recording, if one is wanted."""
        with self._lock:
            want = self._rec_want
        if self._rec_out is not None and self._rec_open_path != want:
            self._rec_close()           # stopped, or a new recording asked for before the old one closed
        if want is None:
            return
        pts = packet.pts if packet.pts is not None else packet.dts
        dts = packet.dts if packet.dts is not None else pts
        if pts is None or dts is None:
            return
        try:
            if self._rec_out is None or stream is not self._rec_src:
                # start of the file, or the stream came back after a dropout: wait for a key frame
                if not packet.is_keyframe:
                    return
                if self._rec_out is None:
                    # flush_packets: every packet goes to disk at once; cluster_time_limit: Matroska
                    # finishes a block at least every second. Together a crash loses <= ~1 s.
                    out = avlib.get().open(want, mode="w", format="matroska",
                                  options={"cluster_time_limit": "1000"},
                                  container_options={"flush_packets": "1"})
                    ost = out.add_stream_from_template(stream)
                    with self._lock:
                        self._rec_out, self._rec_ost, self._rec_open_path = out, ost, want
                    self._rec_tb = stream.time_base
                    self._rec_last = None
                    next_ts = 0
                else:                                      # continue right after the last frame
                    next_ts = self._rec_last + self._rec_frame
                rate = stream.average_rate or stream.guessed_rate
                if rate and self._rec_tb:
                    self._rec_frame = max(1, int(round(1 / (float(rate) * float(self._rec_tb)))))
                self._rec_src = stream
                self._rec_shift = next_ts - dts
            out_dts = dts + self._rec_shift
            out_pts = pts + self._rec_shift
            if self._rec_last is not None and out_dts <= self._rec_last:      # keep dts increasing
                bump = self._rec_last + 1 - out_dts
                out_dts += bump
                out_pts += bump
            packet.stream = self._rec_ost
            packet.dts, packet.pts = out_dts, max(out_pts, out_dts)
            size = packet.size
            self._rec_out.mux(packet)
            self._rec_last = out_dts
            with self._lock:
                self._rec_seconds = float(out_pts * self._rec_tb)
                self._rec_bytes += size
        except Exception as exc:                           # disk full, no permission, ...
            with self._lock:
                self.rec_error = f"Recording stopped — {exc}"
                self._rec_want = None
            self._rec_close()

    def _rec_close(self):
        with self._lock:
            out, self._rec_out, self._rec_ost = self._rec_out, None, None
            self._rec_src, self._rec_open_path = None, None
        if out is not None:
            try:
                out.close()
            except Exception:
                pass

    # ---------------- receive thread ----------------
    def _run(self):
        # overrun_nonfatal + a big fifo: if the decoder falls behind briefly, drop
        # old packets rather than erroring out. listen on all interfaces.
        url = (f"udp://0.0.0.0:{self.port}"
               f"?overrun_nonfatal=1&fifo_size=1000000&buffer_size=4194304")
        try:
            self._run_loop(url)
        finally:
            self._rec_close()                 # console closing: finish the recording file

    def _run_loop(self, url):
        while not self._stop.is_set():
            with self._lock:
                stopped_rec = self._rec_out is not None and self._rec_open_path != self._rec_want
            if stopped_rec:                   # REC turned off while no video was arriving
                self._rec_close()
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
        container = avlib.get().open(
            url, format="mpegts",
            # analyzeduration 0.1 s (was 0.5 s): the picture appears ~0.4 s sooner after CONNECT
            # or a dropout. Don't cut probesize as well: with too little probed the stream can
            # miss its SPS/PPS, and then a recording started from it can't be written.
            options={"fflags": "nobuffer", "probesize": "500000", "analyzeduration": "100000"},
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
                frames = packet.decode()
                self._rec_packet(packet, stream)      # after decode: muxing re-targets the packet
                for frame in frames:
                    with self._lock:
                        view = self._view
                    img = self._to_qimage(frame, view)
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
                    cb = self.on_frame
                    if cb is not None:
                        cb()                          # console: draw it now, not on the next UI tick
        finally:
            container.close()

    @staticmethod
    def _to_qimage(frame, view=None):
        """frame -> QImage, scaled to fit view (w, h, dpr in device pixels, aspect kept) and
        converted to Qt's native 32-bit RGB in one FFmpeg pass. The QImage uses FFmpeg's
        buffer directly (PySide keeps the plane, and so the frame, alive) - no copies."""
        fw, fh = frame.width, frame.height
        w, h, dpr = fw, fh, 1.0
        if view is not None:
            vw, vh, dpr = view
            k = min(vw / fw, vh / fh)
            w, h = max(2, round(fw * k)), max(2, round(fh * k))
        out = frame.reformat(width=w, height=h, format="bgra")     # bgra = QImage RGB32 in memory
        plane = out.planes[0]
        img = QImage(plane, w, h, plane.line_size, QImage.Format.Format_RGB32)
        img.setDevicePixelRatio(dpr)
        return img
