"""Exit dialog: preview of this session's event log, then SAVE / EXPORT... / DISCARD.

Shown by the console after it has disarmed and stopped talking to the ROV (closeEvent),
so nothing is sent to the vehicle while it is open. The operator must pick an option:
Esc and closing the window do nothing.

    SAVE       keep the session file in logs/ and exit
    EXPORT...  also save a copy as Excel (.xlsx), CSV (.csv) or PDF (.pdf) where you choose;
               the dialog stays open so several formats can be exported, then SAVE or DISCARD
    DISCARD    delete the session file from logs/ and exit (click twice to confirm;
               copies already exported are not touched)
"""

import html
import os

from PySide6.QtCore import QMarginsF, QSizeF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QHeaderView, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from command_center_py.event_log import (EVENT_COLS, LABELS, MARK_COLS, SNAPSHOT_FIELDS, export_csv,
                                         export_xlsx)
from command_center_py.ui.theme import (ACCENT, BLUE, BORDER, BORDER2, BRIGHT, DANGER, DIM, GRID, HEAD,
                                        LABEL, MUTED, PANEL, TEXT, WARN, WELL, lab, mono)

SOFT = "#c9d3de"
OK_GREEN, OK_BORDER = "#123a30", "#2a6f5c"
RED_FILL, RED_BORDER = "#2a1416", "#7f2b2e"

# Tag colours in the preview, as in the console's event log
TAG_COLORS = {"SYS": BLUE, "LOG": MUTED, "MARK": BLUE, "WARN": WARN, "DENY": WARN, "ALARM": DANGER,
              "ESTOP": DANGER, "FAIL": DANGER, "DEMO": MUTED}

FILTERS = {"Excel workbook (*.xlsx)": ".xlsx", "CSV (*.csv)": ".csv", "PDF (*.pdf)": ".pdf"}


class ExitLogDialog(QDialog):
    KEEP, DISCARD = "keep", "discard"

    def __init__(self, parent, log_file, scale=1.0):
        super().__init__(parent)
        s = self._s = lambda v: round(v * scale)
        self.log_file = log_file
        self.choice = None
        self.exported = []                       # paths exported this time
        self._discard_armed = False
        rows, marks = log_file.rows, log_file.marks()

        self.setWindowTitle("Session Log")
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.resize(s(1100), s(600))
        self.setStyleSheet(f"QDialog {{ background: {PANEL}; border: 1px solid {BORDER2}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        # header: title, file, summary (no ✕ - an option must be picked)
        head = QFrame()
        head.setObjectName("logHead")
        head.setStyleSheet(f"QFrame#logHead {{ background: {HEAD}; border-bottom: 1px solid {BORDER}; }}")
        hv = QVBoxLayout(head)
        hv.setContentsMargins(s(16), s(12), s(16), s(12))
        hv.setSpacing(s(4))
        title = lab("SESSION LOG", s(14), BRIGHT, QFont.Weight.Bold)
        tf = title.font()
        tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, s(14) * 0.06)
        title.setFont(tf)
        hv.addWidget(title)
        if rows:
            span = f"{rows[0]['local_time'][:19]} → {rows[-1]['local_time'][11:19]} local " \
                   f"({rows[0]['utc_offset']})  ·  {rows[0]['utc_time'][:19]} → {rows[-1]['utc_time'][11:19]} UTC"
        else:
            span = "no events"
        where = (f"logs/{log_file.path.name}" if log_file.path is not None and not log_file.error
                 else (log_file.error or "not saved to disk"))
        hv.addWidget(lab(f"{log_file.vehicle}  ·  {len(rows)} events  ·  {len(marks)} operator marks", s(11), DIM))
        hv.addWidget(lab(span, s(11), LABEL))
        hv.addWidget(lab(where, s(11), MUTED if not log_file.error else WARN))
        root.addWidget(head)

        # tabs: operator marks (one column per value) and all events
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: none; background: {PANEL}; }}"
            f"QTabBar::tab {{ background: {PANEL}; color: {LABEL}; padding: {s(7)}px {s(14)}px;"
            f" border: none; border-bottom: 2px solid transparent; font-weight: 600; }}"
            f"QTabBar::tab:selected {{ color: {BRIGHT}; border-bottom: 2px solid {ACCENT}; }}"
            f"QTabBar::tab:hover {{ color: {BRIGHT}; }}")
        tabs.tabBar().setFont(mono(s(11), QFont.Weight.DemiBold))
        tabs.tabBar().setDrawBase(False)
        tabs.addTab(self._table(marks, MARK_COLS), f"OPERATOR MARKS ({len(marks)})")
        tabs.addTab(self._table(rows, EVENT_COLS), f"ALL EVENTS ({len(rows)})")
        tabs.setCurrentIndex(0 if marks else 1)
        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(s(12), s(8), s(12), s(8))
        bv.addWidget(tabs)
        root.addWidget(body, 1)

        # status line (export / discard results)
        self.status = lab("", s(11), DIM)
        self.status.setWordWrap(True)
        self.status.setContentsMargins(s(16), 0, s(16), s(6))
        root.addWidget(self.status)

        # footer: DISCARD ............ EXPORT...  SAVE
        foot = QFrame()
        foot.setObjectName("logFoot")
        foot.setStyleSheet(f"QFrame#logFoot {{ background: #0a0e13; border-top: 1px solid {BORDER}; }}")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(s(16), s(10), s(16), s(10))
        fh.setSpacing(s(8))
        self.discard_btn = self._btn("DISCARD", 190, f"border: 1px solid {RED_BORDER}; background: {RED_FILL}; color: {DANGER};",
                                     f"border-color: {DANGER};")
        self.discard_btn.clicked.connect(self._discard)
        self.discard_btn.setEnabled(log_file.path is not None and not log_file.error)
        fh.addWidget(self.discard_btn)
        fh.addStretch(1)
        export = self._btn("EXPORT…", 120, f"border: 1px solid {GRID}; background: #1a2029; color: {SOFT};",
                           f"color: {BRIGHT}; border-color: {LABEL};")
        export.clicked.connect(self._export)
        fh.addWidget(export)
        keep = self._btn("SAVE", 120, f"border: 1px solid {OK_BORDER}; background: {OK_GREEN}; color: {ACCENT};",
                         f"border-color: {ACCENT}; color: #5ee7c1;")
        keep.clicked.connect(self._keep)
        fh.addWidget(keep)
        root.addWidget(foot)
        # Mouse only, like the Reference Values dialog: no default button, nothing takes focus,
        # so a stray Enter / Space can't pick an option.
        for b in (self.discard_btn, export, keep):
            b.setAutoDefault(False)
            b.setDefault(False)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    # ---------------- building blocks ----------------
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

    def _table(self, rows, cols):
        return log_table(rows, cols, self._s)

    # ---------------- options ----------------
    def _keep(self):
        self.choice = self.KEEP
        self.accept()

    def _discard(self):
        if not self._discard_armed:           # first click arms, second deletes
            self._discard_armed = True
            self.discard_btn.setText("CLICK AGAIN TO DELETE")
            self.status.setStyleSheet(f"color: {WARN}; background: transparent;")
            self.status.setText(f"DISCARD deletes logs/{self.log_file.path.name}. This can't be undone."
                                + ("  Exported copies are kept." if self.exported else ""))
            QTimer.singleShot(4000, self._disarm_discard)
            return
        err = self.log_file.discard()
        if err:
            self.status.setStyleSheet(f"color: {DANGER}; background: transparent;")
            self.status.setText(err)
            return
        self.choice = self.DISCARD
        self.accept()

    def _disarm_discard(self):
        if self._discard_armed and self.choice is None:
            self._discard_armed = False
            self.discard_btn.setText("DISCARD")
            self.status.setText("")

    def _export(self):
        path, err = export_session(self, self.log_file)
        if err:
            self._say(DANGER, err)
        elif path:
            self.exported.append(path)
            self._say(ACCENT, f"Exported {os.path.basename(path)} to {os.path.dirname(path)}. "
                              "Export another format, or choose SAVE or DISCARD to exit.")

    def _say(self, color, text):
        self.status.setStyleSheet(f"color: {color}; background: transparent;")
        self.status.setText(text)

    # An option must be picked: Esc and window-close do nothing.
    def reject(self):
        pass

    def closeEvent(self, e):
        if self.choice is None:
            e.ignore()
        else:
            super().closeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        p = self.parentWidget()
        if p is not None:   # centre over the console window
            g = p.frameGeometry()
            self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)


def log_table(rows, cols, s=lambda v: v):
    """Read-only, dark-themed table of log rows. s scales px sizes. Shared by the exit
    dialog and the main menu's VIEW LOGS browser."""
    t = QTableWidget(len(rows), len(cols))
    t.setHorizontalHeaderLabels([LABELS[c] for c in cols])
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setWordWrap(False)
    t.setFont(mono(s(11)))
    t.horizontalHeader().setFont(mono(s(10), QFont.Weight.DemiBold))
    t.setStyleSheet(
        f"QTableWidget {{ background: {WELL}; color: {TEXT}; gridline-color: {BORDER}; border: 1px solid {BORDER};"
        f" selection-background-color: #16303a; selection-color: {BRIGHT}; }}"
        f"QHeaderView {{ background: {HEAD}; border: none; }}"
        f"QHeaderView::section {{ background: {HEAD}; color: {LABEL}; border: none;"
        f" border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER}; padding: {s(4)}px {s(6)}px; }}"
        f"QTableCornerButton::section {{ background: {HEAD}; border: none; }}"
        f"QScrollBar {{ background: {PANEL}; border: none; width: {s(10)}px; height: {s(10)}px; }}"
        f"QScrollBar::handle {{ background: {GRID}; border-radius: {s(4)}px; min-width: {s(24)}px; min-height: {s(24)}px; }}"
        f"QScrollBar::handle:hover {{ background: {LABEL}; }}"
        f"QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}"
        f"QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}")
    for r, row in enumerate(rows):
        for c, key in enumerate(cols):
            val = row.get(key, "")
            text = "--" if val in ("", None) and key not in EVENT_COLS else str(val)
            if key in ("local_time", "utc_time"):
                text = text[11:]                       # HH:MM:SS.mmm (date is in the header)
            it = QTableWidgetItem(text)
            if key == "tag":
                it.setForeground(QColor(TAG_COLORS.get(text, ACCENT)))
            elif key == "leak":
                it.setForeground(QColor(DANGER if text == "LEAK" else (MUTED if text == "NO DATA" else ACCENT)))
            elif key in ("local_time", "utc_time") or text == "--":
                it.setForeground(QColor(MUTED))
            if key in SNAPSHOT_FIELDS and key != "leak":       # numbers (and "--") right-aligned
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            t.setItem(r, c, it)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if "message" in cols:
        h.setSectionResizeMode(cols.index("message"), QHeaderView.ResizeMode.Stretch)
    t.verticalHeader().setDefaultSectionSize(s(22))
    t.scrollToBottom()
    return t


def export_session(parent, log):
    """Asks where to save, then exports `log` (an EventLogFile or SavedLog) as .xlsx / .csv / .pdf.
    Returns (path, None) on success, (None, error) on failure, (None, None) if cancelled."""
    stem = log.path.stem if log.path is not None else "event_log"
    start_dir = os.path.join(os.path.expanduser("~"), "Documents")
    if not os.path.isdir(start_dir):
        start_dir = os.path.expanduser("~")
    path, chosen = QFileDialog.getSaveFileName(parent, "Export Session Log", os.path.join(start_dir, stem + ".xlsx"),
                                               ";;".join(FILTERS))
    if not path:
        return None, None
    ext = os.path.splitext(path)[1].lower()
    if ext not in FILTERS.values():               # no / wrong extension: use the chosen filter's
        ext = FILTERS.get(chosen, ".xlsx")
        path += ext
    try:
        if ext == ".csv":
            export_csv(log.rows, path)
        elif ext == ".pdf":
            export_pdf(log, path)
        else:
            export_xlsx(log.rows, path, log.vehicle)
    except ImportError:
        return None, "Excel export needs openpyxl — run: python -m pip install -r py_requirements.txt"
    except Exception as e:                        # disk full, file open in Excel, ...
        return None, f"Export failed — {e}"
    return path, None


def export_pdf(log_file, path):
    """Printable report: session summary, operator-mark table, then every event. A4 landscape."""
    rows, marks = log_file.rows, log_file.marks()
    esc = lambda v: html.escape("" if v is None else str(v))
    cell = "border: 1px solid #b8c2cc; padding: 2px 4px;"

    def table(data, cols, empty):
        if not data:
            return f"<p style='color:#666'>{empty}</p>"
        out = ["<table width='100%' cellspacing='0' cellpadding='3' style='border-collapse: collapse;'><tr>"]
        out += [f"<th style='{cell} background: #1f2933; color: white;'>{esc(LABELS[c])}</th>" for c in cols]
        out.append("</tr>")
        for i, r in enumerate(data):
            bg = "#f2f5f8" if i % 2 else "#ffffff"
            out.append(f"<tr style='background: {bg};'>")
            for c in cols:
                v = r.get(c, "")
                align = "right" if isinstance(v, (int, float)) else "left"
                out.append(f"<td style='{cell} text-align: {align};'>{esc(v if v != '' else '--')}</td>")
            out.append("</tr>")
        out.append("</table>")
        return "".join(out)

    span = (f"{esc(rows[0]['local_time'])} to {esc(rows[-1]['local_time'])} local (UTC {esc(rows[0]['utc_offset'])})<br>"
            f"{esc(rows[0]['utc_time'])} to {esc(rows[-1]['utc_time'])} UTC") if rows else "no events"
    doc_html = (
        "<html><body style='font-family: \"IBM Plex Sans\", \"Segoe UI\", sans-serif; font-size: 9pt;'>"
        f"<h2 style='margin: 0;'>Camosun ROV — session log</h2>"
        f"<p>Vehicle: <b>{esc(log_file.vehicle)}</b> · {len(rows)} events · {len(marks)} operator marks<br>{span}</p>"
        f"<h3>Operator marks</h3>{table(marks, MARK_COLS, 'No operator marks this session.')}"
        f"<h3>All events</h3>{table(rows, ['local_time', 'utc_time', 'tag', 'message'], 'No events.')}"
        "</body></html>")

    writer = QPdfWriter(path)
    writer.setTitle(f"Camosun ROV session log {log_file.vehicle}")
    writer.setCreator("Camosun ROV Command Centre")
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Landscape,
                                     QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter))
    writer.setResolution(96)      # lay out at screen DPI so pt sizes come out as written (text stays vector)
    doc = QTextDocument()
    doc.setHtml(doc_html)
    rect = writer.pageLayout().paintRectPixels(writer.resolution())
    doc.setPageSize(QSizeF(rect.width(), rect.height()))
    doc.print_(writer)
