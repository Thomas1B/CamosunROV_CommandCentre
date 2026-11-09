"""Building blocks shared by the main menu's cards.

    Card ........ dialog card: title bar (+ optional maximise button) with ✕, body, footer strip
    Overlay ..... dims the menu and centres one card on it; clicking the dim area closes it
    ResizeGrip .. bottom-right corner handle for the resizable cards
    MaxButton ... title-bar maximise / restore button
    button(), close_x(), slab(), spaced() ... styled widgets; SOFT, FOOT, OK_*, RED_* colours;
    LIST_CSS, EDIT_CSS, SPIN_CSS ... shared style sheets
"""

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from command_center_py.ui.theme import (ACCENT, BORDER, BORDER2, BRIGHT, GRID, HEAD, LABEL, MUTED,
                                        PANEL, WELL, lab, mono)


SOFT = "#c9d3de"           # light grey used for secondary text in the design


FOOT = "#0a0e13"           # card footer background


OK_GREEN, OK_BORDER, OK_TEXT = "#123a30", "#2a6f5c", "#5ee7c1"


RED_BORDER, RED_DOT = "#7f2b2e", "#ff5c5c"


def spaced(font, px):
    """Return font with extra letter spacing (CSS letter-spacing in px)."""
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px)
    return font


def slab(text, px, color, weight=QFont.Weight.Normal, spacing=0.0):
    w = lab(text, px, color, weight)
    if spacing:
        w.setFont(spaced(w.font(), spacing))
    return w


def button(text, px, width=None, css="", hover=""):
    b = QPushButton(text)
    b.setFont(mono(px, QFont.Weight.DemiBold))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if width:
        b.setFixedWidth(width)
    b.setStyleSheet(f"QPushButton {{ {css} }} QPushButton:hover {{ {hover} }}")
    return b


def close_x(size):
    x = QPushButton("✕")
    x.setFixedSize(size, size)
    x.setFont(mono(round(size * 0.54)))
    x.setCursor(Qt.CursorShape.PointingHandCursor)
    x.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    x.setStyleSheet(f"QPushButton {{ border: none; border-radius: 2px; color: {LABEL}; background: transparent; }}"
                    f"QPushButton:hover {{ background: {BORDER}; color: {BRIGHT}; }}")
    return x


class MaxButton(QPushButton):
    """Title-bar maximise / restore button, drawn like the Windows one: one square
    (maximise) or two overlapping squares (restore). Same size and hover as the ✕."""

    def __init__(self, size):
        super().__init__()
        self.maximized = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(f"QPushButton {{ border: none; border-radius: 2px; background: transparent; }}"
                           f"QPushButton:hover {{ background: {BORDER}; }}")
        self.set_maximized(False)

    def set_maximized(self, on):
        self.maximized = on
        self.setToolTip("Restore size (or double-click the title bar)" if on
                        else "Maximise (or double-click the title bar)")
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setPen(QPen(QColor(BRIGHT if self.underMouse() else LABEL), 1))
        c, a = self.width() / 2, max(4.0, round(self.width() * 0.2))   # centre, half the square's side
        if self.maximized:
            o = round(a * 0.5)                                          # back square: up and right
            p.drawRect(QRectF(c - a + 0.5, c - a + o + 0.5, 2 * a - o, 2 * a - o))
            p.drawPolyline([QPointF(c - a + o + 0.5, c - a + o + 0.5), QPointF(c - a + o + 0.5, c - a + 0.5),
                            QPointF(c + a + 0.5, c - a + 0.5), QPointF(c + a + 0.5, c + a - o + 0.5),
                            QPointF(c + a - o + 0.5, c + a - o + 0.5)])
        else:
            p.drawRect(QRectF(c - a + 0.5, c - a + 0.5, 2 * a, 2 * a))


# ============================================================================
# OVERLAY + CARDS
# ============================================================================
class Overlay(QWidget):
    """Dims the whole menu and centres one card on it. Clicking the dim area closes it."""

    def __init__(self, parent, card, on_backdrop):
        super().__init__(parent)
        self.card = card
        self._on_backdrop = on_backdrop
        lay = QGridLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.addWidget(card, 0, 0, Qt.AlignmentFlag.AlignCenter)
        self.hide()

    def paintEvent(self, e):
        QPainter(self).fillRect(self.rect(), QColor(0, 0, 0, 128))

    def mousePressEvent(self, e):
        if not self.card.geometry().contains(e.position().toPoint()):
            self._on_backdrop()


class Card(QFrame):
    """Dialog card: title bar with ✕, a body and a footer strip."""

    def __init__(self, title, width, scale=1.0):
        super().__init__()
        s = lambda v: round(v * scale)
        self.setObjectName("card")
        self.setFixedWidth(s(width))
        self.setStyleSheet(f"QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER2}; border-radius: 4px; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        head = QFrame()
        head.setObjectName("cardHead")
        head.setStyleSheet(f"QFrame#cardHead {{ background: {HEAD}; border-bottom: 1px solid {BORDER};"
                           f" border-top-left-radius: 3px; border-top-right-radius: 3px; }}")
        hh = QHBoxLayout(head)
        hh.setContentsMargins(s(16), s(12), s(12), s(12))
        hh.addWidget(slab(title, s(14), BRIGHT, QFont.Weight.Bold, s(14) * 0.06), 1)
        self._head, self._hh, self._s = head, hh, s
        self.max_btn = None
        self.close_btn = close_x(s(24))
        hh.addWidget(self.close_btn)
        root.addWidget(head)

        self.body = QWidget()
        root.addWidget(self.body)

        self.foot = QFrame()
        self.foot.setObjectName("cardFoot")
        self.foot.setStyleSheet(f"QFrame#cardFoot {{ background: {FOOT}; border-top: 1px solid {BORDER};"
                                f" border-bottom-left-radius: 3px; border-bottom-right-radius: 3px; }}")
        self.foot_lay = QHBoxLayout(self.foot)
        self.foot_lay.setContentsMargins(s(16), s(10), s(16), s(10))
        self.foot_lay.setSpacing(s(8))
        root.addWidget(self.foot)

    # ---------------- maximise (resizable cards: VIEW LOGS, VIEW RECORDINGS) ----------------
    def add_maximize(self, grip):
        """Adds the maximise / restore button left of the ✕ (double-clicking the title bar
        does the same). Maximised = the whole menu window minus the usual 24 px margin, and it
        follows the window if that is resized. Dragging the corner grip ends maximised."""
        self.grip = grip
        self._restore = None                     # size to go back to, while maximised
        self.max_btn = MaxButton(self._s(24))
        self.max_btn.clicked.connect(self.toggle_maximize)
        self._hh.insertWidget(self._hh.count() - 1, self.max_btn)
        self._hh.insertSpacing(self._hh.count() - 1, self._s(4))
        self._head.installEventFilter(self)
        grip.pressed_hook = self._grip_pressed

    def toggle_maximize(self):
        if self._restore is None:
            self._restore = (self.width(), self.height())
            self.setFixedSize(*self.grip.clamp(10 ** 6, 10 ** 6))
            self.max_btn.set_maximized(True)
        else:
            self.setFixedSize(*self.grip.clamp(*self._restore))
            self._restore = None
            self.max_btn.set_maximized(False)

    def refit(self):
        """Menu window resized: a maximised card follows it; others just stay inside it."""
        if self.max_btn is None:
            return
        if self._restore is not None:
            self.setFixedSize(*self.grip.clamp(10 ** 6, 10 ** 6))
        else:
            self.setFixedSize(*self.grip.clamp(self.width(), self.height()))

    def _grip_pressed(self):
        if self._restore is not None:            # resizing by hand: no longer "maximised"
            self._restore = None
            self.max_btn.set_maximized(False)

    def eventFilter(self, obj, e):
        if obj is getattr(self, "_head", None) and e.type() == QEvent.Type.MouseButtonDblClick:
            self.toggle_maximize()
            return True
        return super().eventFilter(obj, e)


class ResizeGrip(QWidget):
    """Corner handle that resizes its card by dragging. The card stays centred on the menu,
    so it grows by twice the mouse movement (both edges move) to keep the corner under the
    pointer. Size is limited to the card's minimum and the menu window minus a 24 px margin."""

    SIZE = 14

    def __init__(self, card, min_w, min_h):
        super().__init__(card)
        self.card, self.min_w, self.min_h = card, min_w, min_h
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("Drag to resize")
        self._start = None
        self.pressed_hook = None      # set by Card.add_maximize: dragging ends "maximised"

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(MUTED), 1.2))
        s = self.SIZE - 3
        p.drawLine(s, 3, 3, s)
        p.drawLine(s, 7, 7, s)

    def clamp(self, w, h):
        ov = self.card.parentWidget()
        max_w = max(self.min_w, ov.width() - 48) if ov is not None else w
        max_h = max(self.min_h, ov.height() - 48) if ov is not None else h
        return max(self.min_w, min(max_w, w)), max(self.min_h, min(max_h, h))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.pressed_hook is not None:
                self.pressed_hook()
            self._start = (e.globalPosition().toPoint(), self.card.width(), self.card.height())

    def mouseMoveEvent(self, e):
        if self._start is None:
            return
        pos, w, h = self._start
        d = e.globalPosition().toPoint() - pos
        self.card.setFixedSize(*self.clamp(w + 2 * d.x(), h + 2 * d.y()))

    def mouseReleaseEvent(self, e):
        self._start = None


LIST_CSS = (f"QListWidget {{ background: {WELL}; border: 1px solid {BORDER}; outline: none; }}"
            f"QListWidget::item {{ color: {LABEL}; padding: 8px 10px; border-bottom: 1px solid {BORDER}; }}"
            f"QListWidget::item:hover {{ color: {BRIGHT}; }}"
            f"QListWidget::item:selected {{ background: rgba(18,58,48,0.75); color: {BRIGHT}; border-left: 2px solid {ACCENT}; }}"
            f"QScrollBar {{ background: {PANEL}; border: none; width: 10px; }}"
            f"QScrollBar::handle {{ background: {GRID}; border-radius: 4px; min-height: 24px; }}"
            f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}")


EDIT_CSS = (f"QLineEdit {{ padding: 7px 9px; border: 1px solid {GRID}; border-radius: 3px; background: {WELL}; color: {BRIGHT};"
            f" selection-background-color: {OK_BORDER}; }} QLineEdit:focus {{ border-color: {ACCENT}; }}")


SPIN_CSS = (f"QDoubleSpinBox {{ padding: 4px 7px; border: 1px solid {GRID}; border-radius: 3px; background: {WELL}; color: {BRIGHT};"
            f" selection-background-color: {OK_BORDER}; }} QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}"
            # arrows hidden here, not with setButtonSymbols(NoButtons): that plus a stylesheet hides the text
            f" QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}")
