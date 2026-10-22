#!/usr/bin/env python3
"""Passive listener for the Paperlike Pro's USB-serial (PL2303) port.

Never writes to the port. Opens it raw at each baud rate in turn and prints whatever arrives,
as text and hex. Note: opening a serial port raises DTR/RTS, which may reset the monitor's MCU.

usage: serial_listen.py [--dev /dev/ttyUSB0] [--bauds 115200,9600,...] [--seconds 10] [--log FILE]
"""
import argparse
import os
import select
import termios
import time

BAUDS = [115200, 9600, 57600, 38400, 19200, 230400, 460800, 921600, 4800]


def configure(fd, baud):
    attrs = termios.tcgetattr(fd)
    speed = getattr(termios, f"B{baud}")
    attrs[0] = 0                                                     # iflag: raw
    attrs[1] = 0                                                     # oflag: raw
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL          # cflag: 8N1, no modem control, no hangup-on-close
    attrs[3] = 0                                                     # lflag: no echo/canonical
    attrs[4] = attrs[5] = speed
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIFLUSH)


def printable(data):
    return "".join(chr(b) if 32 <= b < 127 or b in (9, 10, 13) else "." for b in data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", default="/dev/ttyUSB0")
    ap.add_argument("--bauds", default=",".join(map(str, BAUDS)))
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--log")
    a = ap.parse_args()
    log = open(a.log, "ab") if a.log else None
    fd = os.open(a.dev, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        for baud in [int(b) for b in a.bauds.split(",")]:
            configure(fd, baud)
            print(f"--- {baud} baud, listening {a.seconds:.0f}s ({time.strftime('%T')})", flush=True)
            total = b""
            end = time.time() + a.seconds
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.2)
                if r:
                    chunk = os.read(fd, 4096)
                    if chunk:
                        total += chunk
                        if log:
                            log.write(chunk)
            if total:
                print(f"    {len(total)} bytes")
                print("    text:", printable(total[:600]))
                print("    hex: ", total[:96].hex(" "))
            else:
                print("    nothing")
    finally:
        os.close(fd)
        if log:
            log.close()


if __name__ == "__main__":
    main()
