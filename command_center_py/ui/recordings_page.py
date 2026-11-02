"""Widgets for the main menu's VIEW RECORDINGS page (RecordingsCard in start_window.py)."""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QSizePolicy, QSlider, QWidget

from command_center_py.ui.theme import ACCENT, BORDER, BORDER2, GRID, LABEL, MUTED, WELL, mono


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
