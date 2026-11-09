"""Exit dialog 1 of 2: keep this session's camera recordings?

Shown by the console when it closes (after it has disarmed and closed the link), only if
REC was used in the session. One tick box per recording, all ticked to start.

    YES, SAVE     keep the ticked recordings (unticked ones are deleted). The event log is
                  saved in logs/ automatically, so the Session Log window is skipped.
                  Disabled while nothing is ticked.
    NO, DELETE    delete all of this session's recordings (click twice to confirm), then the
                  Session Log window opens (SAVE / EXPORT... / DISCARD).

The operator must pick: there is no ✕, and Esc / closing the window do nothing.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from command_center_py.video.recordings import Recording, clock
from command_center_py.ui.theme import (ACCENT, BORDER, BORDER2, BRIGHT, DANGER, DIM, GRID, LABEL, MUTED,
                                        PANEL, WARN, WELL, lab, mono)

OK_GREEN, OK_BORDER = "#123a30", "#2a6f5c"
RED_FILL, RED_BORDER = "#2a1416", "#7f2b2e"


class ExitRecordingDialog(QDialog):
    SAVE, DELETE = "save", "delete"

    def __init__(self, parent, paths, scale=1.0):
        super().__init__(parent)
        s = self._s = lambda v: round(v * scale)
        self.recs = [Recording(p) for p in paths if p.exists()]
        self.choice = None
        self.kept, self.deleted, self.errors = [], [], []
        self._delete_armed = False

        self.setWindowTitle("Save Recording")
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.resize(s(760), s(380))
        self.setStyleSheet(f"QDialog {{ background: {PANEL}; border: 1px solid {BORDER2}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        # header (no ✕ - an option must be picked)
        head = QFrame()
        head.setObjectName("recHead")
        head.setStyleSheet(f"QFrame#recHead {{ background: #131a22; border-bottom: 1px solid {BORDER}; }}")
        hv = QVBoxLayout(head)
        hv.setContentsMargins(s(16), s(12), s(16), s(12))
        hv.setSpacing(s(3))
        title = lab("SAVE RECORDING?", s(14), BRIGHT, QFont.Weight.Bold)
        hv.addWidget(title)
        n = len(self.recs)
        hv.addWidget(lab(f"REC was used {n} time{'' if n == 1 else 's'} this session. "
                         "Untick a recording to delete it.", s(11), DIM))
        root.addWidget(head)

        # one tick box per recording
        box = QWidget()
        box.setStyleSheet(f"background: {WELL};")
        bv = QVBoxLayout(box)
        bv.setContentsMargins(s(12), s(8), s(12), s(8))
        bv.setSpacing(0)
        self.checks = []
        for r in self.recs:
            length = clock(r.length) if r.length is not None else "--:--"
            cb = QCheckBox(f"recordings/{r.path.name}    {length}  ·  {r.size_text()}")
            cb.setChecked(True)
            cb.setFont(mono(s(11)))
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            cb.setStyleSheet(
                f"QCheckBox {{ color: {BRIGHT}; padding: {s(8)}px {s(4)}px; border-bottom: 1px solid {BORDER}; spacing: {s(10)}px; }}"
                f"QCheckBox:!checked {{ color: {MUTED}; }}"
                f"QCheckBox::indicator {{ width: {s(14)}px; height: {s(14)}px; border: 1px solid {GRID};"
                f" border-radius: 2px; background: {PANEL}; }}"
                f"QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}"
                f"QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}")
            cb.toggled.connect(self._update)
            bv.addWidget(cb)
            self.checks.append(cb)
        bv.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(box)
        scroll.setStyleSheet(f"QScrollArea {{ border: 1px solid {BORDER}; background: {WELL}; }}"
                             f"QScrollBar {{ background: {PANEL}; border: none; width: 10px; }}"
                             f"QScrollBar::handle {{ background: {GRID}; border-radius: 4px; min-height: 24px; }}"
                             f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}")
        wrap = QWidget()
        wv = QVBoxLayout(wrap)
        wv.setContentsMargins(s(15), s(12), s(15), s(8))
        wv.addWidget(scroll)
        root.addWidget(wrap, 1)

        # status line (right-aligned, like the Session Log window)
        self.status = lab("", s(11), DIM)
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status.setContentsMargins(s(16), 0, s(16), s(6))
        root.addWidget(self.status)

        # footer: YES, SAVE ............ NO, DELETE
        foot = QFrame()
        foot.setObjectName("recFoot")
        foot.setStyleSheet(f"QFrame#recFoot {{ background: #0a0e13; border-top: 1px solid {BORDER}; }}")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(s(16), s(10), s(16), s(10))
        fh.setSpacing(s(8))
        self.save_btn = self._btn("YES, SAVE", 150, f"border: 1px solid {OK_BORDER}; background: {OK_GREEN}; color: {ACCENT};",
                                  f"border-color: {ACCENT}; color: #5ee7c1;")
        self.save_btn.clicked.connect(self._save)
        fh.addWidget(self.save_btn)
        fh.addStretch(1)
        self.delete_btn = self._btn("NO, DELETE", 240, f"border: 1px solid {RED_BORDER}; background: {RED_FILL}; color: {DANGER};",
                                    f"border-color: {DANGER};")
        self.delete_btn.clicked.connect(self._delete)
        fh.addWidget(self.delete_btn)
        root.addWidget(foot)
        # Mouse only, like the Session Log window: a stray Enter / Space can't pick an option.
        for b in (self.save_btn, self.delete_btn):
            b.setAutoDefault(False)
            b.setDefault(False)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._update()

    def _btn(self, text, width, css, hover):
        s = self._s
        b = QPushButton(text)
        b.setFont(mono(s(11), QFont.Weight.DemiBold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedWidth(s(width))
        b.setStyleSheet(f"QPushButton {{ padding: {s(7)}px 0; border-radius: 3px; {css} }}"
                        f"QPushButton:hover {{ {hover} }}"
                        f"QPushButton:disabled {{ color: {MUTED}; border-color: {BORDER2}; background: transparent; }}")
        return b

    def _say(self, color, text):
        self.status.setStyleSheet(f"color: {color}; background: transparent;")
        self.status.setText(text)

    def _update(self):
        keep = sum(cb.isChecked() for cb in self.checks)
        drop = len(self.checks) - keep
        self.save_btn.setEnabled(keep > 0)
        if self._delete_armed:
            return
        if keep == 0:
            self._say(WARN, "Nothing ticked. Tick a recording to save it, or choose NO, DELETE.")
        elif drop:
            self._say(LABEL, f"YES, SAVE keeps {keep} and deletes {drop}. The event log is saved automatically.")
        else:
            self._say(LABEL, "YES, SAVE keeps the recording" + ("s" if keep > 1 else "")
                      + " and saves the event log automatically.")

    def _remove(self, recs):
        for r in recs:
            err = r.delete()
            (self.errors.append(err) if err else self.deleted.append(r.path.name))

    def _save(self):
        keep = [r for r, cb in zip(self.recs, self.checks) if cb.isChecked()]
        if not keep:
            return
        self._remove([r for r, cb in zip(self.recs, self.checks) if not cb.isChecked()])
        self.kept = [r.path.name for r in keep]
        self.choice = self.SAVE
        self.accept()

    def _delete(self):
        if not self._delete_armed:            # first click arms, second deletes
            self._delete_armed = True
            self.delete_btn.setText("CLICK AGAIN TO DELETE")
            n = len(self.recs)
            self._say(WARN, f"Deletes {'this recording' if n == 1 else f'all {n} recordings'} from this session."
                            " This can't be undone.")
            QTimer.singleShot(4000, self._disarm_delete)
            return
        self._remove(self.recs)
        self.choice = self.DELETE
        self.accept()

    def _disarm_delete(self):
        if self._delete_armed and self.choice is None:
            self._delete_armed = False
            self.delete_btn.setText("NO, DELETE")
            self._update()

    # An option must be picked: Esc and window-close do nothing.
    def reject(self):
        pass

    def closeEvent(self, e):
        if self.choice is None:
            e.ignore()
