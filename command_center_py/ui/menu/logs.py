"""VIEW LOGS card (SESSION LOGS): every saved session log in logs/ - preview, export, delete."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QTabWidget, QVBoxLayout

from command_center_py.config import LOGS_DIR
from command_center_py.logs.event_log import EVENT_COLS, MARK_COLS, list_logs
from command_center_py.ui.console.exit_log_dialog import export_session, log_table
from command_center_py.ui.menu.cards import Card, RED_BORDER, ResizeGrip, SOFT, button
from command_center_py.ui.theme import (ACCENT, BORDER, BORDER2, BRIGHT, DANGER, GRID, HEAD, LABEL,
                                        MUTED, PANEL, WARN, WELL, lab, mono)


class LogsCard(Card):
    """SESSION LOGS: every console session saved in logs/, newest first.

    Left: the list of sessions (start time, vehicle, events, marks, length). Right: the
    selected session in the same OPERATOR MARKS / ALL EVENTS tables as the exit pop-up.
    Footer: OPEN FOLDER, DELETE (click twice), EXPORT... (.xlsx / .csv / .pdf), CLOSE.
    Esc / ✕ / CLOSE close it; arrow keys pick a session.
    Resizable: drag the grip in the bottom-right corner (kept while the program runs).
    """

    MIN_W, MIN_H = 720, 380

    def __init__(self, on_close):
        super().__init__("SESSION LOGS", 1040)
        self._on_close = on_close
        self.close_btn.clicked.connect(on_close)
        self.logs = []
        self._del_armed = False

        h = QHBoxLayout(self.body)
        h.setContentsMargins(14, 14, 14, 10)
        h.setSpacing(14)

        self.list = QListWidget()
        self.list.setFixedWidth(270)
        self.list.setFont(mono(12))
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setStyleSheet(
            f"QListWidget {{ background: {WELL}; border: 1px solid {BORDER}; outline: none; }}"
            f"QListWidget::item {{ color: {LABEL}; padding: 8px 10px; border-bottom: 1px solid {BORDER}; }}"
            f"QListWidget::item:hover {{ color: {BRIGHT}; }}"
            f"QListWidget::item:selected {{ background: rgba(18,58,48,0.75); color: {BRIGHT};"
            f" border-left: 2px solid {ACCENT}; }}"
            f"QScrollBar {{ background: {PANEL}; border: none; width: 10px; }}"
            f"QScrollBar::handle {{ background: {GRID}; border-radius: 4px; min-height: 24px; }}"
            f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}")
        self.list.currentRowChanged.connect(self._show)
        h.addWidget(self.list)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.info = lab("", 12, SOFT)
        self.info.setWordWrap(True)
        right.addWidget(self.info)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.tabBar().setFont(mono(11, QFont.Weight.DemiBold))
        self.tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: none; background: {PANEL}; }}"
            f"QTabBar::tab {{ background: {PANEL}; color: {LABEL}; padding: 6px 12px;"
            f" border: none; border-bottom: 2px solid transparent; }}"
            f"QTabBar::tab:selected {{ color: {BRIGHT}; border-bottom: 2px solid {ACCENT}; }}"
            f"QTabBar::tab:hover {{ color: {BRIGHT}; }}")
        right.addWidget(self.tabs, 1)
        self.empty = lab("No session logs yet. A log is saved in logs/ every time the console runs.", 12, LABEL)
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.empty, 1)
        h.addLayout(right, 1)
        self.layout().setStretchFactor(self.body, 1)      # extra height goes to the tables
        self.setFixedSize(1040, 600)
        self.grip = ResizeGrip(self, self.MIN_W, self.MIN_H)
        self.add_maximize(self.grip)           # maximise button next to the ✕ (or double-click the title)

        # footer: OPEN FOLDER  DELETE  status ........ EXPORT...  CLOSE
        folder = button("OPEN FOLDER", 11, None,
                        f"padding: 6px 12px; border: 1px solid {GRID}; border-radius: 3px; background: {HEAD}; color: {SOFT};",
                        f"border-color: {ACCENT}; color: {ACCENT};")
        folder.clicked.connect(self._open_folder)
        self.foot_lay.addWidget(folder)
        self.del_btn = button("DELETE", 11, 190,
                              f"padding: 6px 0; border: 1px solid {RED_BORDER}; border-radius: 3px; background: #2a1416; color: {DANGER};",
                              f"border-color: {DANGER};")
        self.del_btn.clicked.connect(self._delete)
        self.foot_lay.addWidget(self.del_btn)
        self.status = lab("", 11, LABEL)
        self.status.setWordWrap(True)
        self.foot_lay.addWidget(self.status, 1)
        self.export_btn = button("EXPORT…", 11, 100,
                                 f"padding: 6px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {SOFT};",
                                 f"color: {BRIGHT}; border-color: {LABEL};")
        self.export_btn.clicked.connect(self._export)
        self.foot_lay.addWidget(self.export_btn)
        close = button("CLOSE", 11, 84,
                       f"padding: 6px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {BRIGHT};",
                       f"border-color: {ACCENT}; color: {ACCENT};")
        close.clicked.connect(on_close)
        self.foot_lay.addWidget(close)
        for b in (self.del_btn, self.export_btn):
            b.setStyleSheet(b.styleSheet() + f" QPushButton:disabled {{ color: {MUTED}; border-color: {BORDER2}; background: transparent; }}")

    # ---------------- state ----------------
    def opened(self):
        """Called each time the card is shown: re-reads logs/ (new sessions, deleted files)."""
        self.setFixedSize(*self.grip.clamp(self.width(), self.height()))   # menu may have shrunk
        self.logs = list_logs()
        self.list.blockSignals(True)
        self.list.clear()
        for lg in self.logs:
            n_ev, n_mk = len(lg.rows), len(lg.marks())
            item = QListWidgetItem(f"{lg.started}\n{lg.vehicle}  ·  {n_ev} event{'' if n_ev == 1 else 's'}"
                                   f"  ·  {n_mk} mark{'' if n_mk == 1 else 's'}")
            if lg.error:
                item.setToolTip(lg.error)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._say(LABEL, "")
        self.list.setCurrentRow(0 if self.logs else -1)
        self._show(self.list.currentRow())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        g = self.grip
        g.move(self.width() - g.width() - 2, self.height() - g.height() - 2)
        g.raise_()

    def current(self):
        i = self.list.currentRow()
        return self.logs[i] if 0 <= i < len(self.logs) else None

    def _show(self, i):
        self._disarm_delete()
        lg = self.current()
        has = lg is not None
        self.tabs.setVisible(has)
        self.empty.setVisible(not has)
        self.del_btn.setEnabled(has)
        self.export_btn.setEnabled(has and not lg.error)
        while self.tabs.count():
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            w.deleteLater()
        if not has:
            self.info.setText("")
            return
        if lg.error:
            self.info.setText(lg.error)
            return
        rows, marks = lg.rows, lg.marks()
        utc = f"  ·  UTC {rows[0]['utc_time'][:19]} → {rows[-1]['utc_time'][11:19]}" if rows else ""
        self.info.setText(f"logs/{lg.path.name}\n{lg.vehicle}  ·  length {lg.duration()}{utc}")
        self.tabs.addTab(log_table(marks, MARK_COLS), f"OPERATOR MARKS ({len(marks)})")
        self.tabs.addTab(log_table(rows, EVENT_COLS), f"ALL EVENTS ({len(rows)})")
        self.tabs.setCurrentIndex(0 if marks else 1)

    def step(self, d):
        if self.logs:
            self.list.setCurrentRow(max(0, min(len(self.logs) - 1, self.list.currentRow() + d)))

    def _say(self, color, text):
        self.status.setStyleSheet(f"color: {color}; background: transparent;")
        self.status.setText(text)

    # ---------------- footer ----------------
    def _open_folder(self):
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self._say(DANGER, f"Can't open logs/ — {e}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOGS_DIR)))

    def _delete(self):
        lg = self.current()
        if lg is None:
            return
        if not self._del_armed:              # first click arms, second deletes
            self._del_armed = True
            self.del_btn.setText("CLICK AGAIN TO DELETE")
            self._say(WARN, f"Deletes {lg.path.name}. Can't be undone.")
            QTimer.singleShot(4000, self._disarm_delete)
            return
        err = lg.delete()
        if err:
            self._disarm_delete()
            self._say(DANGER, err)
            return
        row = self.list.currentRow()
        self.opened()
        self.list.setCurrentRow(min(row, len(self.logs) - 1))
        self._say(LABEL, f"Deleted {lg.path.name}")

    def _disarm_delete(self):
        if self._del_armed:
            self._del_armed = False
            self.del_btn.setText("DELETE")
            self._say(LABEL, "")

    def _export(self):
        lg = self.current()
        if lg is None or lg.error:
            return
        path, err = export_session(self.window(), lg)
        if err:
            self._say(DANGER, err)
        elif path:
            self._say(ACCENT, f"Exported {Path(path).name}")

    def key(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self._on_close()
        elif k == Qt.Key.Key_Down:
            self.step(1)
        elif k == Qt.Key.Key_Up:
            self.step(-1)
        else:
            return False
        return True
