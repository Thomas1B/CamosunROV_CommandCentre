"""VIEW RECORDINGS card: camera recordings in recordings/ - built-in player, events, export.

Also the video view and seek bar it uses (VideoView, SeekBar)."""

import threading
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem, QSizePolicy,
                               QSlider, QVBoxLayout, QWidget)

from command_center_py.config import RECORDINGS_DIR
from command_center_py.ui.menu.cards import (Card, LIST_CSS, OK_BORDER, OK_GREEN, OK_TEXT,
                                             RED_BORDER, ResizeGrip, SOFT, button, slab)
from command_center_py.ui.theme import (ACCENT, BORDER, BORDER2, BRIGHT, DANGER, GRID, HEAD, LABEL,
                                        MUTED, WARN, WELL, lab, mono)
from command_center_py.video.player import VideoPlayer
from command_center_py.video.recordings import (clock, events_for, export_events, export_mp4,
                                                list_recordings)


class RecordingsCard(Card):
    """RECORDINGS: camera recordings in recordings/ (console REC button), newest first.

    Left: the recordings (start time, vehicle, length, size, marks). Middle: the built-in
    player (PyAV, see video/player.py) with play / pause, -3 / -1 / +1 / +3 s and a seek bar.
    Right: every event logged while that file was recording (from logs/); click one to jump.
    Footer: OPEN FOLDER, SAVE FRAME... (PNG of the frame on screen), EXPORT... (the video as .mp4,
    or its events as .xlsx / .csv), DELETE (click twice), CLOSE.
    Keys: Space play / pause, Left / Right -3 / +3 s (with Shift -1 / +1 s), Up / Down another
    recording, Esc close. Resizable from the bottom-right corner.
    """

    MIN_W, MIN_H = 960, 520
    STEP_S = 3.0          # ◀◀ / ▶▶, ← / →
    FINE_S = 1.0          # ◀ / ▶, Shift+← / →

    def __init__(self, on_close):
        super().__init__("RECORDINGS", 1180)
        self._on_close = on_close
        self.close_btn.clicked.connect(self.close_card)
        self.recs = []
        self.marks = []
        self.player = VideoPlayer()
        self._del_armed = False
        self._last_err = None

        h = QHBoxLayout(self.body)
        h.setContentsMargins(14, 14, 14, 10)
        h.setSpacing(14)

        self.list = QListWidget()
        self.list.setFixedWidth(260)
        self.list.setFont(mono(12))
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setStyleSheet(LIST_CSS)
        self.list.currentRowChanged.connect(self._show)
        h.addWidget(self.list)

        mid = QVBoxLayout()
        mid.setSpacing(8)
        self.info = lab("", 12, SOFT)
        self.info.setWordWrap(True)
        mid.addWidget(self.info)
        self.view = VideoView()
        mid.addWidget(self.view, 1)
        ctl = QHBoxLayout()
        ctl.setSpacing(6)
        small = (f"padding: 6px 10px; border: 1px solid {GRID}; border-radius: 3px; background: {HEAD}; color: {SOFT};",
                 f"border-color: {ACCENT}; color: {ACCENT};")
        self.back_btn = button("◀◀ 3 s", 11, None, *small)
        self.back_btn.clicked.connect(lambda: self.step(-self.STEP_S))
        self.back1_btn = button("◀ 1 s", 11, None, *small)
        self.back1_btn.clicked.connect(lambda: self.step(-self.FINE_S))
        self.play_btn = button("▶ PLAY", 11, 96,
                               f"padding: 6px 0; border: 1px solid {OK_BORDER}; border-radius: 3px; background: {OK_GREEN}; color: {ACCENT};",
                               f"border-color: {ACCENT}; color: {OK_TEXT};")
        self.play_btn.clicked.connect(self.player.toggle)
        self.fwd1_btn = button("1 s ▶", 11, None, *small)
        self.fwd1_btn.clicked.connect(lambda: self.step(self.FINE_S))
        self.fwd_btn = button("3 s ▶▶", 11, None, *small)
        self.fwd_btn.clicked.connect(lambda: self.step(self.STEP_S))
        self.seek = SeekBar()
        self.seek.jumped.connect(self.player.seek)
        self.time_lbl = lab("00:00 / 00:00", 12, SOFT)
        for w_ in (self.back_btn, self.back1_btn, self.play_btn, self.fwd1_btn, self.fwd_btn):
            ctl.addWidget(w_)
        ctl.addWidget(self.seek, 1)
        ctl.addWidget(self.time_lbl)
        mid.addLayout(ctl)
        h.addLayout(mid, 1)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(slab("EVENTS IN THIS RECORDING", 10, LABEL, QFont.Weight.Bold, 1.0))
        self.marks_list = QListWidget()
        self.marks_list.setFixedWidth(250)
        self.marks_list.setFont(mono(11))
        self.marks_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.marks_list.setWordWrap(True)
        self.marks_list.setStyleSheet(LIST_CSS)
        self.marks_list.itemClicked.connect(self._jump_to_mark)
        right.addWidget(self.marks_list, 1)
        self.marks_hint = lab("Click an event to jump to it.", 10, MUTED)
        self.marks_hint.setWordWrap(True)
        right.addWidget(self.marks_hint)
        h.addLayout(right)

        # footer: OPEN FOLDER  DELETE  status ........ SAVE FRAME…  EXPORT…  CLOSE
        folder = button("OPEN FOLDER", 11, None, *small)
        folder.clicked.connect(self._open_folder)
        self.foot_lay.addWidget(folder)
        self.frame_btn = button("SAVE FRAME…", 11, None, *small)
        self.frame_btn.clicked.connect(self._save_frame)
        self.export_btn = button("EXPORT…", 11, None, *small)
        self.export_btn.setToolTip("Save the video as .mp4 (plays anywhere), or its events as Excel / CSV")
        self.export_btn.clicked.connect(self._export)
        self._exp = None                      # running MP4 export: {"name", "frac", "done", "error", "path"}
        self.del_btn = button("DELETE", 11, 190,
                              f"padding: 6px 0; border: 1px solid {RED_BORDER}; border-radius: 3px; background: #2a1416; color: {DANGER};",
                              f"border-color: {DANGER};")
        self.del_btn.clicked.connect(self._delete)
        self.foot_lay.addWidget(self.del_btn)
        self.status = lab("", 11, LABEL)
        self.status.setWordWrap(True)
        self.foot_lay.addWidget(self.status, 1)
        self.foot_lay.addWidget(self.frame_btn)
        self.foot_lay.addWidget(self.export_btn)
        close = button("CLOSE", 11, 84,
                       f"padding: 6px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {BRIGHT};",
                       f"border-color: {ACCENT}; color: {ACCENT};")
        close.clicked.connect(self.close_card)
        self.foot_lay.addWidget(close)
        disabled = f" QPushButton:disabled {{ color: {MUTED}; border-color: {BORDER2}; background: transparent; }}"
        for b in (self.back_btn, self.back1_btn, self.play_btn, self.fwd1_btn, self.fwd_btn, self.frame_btn,
                  self.export_btn, self.del_btn):
            b.setStyleSheet(b.styleSheet() + disabled)

        self.layout().setStretchFactor(self.body, 1)
        self.setFixedSize(1180, 700)
        self.grip = ResizeGrip(self, self.MIN_W, self.MIN_H)
        self.add_maximize(self.grip)           # maximise button next to the ✕ (or double-click the title)
        self.timer = QTimer(self)
        self.timer.setInterval(33)                # ~30 fps display refresh while open
        self.timer.timeout.connect(self._tick)

    # ---------------- lifecycle ----------------
    def opened(self):
        """Called each time the card is shown: re-reads recordings/."""
        self.setFixedSize(*self.grip.clamp(self.width(), self.height()))
        self.recs = list_recordings()
        self.list.blockSignals(True)
        self.list.clear()
        for r in self.recs:
            ev = events_for(r)
            n, m = len(ev), sum(1 for e in ev if e[2] == "MARK")
            length = clock(r.length) if r.length is not None else "--:--"
            count = (f"{n} event{'' if n == 1 else 's'}" + (f"  ·  {m} mark{'' if m == 1 else 's'}" if m else "")
                     if n else "")
            self.list.addItem(QListWidgetItem(f"{r.started}\n{r.vehicle}  ·  {length}  ·  {r.size_text()}"
                                              + (f"\n{count}" if count else "")))
        self.list.blockSignals(False)
        self._say(LABEL, "")
        self.list.setCurrentRow(0 if self.recs else -1)
        self._show(self.list.currentRow())
        self.timer.start()

    def close_card(self):
        self.timer.stop()
        self.player.close()
        self._disarm_delete()
        self._on_close()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        g = self.grip
        g.move(self.width() - g.width() - 2, self.height() - g.height() - 2)
        g.raise_()

    def current(self):
        i = self.list.currentRow()
        return self.recs[i] if 0 <= i < len(self.recs) else None

    def _show(self, i):
        self._disarm_delete()
        r = self.current()
        self.player.close()
        self.marks_list.clear()
        has = r is not None
        for b in (self.back_btn, self.back1_btn, self.play_btn, self.fwd1_btn, self.fwd_btn, self.frame_btn,
                  self.export_btn, self.del_btn):
            b.setEnabled(has)
        if self._exp is not None and not self._exp["done"]:
            self.export_btn.setEnabled(False)  # one export at a time; and no DELETE while a file is being read
            self.del_btn.setEnabled(False)
        if not has:
            self.info.setText("")
            self.view.set_image(None, "No recordings yet. Use ● REC in the console to record the camera.")
            self.seek.setRange(0, 0)
            self.time_lbl.setText("00:00 / 00:00")
            self.marks_hint.setText("")
            return
        self.info.setText(f"recordings/{r.path.name}\n{r.vehicle}  ·  started {r.started}  ·  "
                          f"{clock(r.length) if r.length is not None else 'length unknown'}  ·  {r.size_text()}")
        self.marks = events_for(r)
        for t, local, tag, text in self.marks:
            it = QListWidgetItem(f"{clock(t)}   {local}   {tag}\n{text}")
            it.setData(Qt.ItemDataRole.UserRole, t)
            self.marks_list.addItem(it)
        self.marks_hint.setText("Click an event to jump to it." if self.marks
                                else "No events were logged while this was recording.")
        self.seek.setRange(0, int(round((r.length or 0) * 10)))
        self.seek.setValue(0)
        self.view.set_image(None, "Loading…")
        self.player.open(r.path, r.length)

    def step(self, d):
        _, pos, _, _ = self.player.state()
        self.player.seek(pos + d)

    def select(self, d):
        if self.recs:
            self.list.setCurrentRow(max(0, min(len(self.recs) - 1, self.list.currentRow() + d)))

    def _jump_to_mark(self, item):
        t = item.data(Qt.ItemDataRole.UserRole)
        if t is not None:
            self.player.seek(max(0.0, float(t)))

    def _tick(self):
        self._export_tick()
        img, pos, length, playing = self.player.state()
        if self.current() is None:
            return
        if self.player.error and self.player.error != self._last_err:
            self._last_err = self.player.error
            self._say(DANGER, self.player.error)
        self.view.set_image(img, "" if img is not None else ("Loading…" if not self.player.error else "Can't play this file"))
        if length and self.seek.maximum() != int(round(length * 10)):
            self.seek.setRange(0, int(round(length * 10)))
        if not self.seek.isSliderDown():
            self.seek.blockSignals(True)
            self.seek.setValue(int(round(pos * 10)))
            self.seek.blockSignals(False)
        self.time_lbl.setText(f"{clock(pos)} / {clock(length) if length else '--:--'}")
        text = "⏸ PAUSE" if playing else "▶ PLAY"
        if self.play_btn.text() != text:
            self.play_btn.setText(text)

    def _say(self, color, text):
        self.status.setStyleSheet(f"color: {color}; background: transparent;")
        self.status.setText(text)

    # ---------------- footer ----------------
    def _open_folder(self):
        try:
            RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self._say(DANGER, f"Can't open recordings/ — {e}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(RECORDINGS_DIR)))

    def _save_frame(self):
        r = self.current()
        img, pos, _, _ = self.player.state()
        if r is None or img is None:
            return
        self.player.pause()
        pics = Path.home() / "Pictures"
        start = pics if pics.is_dir() else Path.home()
        name = f"{r.path.stem}_{clock(pos).replace(':', '-')}.png"
        path, _ = QFileDialog.getSaveFileName(self.window(), "Save Frame", str(start / name), "PNG image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        if img.save(path, "PNG"):
            self._say(ACCENT, f"Saved {Path(path).name} ({clock(pos)})")
        else:
            self._say(DANGER, f"Could not save {Path(path).name}")

    def _export(self):
        """EXPORT...: one Save dialog; the file type picks what is exported."""
        r = self.current()
        if r is None or (self._exp is not None and not self._exp["done"]):
            return
        self.player.pause()
        home = Path.home()
        start = next((d for d in (home / "Videos", home / "Documents") if d.is_dir()), home)
        types = {"MP4 video (*.mp4)": ".mp4", "Events — Excel workbook (*.xlsx)": ".xlsx",
                 "Events — CSV (*.csv)": ".csv"}
        path, chosen = QFileDialog.getSaveFileName(self.window(), "Export Recording",
                                                   str(start / (r.path.stem + ".mp4")), ";;".join(types))
        if not path:
            return
        ext = Path(path).suffix.lower()
        if ext not in types.values():            # no / other extension: use the chosen type's
            ext = types.get(chosen, ".mp4")
            path += ext
        if ext == ".mp4":
            # copy in the background (big files take a few seconds); progress shows in the footer
            st = {"name": Path(path).name, "frac": 0.0, "done": False, "error": None}
            self._exp = st

            def run():
                try:
                    export_mp4(r, path, lambda f: st.__setitem__("frac", f))
                except Exception as e:           # disk full, file open in another program, ...
                    st["error"] = f"Export failed — {e}"
                st["done"] = True

            threading.Thread(target=run, name="export-mp4", daemon=True).start()
            self.export_btn.setEnabled(False)
            self.del_btn.setEnabled(False)
            self._say(LABEL, f"Exporting {st['name']}…")
            return
        try:
            n = export_events(r, path)
        except ImportError:
            self._say(DANGER, "Excel export needs openpyxl — run: python -m pip install -r py_requirements.txt")
            return
        except Exception as e:
            self._say(DANGER, f"Export failed — {e}")
            return
        self._say(ACCENT if n else WARN, f"Exported {Path(path).name} ({n} event{'' if n == 1 else 's'})"
                  if n else f"Exported {Path(path).name} — no events were logged during this recording")

    def _export_tick(self):
        st = self._exp
        if st is None:
            return
        if not st["done"]:
            self._say(LABEL, f"Exporting {st['name']}…  {st['frac'] * 100:.0f} %")
            return
        self._exp = None
        has = self.current() is not None
        self.export_btn.setEnabled(has)
        self.del_btn.setEnabled(has)
        if st["error"]:
            self._say(DANGER, st["error"])
        else:
            self._say(ACCENT, f"Exported {st['name']}")

    def _delete(self):
        r = self.current()
        if r is None:
            return
        if not self._del_armed:              # first click arms, second deletes
            self._del_armed = True
            self.del_btn.setText("CLICK AGAIN TO DELETE")
            self._say(WARN, f"Deletes {r.path.name}. Can't be undone.")
            QTimer.singleShot(4000, self._disarm_delete)
            return
        self.player.close()                  # Windows can't delete a file that is open
        err = r.delete()
        if err:
            self._disarm_delete()
            self._say(DANGER, err)
            self._show(self.list.currentRow())
            return
        row = self.list.currentRow()
        self.opened()
        if self.recs:
            self.list.setCurrentRow(min(row, len(self.recs) - 1))
        self._say(LABEL, f"Deleted {r.path.name}")

    def _disarm_delete(self):
        if self._del_armed:
            self._del_armed = False
            self.del_btn.setText("DELETE")
            self._say(LABEL, "")

    def key(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self.close_card()
        elif k == Qt.Key.Key_Space:
            self.player.toggle()
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Right):      # Shift: the 1 s step
            fine = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            d = self.FINE_S if fine else self.STEP_S
            self.step(-d if k == Qt.Key.Key_Left else d)
        elif k == Qt.Key.Key_Up:
            self.select(-1)
        elif k == Qt.Key.Key_Down:
            self.select(1)
        else:
            return False
        return True


class VideoView(QWidget):
    """Paints a QImage letterboxed (aspect kept) on black; a message when there is none."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image = None
        self.message = "No recording selected"

    def set_image(self, img, message=""):
        self.image, self.message = img, message
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000000"))
        if self.image is not None and not self.image.isNull():
            iw, ih = self.image.width(), self.image.height()
            k = min(self.width() / iw, self.height() / ih)
            w, h = iw * k, ih * k
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h), self.image)
        if self.message:
            p.setFont(mono(12))
            p.setPen(QColor(LABEL))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
        p.setPen(QColor(BORDER))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


class SeekBar(QSlider):
    """Horizontal slider in tenths of a second; a click jumps straight to that spot."""

    jumped = Signal(float)          # seconds

    def __init__(self):
        super().__init__(Qt.Orientation.Horizontal)
        self.setRange(0, 0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: 6px; background: {WELL}; border: 1px solid {BORDER2}; border-radius: 3px; }}"
            f"QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}"
            f"QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; border-radius: 7px; background: #eaf2fa;"
            f" border: 1px solid {GRID}; }}")
        self.sliderReleased.connect(lambda: self.jumped.emit(self.value() / 10))

    def mousePressEvent(self, e):
        span = self.maximum() - self.minimum()
        if e.button() == Qt.MouseButton.LeftButton and span > 0:
            x = e.position().x()
            handle_x = (self.value() - self.minimum()) / span * self.width()
            if abs(x - handle_x) > 10:          # a click on the bar (not the handle): jump there
                v = round(self.minimum() + span * max(0.0, min(1.0, x / max(1, self.width()))))
                self.setValue(v)
                self.jumped.emit(v / 10)
                return
        super().mousePressEvent(e)             # on the handle: normal dragging
