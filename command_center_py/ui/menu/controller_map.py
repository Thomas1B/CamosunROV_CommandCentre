"""CONTROLLER MAP card: DualShock 3, Xbox and keyboard maps, one tab each."""

from PySide6.QtWidgets import QVBoxLayout

from command_center_py.config import ARM_HOLD_S
from command_center_py.ui.menu.cards import Card, SOFT, button
from command_center_py.ui.theme import ACCENT, BRIGHT, CONSOLE_FONT_SCALE, GRID, LABEL
from command_center_py.ui.widgets import map_tab_show, map_tab_step, map_tabs, map_tabs_hint


class ControllerMapCard(Card):
    """CONTROLLER MAPS: DUALSHOCK 3 / XBOX / KEYBOARD tabs (ui/widgets.py map_tabs, also used by the
    console's Help > Controller Maps). Opens on the button layout in use; Left / Right switch
    tabs. Esc / Enter / ✕ / OK close it."""

    def __init__(self, on_close):
        # Same text sizes as the console's Help > Controller Maps (console font scale, 1.25).
        z = lambda v: round(v * CONSOLE_FONT_SCALE)
        super().__init__("CONTROLLER MAPS", 560, scale=CONSOLE_FONT_SCALE)
        self.close_btn.clicked.connect(on_close)
        v = QVBoxLayout(self.body)
        v.setContentsMargins(0, 0, 0, 0)
        self.tabs = map_tabs(ARM_HOLD_S, CONSOLE_FONT_SCALE, margins=(14, 4, 14, 18))
        v.addWidget(self.tabs)

        map_tabs_hint(self.foot_lay, z(10), SOFT, LABEL)
        self.foot_lay.addStretch(1)
        ok = button("OK", z(11), z(72),
                    f"padding: 6px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {BRIGHT};",
                    f"border-color: {ACCENT}; color: {ACCENT};")
        ok.clicked.connect(on_close)
        self.foot_lay.addWidget(ok)
        # Widen to fit the longest line in the installed font (no wrapping, nothing cut off).
        self.setFixedWidth(max(self.width(), self.sizeHint().width() + 8))

    def opened(self):
        """Show the tab for the controller layout in use (DUALSHOCK 3 / XBOX toggle in the console)."""
        map_tab_show(self.tabs, None)

    def step(self, d):
        """Left / Right: previous / next tab (wraps)."""
        map_tab_step(self.tabs, d)
