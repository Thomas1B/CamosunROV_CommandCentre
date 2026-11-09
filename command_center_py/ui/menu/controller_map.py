"""CONTROLLER MAP card: DualShock 3 and Xbox button maps side by side."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QGridLayout, QVBoxLayout

from command_center_py.config import ARM_HOLD_S
from command_center_py.ui.menu.cards import Card, RED_BORDER, SOFT, button, slab
from command_center_py.ui.theme import ACCENT, BORDER, BRIGHT, DANGER, GRID, LABEL, PANEL, lab
from command_center_py.ui.widgets import CONTROLLER_MAPS, controller_map_body, key_chip


class ControllerMapCard(Card):
    """CONTROLLER MAPS: DualShock 3 and Xbox side by side. Esc / Enter / ✕ / OK / ○ / ✕ close it."""

    def __init__(self, on_close):
        super().__init__("CONTROLLER MAPS", 860)
        self.close_btn.clicked.connect(on_close)
        grid = QGridLayout(self.body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(1)
        self.body.setObjectName("mapGrid")
        self.body.setStyleSheet(f"QWidget#mapGrid {{ background: {BORDER}; }}")
        for col, kind in enumerate(("ds3", "xbox")):
            cell = QFrame()
            cell.setObjectName("mapCell")
            cell.setStyleSheet(f"QFrame#mapCell {{ background: {PANEL}; }}")
            v = QVBoxLayout(cell)
            v.setContentsMargins(16, 14, 16, 18)
            v.setSpacing(0)
            v.addWidget(slab(CONTROLLER_MAPS[kind]["short"], 12, ACCENT, QFont.Weight.Bold, 1.0))
            v.addWidget(controller_map_body(kind, ARM_HOLD_S))
            v.addStretch(1)
            grid.addWidget(cell, 0, col)

        self.foot_lay.addWidget(lab("Keyboard", 10, LABEL))
        self.foot_lay.addWidget(key_chip("SPACE", DANGER, RED_BORDER, 10))
        self.foot_lay.addWidget(lab("— E-STOP ·", 10, LABEL))
        self.foot_lay.addWidget(lab("ESC", 10, SOFT))
        self.foot_lay.addWidget(lab("to close", 10, LABEL))
        self.foot_lay.addStretch(1)
        ok = button("OK", 11, 72,
                    f"padding: 6px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {BRIGHT};",
                    f"border-color: {ACCENT}; color: {ACCENT};")
        ok.clicked.connect(on_close)
        self.foot_lay.addWidget(ok)
        # Widen to fit the longest line in the installed font (no wrapping, nothing cut off).
        self.setFixedWidth(max(self.width(), self.sizeHint().width() + 8))
