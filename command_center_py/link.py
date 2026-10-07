"""UDP link to the Raspberry Pi: command packets out, JSON telemetry in.

WIRE CONTRACT  (proposed - the Pi side must match this)

Command packet  laptop -> Pi, UDP, CMD_PORT, 50 Hz, 16 bytes, little-endian
    struct format "<2sBBH6bbxH"
    0  2s   magic      b"RV"
    2  B    version    1
    3  B    flags      bit0 = armed
    4  H    seq        increments every packet, wraps at 65535
    6  6b   throttle   T1..T6, int8, -100..+100 percent
    12 b    cam_tilt   int8 degrees, TILT_MIN..TILT_MAX (0 = level, + = up)
                       sent even when disarmed; Pi maps it to servo PWM
    13 x    pad
    14 H    crc16      CRC-16/CCITT-FALSE over bytes 0..13
                       (Python: binascii.crc_hqx(pkt[:14], 0xFFFF))
    The Pi should zero all thrusters if no valid packet arrives for ~250 ms.

Telemetry  Pi -> laptop, UDP, TELEM_PORT, JSON object per datagram, any keys optional:
    {"depth_m": 12.4, "pressure_mbar": 2240, "water_c": 8.7, "internal_c": 41.6,
     "roll": 1.2, "pitch": -0.4, "yaw": 214.0, "voltage": 15.8, "current": 8.3,
     "leak": false, "ack": <last cmd seq received>, "rx_cmds": <total cmds received>}
"""

import binascii
import json
import math
import socket
import struct
import time

from command_center_py.config import LINK_TIMEOUT_S, RATE_HZ, TILT_MAX, TILT_MIN


CMD_STRUCT = struct.Struct("<2sBBH6bbx")   # 14 bytes, + 2-byte CRC = 16


def pack_command(seq, armed, throttles, tilt):
    body = CMD_STRUCT.pack(b"RV", 1, 1 if armed else 0, seq & 0xFFFF,
                           *[max(-100, min(100, int(t))) for t in throttles],
                           max(TILT_MIN, min(TILT_MAX, int(tilt))))
    return body + struct.pack("<H", binascii.crc_hqx(body, 0xFFFF))


class Link:
    def __init__(self, host, cmd_port, telem_port):
        self.label = f"{host} : {cmd_port}"
        self.addr = (host, cmd_port)
        self.seq = 0
        self.tx_count = 0
        self.rx_count = 0
        self.last_rx = 0.0
        self.rtt_ms = None
        self.loss_pct = None
        self.error = None
        self._sent = {}
        self._loss_ref = None
        self.tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.tx.setblocking(False)
        self.rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx.setblocking(False)
        try:
            self.rx.bind(("0.0.0.0", telem_port))
        except OSError as exc:
            self.error = f"Cannot listen on UDP {telem_port}: {exc}"

    def up(self, now):
        return now - self.last_rx < LINK_TIMEOUT_S

    def send(self, armed, throttles, tilt):
        self.seq = (self.seq + 1) & 0xFFFF
        pkt = pack_command(self.seq, armed, throttles, tilt)
        self._sent[self.seq] = time.monotonic()
        self._sent.pop((self.seq - 200) & 0xFFFF, None)
        self._transmit(pkt)

    def _transmit(self, pkt):
        try:
            self.tx.sendto(pkt, self.addr)
            self.tx_count += 1
        except OSError as exc:
            self.error = f"Send failed: {exc}"

    def poll(self):
        latest = None
        while True:
            try:
                data, _ = self.rx.recvfrom(4096)
            except (BlockingIOError, ConnectionResetError):
                break
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(msg, dict):
                latest = msg
                self._account(msg)
        return latest

    def _account(self, msg):
        now = time.monotonic()
        self.rx_count += 1
        self.last_rx = now
        ack = msg.get("ack")
        if isinstance(ack, int) and ack in self._sent:
            self.rtt_ms = (now - self._sent[ack]) * 1000.0
        rx_cmds = msg.get("rx_cmds")
        if isinstance(rx_cmds, int):
            if self._loss_ref is None:
                self._loss_ref = (now, self.tx_count, rx_cmds)
            elif now - self._loss_ref[0] >= 1.0:
                sent = self.tx_count - self._loss_ref[1]
                got = rx_cmds - self._loss_ref[2]
                if sent > 0:
                    self.loss_pct = max(0.0, min(100.0, 100.0 * (1 - got / sent)))
                self._loss_ref = (now, self.tx_count, rx_cmds)


class DemoLink(Link):
    """No network. A crude vehicle model answers every command so the UI is testable."""

    def __init__(self):
        super().__init__("127.0.0.1", 0, 0)
        self.label = "DEMO · simulated vehicle"
        self.error = None
        self.depth = 12.4
        self.heading = 214.0
        self.t0 = time.monotonic()
        self.temp = 39.5
        self._last = None

    def _transmit(self, pkt):
        self.tx_count += 1
        self._last = pkt

    def poll(self):
        if self._last is None:
            return None
        _, _, flags, seq, *rest = CMD_STRUCT.unpack(self._last[:14])
        thr = rest[:6]
        dt = 1.0 / RATE_HZ
        t = time.monotonic() - self.t0
        heave = (thr[4] + thr[5]) / 200.0
        yaw = (thr[0] - thr[1] + thr[2] - thr[3]) / 400.0
        self.depth = max(0.0, self.depth - heave * 0.6 * dt)
        self.heading = (self.heading + yaw * 35.0 * dt) % 360
        load = sum(abs(x) for x in thr) / 600.0
        self.temp += ((38.0 + 10.0 * load) - self.temp) * 0.002
        wob = lambda s, a: (math.sin(t * 0.7 + s) + 0.4 * math.sin(t * 1.9 + s * 2.3)) * a
        msg = {
            "depth_m": self.depth + wob(0.9, 0.02),
            "pressure_mbar": 1013.25 + self.depth * 100.5,
            "water_c": 8.7 + wob(2.2, 0.15),
            "internal_c": self.temp,
            "roll": wob(1.1, 3.0) + (thr[0] - thr[1]) / 40.0,
            "pitch": wob(2.7, 2.0) - (thr[0] + thr[1] - thr[2] - thr[3]) / 80.0,
            "yaw": self.heading,
            "voltage": 15.8 - load * 0.9,
            "current": 1.2 + load * 18.0,
            "leak": False,
            "ack": seq,
            "rx_cmds": self.tx_count,
        }
        self._account(msg)
        return msg
