"""Switches between the main menu and the control console.

One Gamepad is shared by both screens, so SDL is only started once.
    main menu --CONNECT (Pi answered)--> console --close (disarmed)--> main menu
    main menu --DEMO MODE------------->  console --close (disarmed)--> main menu
    main menu --QUIT / window closed--> program exits
"""

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from command_center_py.gamepad import Gamepad
from command_center_py.link import DemoLink
from command_center_py.ui.menu import MainMenu
from command_center_py.ui.window import ConsoleWindow


ICON_SVG = Path(__file__).resolve().parent / "ui" / "assets" / "camosunrov-icon.svg"


def app_icon():
    """CamosunROV logo as a window icon, pre-rendered at the sizes Windows asks for."""
    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:
        return QIcon()
    r = QSvgRenderer(str(ICON_SVG))
    if not r.isValid():
        return QIcon()
    icon = QIcon()
    ds = r.defaultSize()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k = min(size / ds.width(), size / ds.height())          # keep the logo's proportions
        w, h = ds.width() * k, ds.height() * k
        r.render(p, QRectF((size - w) / 2, (size - h) / 2, w, h))
        p.end()
        icon.addPixmap(pm)
    return icon


class RovApp:
    def __init__(self):
        # One app-wide icon: used by the title bar of every window and dialog
        # (main menu, console, controller map) and by the taskbar.
        QApplication.instance().setWindowIcon(app_icon())
        self.pad = Gamepad()
        if self.pad.error:
            print(f"Controller: {self.pad.error}", flush=True)
        self.console = None
        self.menu = MainMenu(self.pad, on_connected=self.open_console, on_demo=self.open_demo)

    def start(self):
        self.menu.show()

    # ---------------- screen switching ----------------
    def open_demo(self):
        self.open_console(DemoLink(), "DEMO", demo=True)

    def open_console(self, link, vehicle, demo=False):
        if self.console is not None:
            link.close()
            return
        print(f"Opening console - {'demo mode' if demo else f'{vehicle} @ {link.label}'}", flush=True)
        self.menu.pause()
        self.console = ConsoleWindow(link, self.pad, demo, vehicle)
        self.console.closed.connect(self._console_closed)
        self._swap(self.menu, self.console)

    def _console_closed(self):
        console, self.console = self.console, None
        print("Console closed - back to main menu", flush=True)
        self._swap(console, self.menu)
        self.menu.resume()
        console.deleteLater()

    @staticmethod
    def _swap(old, new):
        """Show new where old was (same size/position, or maximised), then hide old.

        new is shown first so there is always a visible window - otherwise Qt
        would treat the hide as "last window closed" and quit.
        """
        state = old.windowState() & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen)
        if state:
            new.setWindowState(state)
            new.show()
        else:
            new.setWindowState(Qt.WindowState.WindowNoState)
            g = old.geometry()
            new.resize(max(g.width(), new.minimumWidth()), max(g.height(), new.minimumHeight()))
            new.move(old.pos())
            new.show()
        new.raise_()
        new.activateWindow()
        old.hide()

    # ---------------- shutdown ----------------
    def shutdown(self):
        """Ctrl+C: disarm and close the console if open, then close the menu."""
        if self.console is not None:
            console, self.console = self.console, None
            console.closed.disconnect(self._console_closed)
            console.force_close()
        self.menu.close()

    def cleanup(self):
        """After the event loop ends: stop the controller thread."""
        if self.console is not None:
            self.console.force_close()
        self.pad.close()
