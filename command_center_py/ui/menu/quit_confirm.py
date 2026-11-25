"""QUIT card: asks "Are you sure?" before the program closes.

Shown by the main menu for QUIT, the window's ✕, Alt+F4 and the taskbar's "Close window".
CANCEL (or Esc, the ✕ or a click on the dimmed menu) goes back; QUIT closes the program.
Keyboard: Tab / Shift+Tab or Left / Right move the highlight between CANCEL and QUIT (CANCEL is
highlighted when the card opens, so a stray Enter doesn't quit), Enter presses the highlighted button. The keys arrive through
MainMenu.keyPressEvent / focusNextPrevChild, as for the other cards.
Ctrl+C in the terminal does not ask (app.py shutdown -> MainMenu.quit_now)."""

from PySide6.QtWidgets import QVBoxLayout

from command_center_py.ui.menu.cards import Card, RED_BORDER, button
from command_center_py.ui.theme import ACCENT, BRIGHT, CONSOLE_FONT_SCALE, DANGER, GRID, lab


class QuitCard(Card):
    """QUIT: the question, then CANCEL and QUIT."""

    def __init__(self, on_cancel, on_quit):
        z = lambda v: round(v * CONSOLE_FONT_SCALE)          # same text size as the other cards
        super().__init__("QUIT", 420, scale=CONSOLE_FONT_SCALE)
        self.close_btn.clicked.connect(on_cancel)
        v = QVBoxLayout(self.body)
        v.setContentsMargins(z(16), z(18), z(16), z(18))
        msg = lab("Are you sure you want to quit the program?", z(12), BRIGHT)
        msg.setWordWrap(True)
        v.addWidget(msg)

        # footer: ........ CANCEL  QUIT
        self.foot_lay.addStretch(1)
        cancel_css = f"padding: {z(6)}px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {BRIGHT};"
        cancel_hover = f"border-color: {ACCENT}; color: {ACCENT};"
        cancel = button("CANCEL", z(11), z(96), cancel_css, cancel_hover)
        cancel.clicked.connect(on_cancel)
        self.foot_lay.addWidget(cancel)
        quit_css = f"padding: {z(6)}px 0; border: 1px solid {RED_BORDER}; border-radius: 3px; background: #2a1416; color: {DANGER};"
        quit_hover = f"border-color: {DANGER};"
        quit_btn = button("QUIT", z(11), z(96), quit_css, quit_hover)
        quit_btn.clicked.connect(on_quit)
        self.foot_lay.addWidget(quit_btn)

        # keyboard highlight: index into _btns (0 = CANCEL, 1 = QUIT)
        self._btns = [(cancel, cancel_css, cancel_hover), (quit_btn, quit_css, quit_hover)]
        self.sel = 0
        self.select(0)

    def select(self, i):
        """Highlight button i (wraps), drawn like its mouse hover."""
        self.sel = i % len(self._btns)
        for j, (b, css, hover) in enumerate(self._btns):
            on = hover if j == self.sel else ""          # later rules in the block win
            b.setStyleSheet(f"QPushButton {{ {css} {on} }} QPushButton:hover {{ {hover} }}")

    def step(self, d):
        """Tab / Right: d = +1, Shift+Tab / Left: d = -1."""
        self.select(self.sel + d)

    def press(self):
        """Enter: press the highlighted button (CANCEL or QUIT)."""
        self._btns[self.sel][0].click()
