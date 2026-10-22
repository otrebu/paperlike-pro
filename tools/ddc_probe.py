#!/usr/bin/env python3
"""Read-only probe for a Dasung Paperlike Pro over DDC/CI (Linux /dev/i2c-N).

Never sends a Set VCP Feature. Modes:
  get    standard Get VCP 0x08 request, then read 11 bytes
  bare   read 11 bytes with nothing written (what the vendor app does after each command)
  heart  the Mac app's heartbeat read: 51 82 01 08 01 01 <chk>, then read 11 bytes

usage: ddc_probe.py --bus N [--mode get|bare|heart|all] [--count 3] [--delay 0.6]
"""
import argparse
import errno
import fcntl
import os
import time

I2C_SLAVE = 0x0703
I2C_SLAVE_FORCE = 0x0706
DDC_ADDR = 0x37  # 0x6E write / 0x6F read
HOST = 0x51
VCP = 0x08

REQUESTS = {
    "get": bytes([HOST, 0x82, 0x01, VCP]),
    "bare": None,
    "heart": bytes([HOST, 0x82, 0x01, VCP, 0x01, 0x01]),
}


def xor(data, seed):
    for b in data:
        seed ^= b
    return seed


def probe(fd, req, delay):
    if req is not None:
        os.write(fd, req + bytes([xor(req, 0x6E)]))
        time.sleep(delay)
    r = os.read(fd, 11)
    ok = (
        len(r) == 11
        and r[0] == 0x6E
        and r[2] == 0x02
        and r[4] == VCP
        and r[10] == xor(r[:10], 0x50)
    )
    return r, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--mode", choices=[*REQUESTS, "all"], default="all")
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--delay", type=float, default=0.6)
    a = ap.parse_args()
    fd = os.open(f"/dev/i2c-{a.bus}", os.O_RDWR)
    try:
        fcntl.ioctl(fd, I2C_SLAVE, DDC_ADDR)
    except OSError as e:
        if e.errno != errno.EBUSY:
            raise
        fcntl.ioctl(fd, I2C_SLAVE_FORCE, DDC_ADDR)
    modes = ["get", "bare", "heart"] if a.mode == "all" else [a.mode]
    for mode in modes:
        for i in range(a.count):
            try:
                r, ok = probe(fd, REQUESTS[mode], a.delay)
                line = f"{mode}#{i} raw={r.hex(' ')} valid={ok}"
                if ok:
                    line += f" rc={r[3]} type(ML)={r[7]:#04x} data(SL&0xF)={r[9] & 0xF} MH={r[6]:#04x} SH={r[8]:#04x}"
                print(line, flush=True)
            except OSError as e:
                print(f"{mode}#{i} error: {e}", flush=True)
            time.sleep(1)
    os.close(fd)


if __name__ == "__main__":
    main()
