#!/usr/bin/env python3
"""Gentle active probe of the Paperlike Pro's USB-serial (PL2303) port.

Only sends harmless bytes:
  text   CR/LF, "?", "help", "AT" at common baud rates (8N1), looking for a console
  stm32  0x7F autobaud sync (8E1, the STM32/GD32 ROM bootloader handshake); on ACK (0x79)
         sends only read-only commands GET (0x00) and GET_ID (0x02)
  boot   (only with --boot) pulses DTR/RTS in the usual reset/BOOT0 patterns, then repeats the stm32 sync
Never sends write, erase, protect/unprotect or go commands.

usage: serial_probe.py [--dev /dev/ttyUSB0] [--steps text,stm32] [--boot] [--log FILE]
"""
import argparse
import fcntl
import os
import select
import struct
import termios
import time

TEXT_BAUDS = [115200, 9600, 57600, 38400, 19200, 230400, 460800, 921600]
STM32_BAUDS = [115200, 57600, 38400, 19200, 9600]
TEXT_PROBES = [b"\r\n", b"?\r\n", b"help\r\n", b"AT\r\n"]
ACK, NACK = 0x79, 0x1F
SAFE_STM32_CMDS = {0x00: "GET", 0x02: "GET_ID"}

TIOCM = {"DTR": termios.TIOCM_DTR, "RTS": termios.TIOCM_RTS, "CTS": termios.TIOCM_CTS,
         "DSR": termios.TIOCM_DSR, "CD": termios.TIOCM_CD, "RI": termios.TIOCM_RI}

log = None


def out(msg):
    print(msg, flush=True)
    if log:
        log.write((msg + "\n").encode())


def configure(fd, baud, parity=False):
    attrs = termios.tcgetattr(fd)
    speed = getattr(termios, f"B{baud}")
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL | (termios.PARENB if parity else 0)
    attrs[3] = 0
    attrs[4] = attrs[5] = speed
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def read_for(fd, seconds):
    data = b""
    end = time.time() + seconds
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            data += os.read(fd, 4096)
    return data


def show(data):
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in data[:200])
    return f"{len(data)} bytes  hex={data[:64].hex(' ')}  text={text!r}"


def modem_lines(fd):
    bits = struct.unpack("I", fcntl.ioctl(fd, termios.TIOCMGET, struct.pack("I", 0)))[0]
    return " ".join(f"{k}={'1' if bits & v else '0'}" for k, v in TIOCM.items())


def set_line(fd, name, on):
    req = termios.TIOCMBIS if on else termios.TIOCMBIC
    fcntl.ioctl(fd, req, struct.pack("I", TIOCM[name]))


def step_text(fd):
    out("== text console probe (8N1)")
    for baud in TEXT_BAUDS:
        configure(fd, baud)
        for p in TEXT_PROBES:
            os.write(fd, p)
            data = read_for(fd, 0.6)
            if data:
                out(f"  {baud} {p!r}: {show(data)}")
        out(f"  {baud}: done")


def stm32_session(fd, baud):
    configure(fd, baud, parity=True)
    os.write(fd, b"\x7f")
    data = read_for(fd, 0.5)
    if not data:
        return False
    out(f"  {baud} sync reply: {show(data)}")
    if data[:1] != bytes([ACK]):
        return True
    for cmd, name in SAFE_STM32_CMDS.items():
        os.write(fd, bytes([cmd, cmd ^ 0xFF]))
        out(f"  {name}: {show(read_for(fd, 0.5))}")
    return True


def step_stm32(fd):
    out("== STM32/GD32 ROM bootloader sync (8E1, 0x7F)")
    for baud in STM32_BAUDS:
        if stm32_session(fd, baud):
            return True
        out(f"  {baud}: no reply")
    return False


def step_boot(fd):
    out("== DTR/RTS reset + BOOT0 patterns, then sync")
    # (bootline, resetline) pairs, both polarities: assert BOOT0, pulse reset, release reset
    for boot, reset in (("RTS", "DTR"), ("DTR", "RTS")):
        for boot_level in (True, False):
            set_line(fd, boot, boot_level)
            for reset_level in (True, False):
                set_line(fd, reset, reset_level)
                time.sleep(0.1)
                set_line(fd, reset, not reset_level)
                time.sleep(0.3)
                out(f"  boot={boot}:{int(boot_level)} reset={reset} pulse:{int(reset_level)} -> {modem_lines(fd)}")
                if stm32_session(fd, 115200) or stm32_session(fd, 57600):
                    return True
    # leave both lines released
    set_line(fd, "DTR", False)
    set_line(fd, "RTS", False)
    return False


def main():
    global log
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", default="/dev/ttyUSB0")
    ap.add_argument("--steps", default="text,stm32")
    ap.add_argument("--boot", action="store_true")
    ap.add_argument("--log")
    a = ap.parse_args()
    log = open(a.log, "ab") if a.log else None
    fd = os.open(a.dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        out(f"start {time.strftime('%T')}  modem lines: {modem_lines(fd)}")
        steps = a.steps.split(",")
        if "text" in steps:
            step_text(fd)
        if "stm32" in steps:
            step_stm32(fd)
        if a.boot:
            step_boot(fd)
        out(f"end {time.strftime('%T')}  modem lines: {modem_lines(fd)}")
    finally:
        os.close(fd)
        if log:
            log.close()


if __name__ == "__main__":
    main()
