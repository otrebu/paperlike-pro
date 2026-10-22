#!/usr/bin/env python3
"""Stream bootloader sync bytes (0x7F) while the monitor is power-cycled, and log any reply.

Chinese 8051-family MCUs (e.g. STC) only enter their ROM ISP if they see 0x7F bytes right
after power-on; STM32/GD32 answer 0x7F with 0x79 when in bootloader. Sends nothing but 0x7F.

usage: serial_sync_stream.py [--dev /dev/ttyUSB0] [--plan 2400N,2400E,115200N] [--seconds 30]
"""
import argparse
import os
import select
import termios
import time


def configure(fd, baud, parity):
    attrs = termios.tcgetattr(fd)
    attrs[0] = attrs[1] = attrs[3] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL | (termios.PARENB if parity else 0)
    attrs[4] = attrs[5] = getattr(termios, f"B{baud}")
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", default="/dev/ttyUSB0")
    ap.add_argument("--plan", default="2400N,2400E,115200N")
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--log")
    a = ap.parse_args()
    log = open(a.log, "ab") if a.log else None
    fd = os.open(a.dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        for item in a.plan.split(","):
            baud, parity = int(item[:-1]), item[-1] == "E"
            configure(fd, baud, parity)
            gap = max(0.01, 12 / baud)  # roughly back-to-back bytes
            print(f"--- {baud} 8{'E' if parity else 'N'}1 streaming 0x7F for {a.seconds:.0f}s ({time.strftime('%T')})", flush=True)
            got = b""
            end = time.time() + a.seconds
            while time.time() < end:
                os.write(fd, b"\x7f")
                r, _, _ = select.select([fd], [], [], gap)
                if r:
                    chunk = os.read(fd, 4096)
                    if chunk:
                        if not got:
                            print(f"    first reply at {time.strftime('%T')}", flush=True)
                        got += chunk
                        if log:
                            log.write(chunk)
            print(f"    {len(got)} bytes" + (f": {got[:96].hex(' ')}" if got else ""), flush=True)
    finally:
        os.close(fd)
        if log:
            log.close()


if __name__ == "__main__":
    main()
