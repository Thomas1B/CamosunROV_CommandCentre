"""Reference-value inputs (surface pressure, water density, second-order cal).

RefFields is shared by the main menu's CONNECT VEHICLE dialog and the console's
File > Reference Values... dialog (ReferenceDialog), so both look and validate the same.
"""

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from command_center_py import reference
from command_center_py.reference import RefValues
from command_center_py.ui.theme import (ACCENT, BORDER, BORDER2, BRIGHT, DANGER, GRID, HEAD, LABEL,
                                        MUTED, PANEL, WELL, lab, mono)

SOFT = "#c9d3de"
OK_GREEN, OK_BORDER = "#123a30", "#2a6f5c"
RED_BORDER = "#7f2b2e"


def _label(text, px, color=LABEL):
    w = lab(text, px, color)
    f = w.font()
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px * 0.1)
    w.setFont(f)
    return w


class RefFields(QWidget):
    """SURFACE PRESSURE [value][unit]  |  WATER DENSITY · KG/M³
       SECOND-ORDER PRESSURE CAL ........................ [ON|OFF]"""

    edited = Signal()

    def __init__(self, scale=1.0, refs=None, label_color=LABEL):
        super().__init__()
        s = self._s = lambda v: round(v * scale)
        self._bad_surface = self._bad_density = False
        self._unit = "hPa"
        self._second = True

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(s(14))

        grid = QGridLayout()
        grid.setHorizontalSpacing(s(10))
        grid.setVerticalSpacing(s(6))
        grid.addWidget(_label("SURFACE PRESSURE", s(9), label_color), 0, 0)
        grid.addWidget(_label("WATER DENSITY · KG/M³", s(9), label_color), 0, 1)
        row = QHBoxLayout()
        row.setSpacing(s(6))
        self.surface_edit = self._line_edit(str(reference.SURFACE_RANGE_HPA[0]))
        self.surface_edit.setPlaceholderText("1013.25")
        row.addWidget(self.surface_edit, 1)
        self.unit_box = QComboBox()
        self.unit_box.addItems(reference.UNITS)
        self.unit_box.setFixedWidth(s(72))
        self.unit_box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.unit_box.setFont(mono(s(11)))
        self.unit_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unit_box.setStyleSheet(
            f"QComboBox {{ padding: 0 {s(6)}px; border: 1px solid {GRID}; border-radius: 3px; background: {HEAD}; color: {SOFT}; }}"
            f"QComboBox:focus {{ border-color: {ACCENT}; }}"
            f"QComboBox::drop-down {{ border: none; width: {s(14)}px; }}"
            f"QComboBox QAbstractItemView {{ background: {HEAD}; color: {SOFT}; border: 1px solid {BORDER2};"
            f" selection-background-color: {BORDER}; selection-color: {BRIGHT}; outline: none; }}")
        self.unit_box.activated.connect(self._unit_changed)
        row.addWidget(self.unit_box)
        grid.addLayout(row, 1, 0)
        self.density_edit = self._line_edit("1000")
        self.density_edit.setPlaceholderText("1000")
        grid.addWidget(self.density_edit, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)

        tog = QHBoxLayout()
        tog.setSpacing(s(10))
        txt = QVBoxLayout()
        txt.setSpacing(s(3))
        txt.addWidget(_label("SECOND-ORDER PRESSURE CAL", s(9), label_color))
        txt.addWidget(lab("Bar30 correction for water below 20 °C", s(10), MUTED))
        tog.addLayout(txt, 1)
        self.on_btn, self.off_btn = QPushButton("ON"), QPushButton("OFF")
        for b, val in ((self.on_btn, True), (self.off_btn, False)):
            b.setFont(mono(s(11), QFont.Weight.DemiBold))
            b.setFixedHeight(s(28))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, x=val: self._set_second(x))
        btns = QHBoxLayout()
        btns.setSpacing(0)
        btns.addWidget(self.on_btn)
        btns.addWidget(self.off_btn)
        tog.addLayout(btns)
        v.addLayout(tog)

        self.set_values(refs or RefValues())

    # ---------------- building blocks ----------------
    def _line_edit(self, text):
        e = QLineEdit(text)
        e.setFont(mono(self._s(13)))
        e.setMinimumWidth(0)
        e.setMaxLength(8)
        e.textEdited.connect(self._text_edited)
        return e

    def _restyle(self):
        s = self._s
        for e, bad in ((self.surface_edit, self._bad_surface), (self.density_edit, self._bad_density)):
            e.setStyleSheet(
                f"QLineEdit {{ padding: {s(9)}px {s(10)}px; border: 1px solid {RED_BORDER if bad else GRID};"
                f" border-radius: 3px; background: {WELL}; color: {BRIGHT}; selection-background-color: {OK_BORDER}; }}"
                f"QLineEdit:focus {{ border-color: {ACCENT}; }}"
                f"QLineEdit:disabled {{ color: {LABEL}; }}")
        for b, on, side in ((self.on_btn, self._second, "left"), (self.off_btn, not self._second, "right")):
            r = (f"border-top-left-radius: 3px; border-bottom-left-radius: 3px;" if side == "left"
                 else "border-top-right-radius: 3px; border-bottom-right-radius: 3px; border-left: none;")
            b.setStyleSheet(f"QPushButton {{ padding: 0 {s(12)}px; border: 1px solid {OK_BORDER if on else GRID}; {r}"
                            f" background: {OK_GREEN if on else HEAD}; color: {ACCENT if on else '#7c8b9c'}; }}"
                            + ("" if on else f"QPushButton:hover {{ color: {BRIGHT}; }}"))

    # ---------------- events ----------------
    def _text_edited(self, *_):
        for e in (self.surface_edit, self.density_edit):       # digits and one decimal point only
            t = re.sub(r"[^0-9.]", "", e.text())
            if "." in t:
                head, _, tail = t.partition(".")
                t = head + "." + tail.replace(".", "")
            if t != e.text():
                e.setText(t)
        self.mark_bad(False)
        self.edited.emit()

    def _unit_changed(self, index):
        new = reference.UNITS[index]
        try:
            hpa = reference.to_hpa(float(self.surface_edit.text()), self._unit)
            self.surface_edit.setText(reference.format_surface(hpa, new))   # convert the shown value
        except ValueError:
            pass
        self._unit = new
        self.mark_bad(False)
        self.edited.emit()

    def _set_second(self, value):
        self._second = value
        self._restyle()
        self.edited.emit()

    # ---------------- public ----------------
    def set_values(self, refs):
        self._unit = refs.unit
        self.unit_box.setCurrentIndex(reference.UNITS.index(refs.unit))
        self.surface_edit.setText(reference.format_surface(refs.surface_hpa, refs.unit))
        self.density_edit.setText(reference.format_density(refs.density))
        self._second = refs.second_order
        self.mark_bad(False)

    def values(self):
        """(RefValues, None) or (None, error message) - and outlines the bad field(s) in red."""
        refs, err = reference.parse(self.surface_edit.text(), self._unit, self.density_edit.text(), self._second)
        if err:
            try:
                hpa = reference.to_hpa(float(self.surface_edit.text()), self._unit)
                bad_s = not (reference.SURFACE_RANGE_HPA[0] <= hpa <= reference.SURFACE_RANGE_HPA[1])
            except ValueError:
                bad_s = True
            try:
                d = float(self.density_edit.text())
                bad_d = not (reference.DENSITY_RANGE[0] <= d <= reference.DENSITY_RANGE[1])
            except ValueError:
                bad_d = True
            self._bad_surface, self._bad_density = bad_s, bad_d
            self._restyle()
        return refs, err

    def mark_bad(self, bad):
        self._bad_surface = self._bad_density = bad
        self._restyle()

    def setEnabled(self, on):
        for w in (self.surface_edit, self.unit_box, self.density_edit, self.on_btn, self.off_btn):
            w.setEnabled(on)


class ReferenceDialog(QDialog):
    """File > Reference Values... in the console. Esc / ✕ / CANCEL close without changes."""

    def __init__(self, parent, refs, scale=1.0):
        super().__init__(parent)
        s = lambda v: round(v * scale)
        self.result_refs = None
        self.setWindowTitle("Reference Values")
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setFixedWidth(s(440))
        self.setStyleSheet(f"QDialog {{ background: {PANEL}; border: 1px solid {BORDER2}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        head = QFrame()
        head.setObjectName("refHead")
        head.setStyleSheet(f"QFrame#refHead {{ background: {HEAD}; border-bottom: 1px solid {BORDER}; }}")
        hh = QHBoxLayout(head)
        hh.setContentsMargins(s(14), s(8), s(8), s(8))
        hh.addWidget(lab("Reference Values", s(13), SOFT, QFont.Weight.Bold), 1)
        x = QPushButton("✕")
        x.setFixedSize(s(22), s(22))
        x.setFont(mono(s(12)))
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setStyleSheet(f"QPushButton {{ border: none; border-radius: 2px; color: {LABEL}; background: transparent; }}"
                        f"QPushButton:hover {{ background: {BORDER}; color: {BRIGHT}; }}")
        x.clicked.connect(self.reject)
        hh.addWidget(x)
        root.addWidget(head)

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(s(14), s(14), s(14), s(6))
        bv.setSpacing(s(12))
        note = lab("Used by the Bar30 depth / pressure calculation. Sent to the Pi, which passes them "
                   "to the STM32.", s(10), LABEL)
        note.setWordWrap(True)
        bv.addWidget(note)
        self.fields = RefFields(scale, refs)
        self.fields.edited.connect(lambda: self.err.setText(""))
        bv.addWidget(self.fields)
        self.err = lab("", s(10), DANGER)
        self.err.setWordWrap(True)
        self.err.setMinimumHeight(s(16))
        bv.addWidget(self.err)
        root.addWidget(body)

        foot = QFrame()
        foot.setObjectName("refFoot")
        foot.setStyleSheet(f"QFrame#refFoot {{ background: #0a0e13; border-top: 1px solid {BORDER}; }}")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(s(14), s(10), s(14), s(10))
        fh.setSpacing(s(8))

        def btn(text, width, css, hover):
            b = QPushButton(text)
            b.setFont(mono(s(11), QFont.Weight.DemiBold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if width:
                b.setFixedWidth(s(width))
            b.setStyleSheet(f"QPushButton {{ {css} }} QPushButton:hover {{ {hover} }}")
            return b

        defaults = btn("DEFAULTS", None, f"padding: {s(6)}px {s(10)}px; border: none; background: transparent; color: {LABEL};",
                       f"color: {BRIGHT};")
        defaults.clicked.connect(lambda: self.fields.set_values(RefValues()))
        fh.addWidget(defaults)
        fh.addStretch(1)
        cancel = btn("CANCEL", 84, f"padding: {s(6)}px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {SOFT};",
                     f"color: {BRIGHT};")
        cancel.clicked.connect(self.reject)
        fh.addWidget(cancel)
        apply = btn("APPLY", 92, f"padding: {s(6)}px 0; border: 1px solid {OK_BORDER}; border-radius: 3px; background: {OK_GREEN}; color: {ACCENT};",
                    f"border-color: {ACCENT}; color: #5ee7c1;")
        apply.setDefault(True)
        apply.clicked.connect(self._apply)
        fh.addWidget(apply)
        root.addWidget(foot)

    def _apply(self):
        refs, err = self.fields.values()
        if err:
            self.err.setText(err)
            return
        self.result_refs = refs
        self.accept()

    def showEvent(self, e):
        super().showEvent(e)
        p = self.parentWidget()
        if p is not None:   # centre over the console window
            g = p.frameGeometry()
            self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
