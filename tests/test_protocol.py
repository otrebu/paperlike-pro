#!/usr/bin/env python3
"""Unit tests for ../paperlike: DDC/CI packets and replies, EDID and bus matching, Hyprland lookup, watch.

The byte strings are real exchanges with a Paperlike Pro (docs/protocol.md). Nothing here opens /dev/i2c-*:
the I2C calls are mocked, and a tripwire fails any test that tries to open one for real. sysfs, the state
cache and $XDG_RUNTIME_DIR are temp folders, and no desktop tool (hyprctl, swaymsg ...) is run.

  python3 -I -m unittest discover -s tests -v
"""
import contextlib
import errno
import importlib.machinery
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "paperlike")


def load_script():
    # the script has no .py extension, so importlib needs its loader spelled out
    loader = importlib.machinery.SourceFileLoader("paperlike", SCRIPT)
    spec = importlib.util.spec_from_loader("paperlike", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


pl = load_script()

# ---- tripwire: a real /dev/i2c-* open fails the test (another monitor may be on the bus) ----

_real_open = os.open


def _guarded_open(path, *args, **kw):
    if not isinstance(path, int) and os.fsdecode(path).startswith("/dev/i2c"):
        raise AssertionError(f"test tried to open {os.fsdecode(path)}")
    return _real_open(path, *args, **kw)


def setUpModule():
    os.open = _guarded_open


def tearDownModule():
    os.open = _real_open


# ---- fixtures ----

def h(s):
    return bytes.fromhex(s)


def reply(*body):
    """An 11-byte reply with a valid checksum (0x50 ^ bytes 0..9), computed here, not by the script."""
    chk = 0x50
    for b in body:
        chk ^= b
    return bytes(body) + bytes([chk])


# real exchanges (docs/protocol.md): (cmd, arg) -> packet sent, reply read back, parsed (type, value)
EXCHANGES = [
    ("heartbeat", (0x01, 0x01), "51 84 03 08 01 01 b0", "6e 88 02 00 08 00 00 01 00 02 bf", (1, 2)),
    ("quick clear", (0x06, 0x01), "51 84 03 08 06 01 b7", "6e 88 02 00 08 00 00 07 00 08 b3", (7, 8)),
    ("mode A2", (0x07, 0x02), "51 84 03 08 07 02 b5", "6e 88 02 00 08 00 00 07 00 02 b9", (7, 2)),
]

# the EDID read from a real Paperlike Pro (docs/protocol.md)
DASUNG_EDID = h("""
00 ff ff ff ff ff ff 00 12 63 01 00 00 00 00 00 2d 1a 01 03 80 3e 22 78 2a 08 a5 a2 57 4f a2 28
0f 50 54 00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 48 3f 40 30 62 b0 32 40 40 c0
13 00 6d 55 21 00 00 1e 88 13 20 00 31 58 1f 20 10 50 13 00 6d 55 21 00 00 1e 00 00 00 fc 00 44
41 53 55 4e 47 20 50 61 70 65 72 0a 00 00 00 fc 00 6c 69 6b 65 20 50 72 6f 0a 20 20 20 20 00 5f
""")


def make_edid(pnp, name):
    """A minimal 128-byte EDID 1.3: header, 3-letter PnP ID, one monitor-name descriptor, valid checksum."""
    e = bytearray(128)
    e[0:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
    e[8:10] = sum((ord(c) - 64) << shift for c, shift in zip(pnp, (10, 5, 0))).to_bytes(2, "big")
    e[18:20] = b"\x01\x03"
    e[54:72] = b"\x00\x00\x00\xfc\x00" + (name.encode() + b"\n").ljust(13, b" ")
    e[127] = -sum(e[:127]) % 256
    return bytes(e)


def pnp_id(edid):
    v = int.from_bytes(edid[8:10], "big")
    return "".join(chr(64 + (v >> shift & 0x1F)) for shift in (10, 5, 0))


FD = 1234  # fake file descriptor; os.close is mocked too, so no real descriptor is touched


@contextlib.contextmanager
def fake_i2c(*reads, write_error=None):
    """Mock the I2C syscalls the script makes. `reads` are returned by successive os.read calls."""
    with contextlib.ExitStack() as stack:
        patch = lambda obj, name, **kw: stack.enter_context(mock.patch.object(obj, name, **kw))
        yield types.SimpleNamespace(
            open=patch(pl.os, "open", return_value=FD),
            ioctl=patch(pl.fcntl, "ioctl"),
            write=patch(pl.os, "write", side_effect=write_error or (lambda fd, data: len(data))),
            read=patch(pl.os, "read", side_effect=list(reads)),
            close=patch(pl.os, "close"),
            sleep=patch(pl.time, "sleep"),
        )


# ---- packets ----

class PacketTest(unittest.TestCase):
    def test_set_packet_real_bytes(self):
        cases = [((0x01, 0x01), "51 84 03 08 01 01 b0"), ((0x06, 0x01), "51 84 03 08 06 01 b7"),
                 ((0x06, 0x02), "51 84 03 08 06 02 b4"), ((0x07, 0x02), "51 84 03 08 07 02 b5")]
        for (cmd, arg), packet in cases:
            with self.subTest(cmd=cmd, arg=arg):
                self.assertEqual(pl.set_packet(cmd, arg), h(packet))

    def test_set_packet_checksum_every_value(self):
        # DDC/CI: the destination address 0x6E XOR every byte of the packet, checksum included, is 0
        for cmd in range(256):
            for arg in range(256):
                p = pl.set_packet(cmd, arg)
                chk = 0x6E
                for b in p:
                    chk ^= b
                if len(p) != 7 or p[:6] != bytes([0x51, 0x84, 0x03, 0x08, cmd, arg]) or chk:
                    self.fail(f"set_packet({cmd:#04x}, {arg:#04x}) = {p.hex(' ')}")

    def test_get_packet(self):
        self.assertEqual(pl.get_packet(), h("51 82 01 08 b4"))


# ---- replies ----

class ReplyTest(unittest.TestCase):
    def test_real_replies(self):
        for name, _, _, rep, parsed in EXCHANGES:
            with self.subTest(name):
                self.assertEqual(pl.parse_reply(h(rep)), parsed)

    def test_value_is_low_nibble_of_sl(self):
        self.assertEqual(pl.parse_reply(reply(0x6E, 0x88, 0x02, 0x00, 0x08, 0x00, 0x00, 0x07, 0x00, 0x34)), (7, 4))

    def test_wrong_checksum(self):
        for _, _, _, rep, _ in EXCHANGES:
            bad = bytearray(h(rep))
            bad[10] ^= 0x01
            self.assertIsNone(pl.parse_reply(bytes(bad)))

    def test_wrong_length(self):
        good = h(EXCHANGES[0][3])
        for r in (b"", good[:10], good + b"\x00"):
            with self.subTest(length=len(r)):
                self.assertIsNone(pl.parse_reply(r))

    def test_wrong_opcode(self):
        # valid checksums, so only the opcode / VCP code check can reject them
        not_vcp_reply = reply(0x6E, 0x88, 0x03, 0x00, 0x08, 0x00, 0x00, 0x01, 0x00, 0x02)
        other_vcp_code = reply(0x6E, 0x88, 0x02, 0x00, 0x10, 0x00, 0x00, 0x01, 0x00, 0x02)
        self.assertIsNone(pl.parse_reply(not_vcp_reply))
        self.assertIsNone(pl.parse_reply(other_vcp_code))


# ---- EDID ----

class EdidTest(unittest.TestCase):
    def test_fixture_is_the_real_edid(self):
        self.assertEqual(len(DASUNG_EDID), 128)
        self.assertEqual(sum(DASUNG_EDID) % 256, 0)
        self.assertEqual(pnp_id(DASUNG_EDID), "DSC")
        self.assertIn(b"DASUNG Paper", DASUNG_EDID)
        self.assertIn(b"like Pro", DASUNG_EDID)

    def test_real_dasung(self):
        self.assertTrue(pl.is_dasung(DASUNG_EDID))

    def test_other_monitor(self):
        other = make_edid("ABC", "Generic 24")
        self.assertEqual(pnp_id(other), "ABC")
        self.assertNotIn(b"\x12\x63", other[8:10])
        self.assertNotIn(b"DASUNG", other)
        self.assertFalse(pl.is_dasung(other))

    def test_pnp_id_or_name_is_enough(self):
        self.assertTrue(pl.is_dasung(make_edid("DSC", "Generic 24")))
        self.assertTrue(pl.is_dasung(make_edid("ABC", "DASUNG Paper")))

    def test_name_in_extension_block_ignored(self):
        self.assertFalse(pl.is_dasung(make_edid("ABC", "Generic 24") + b"\x02\x03" + b"DASUNG".ljust(126, b"\x00")))

    def test_short_input(self):
        for edid in (b"", DASUNG_EDID[:64], DASUNG_EDID[:127]):
            with self.subTest(length=len(edid)):
                self.assertFalse(pl.is_dasung(edid))


# ---- modes and contrast ----

class ModeTest(unittest.TestCase):
    def test_defaults_per_mode(self):
        expected = {"floyd": [(0x07, 1), (0x08, 5)], "a2": [(0x07, 2), (0x09, 190)], "16": [(0x07, 3)],
                    "a5": [(0x07, 4), (0x0B, 160)], "a2-low": [(0x07, 5), (0x0A, 190)], "a61": [(0x07, 6)]}
        self.assertEqual(set(expected), set(pl.MODES))
        for name, pairs in expected.items():
            with self.subTest(name):
                self.assertEqual(pl.mode_pairs(pl.MODES[name]), pairs)

    def test_contrast_in_range(self):
        for mode, (cmd, lo, hi, _) in pl.CONTRAST.items():
            for value in (lo, hi):
                with self.subTest(mode=mode, value=value):
                    self.assertEqual(pl.mode_pairs(mode, value), [(0x07, mode), (cmd, value)])

    def test_contrast_out_of_range(self):
        for mode, (_, lo, hi, _) in pl.CONTRAST.items():
            for value in (lo - 1, hi + 1):
                with self.subTest(mode=mode, value=value):
                    with self.assertRaises(SystemExit) as cm:
                        pl.mode_pairs(mode, value)
                    self.assertIn(f"{lo}-{hi}", str(cm.exception))

    def test_tables_consistent(self):
        self.assertEqual(sorted(pl.MODES.values()), [1, 2, 3, 4, 5, 6])
        self.assertEqual(pl.MODE_NAMES, {v: k for k, v in pl.MODES.items()})
        self.assertLessEqual(set(pl.CONTRAST), set(pl.MODES.values()))
        cmds = [cmd for cmd, _, _, _ in pl.CONTRAST.values()]
        self.assertEqual(sorted(cmds), [0x08, 0x09, 0x0A, 0x0B])
        for mode, (_, lo, hi, default) in pl.CONTRAST.items():
            with self.subTest(mode=pl.MODE_NAMES[mode]):
                self.assertTrue(0 <= lo <= default <= hi <= 255)

    def test_waits_match_protocol_doc(self):
        self.assertEqual(pl.WAITS, {0x01: 0.1, 0x02: 0.6, 0x04: 0.6, 0x06: 0.5, 0x07: 0.8})


# ---- describe ----

class DescribeTest(unittest.TestCase):
    def test_describe(self):
        cases = [((0x01, 2), "alive (heartbeat OK)"),
                 ((0x07, 2), "alive, last change: mode 2 (a2)"),
                 ((0x07, 4), "alive, last change: mode 4 (a5)"),
                 ((0x07, 8), "alive, last change: ghost clear (or screensaver cancelled)"),
                 ((0x06, 4), "type 0x06 value 4"),
                 (None, "no valid reply")]
        for rep, text in cases:
            with self.subTest(rep=rep):
                self.assertEqual(pl.describe(rep), text)

    def test_describe_real_replies(self):
        self.assertEqual(pl.describe(pl.parse_reply(h(EXCHANGES[0][3]))), "alive (heartbeat OK)")
        self.assertEqual(pl.describe(pl.parse_reply(h(EXCHANGES[1][3]))),
                         "alive, last change: ghost clear (or screensaver cancelled)")


# ---- I2C with mocked syscalls ----

class MonitorTest(unittest.TestCase):
    def test_tripwire_blocks_real_i2c(self):
        with self.assertRaises(AssertionError):
            pl.Monitor(5)
        with self.assertRaises(AssertionError):
            pl.read_edid(5)

    def test_open_and_close(self):
        with fake_i2c() as io_:
            m = pl.Monitor(5)
            m.close()
        io_.open.assert_called_once_with("/dev/i2c-5", os.O_RDWR)
        io_.ioctl.assert_called_once_with(FD, 0x0703, 0x37)
        io_.close.assert_called_once_with(FD)

    def test_send_real_exchanges(self):
        for name, (cmd, arg), packet, rep, parsed in EXCHANGES:
            with self.subTest(name), fake_i2c(h(rep)) as io_:
                self.assertEqual(pl.Monitor(5).send(cmd, arg), parsed)
                io_.write.assert_called_once_with(FD, h(packet))
                io_.read.assert_called_once_with(FD, 11)
                io_.sleep.assert_called_once_with(pl.WAITS[cmd])

    def test_send_default_wait_and_invalid_reply(self):
        with fake_i2c(b"\xff" * 11) as io_:
            self.assertIsNone(pl.Monitor(5).send(0x08, 0x05))
        io_.write.assert_called_once_with(FD, h("51 84 03 08 08 05 bd"))
        io_.sleep.assert_called_once_with(0.5)

    def test_get(self):
        with fake_i2c(h(EXCHANGES[0][3])) as io_:
            self.assertEqual(pl.Monitor(5).get(), (1, 2))
        io_.write.assert_called_once_with(FD, h("51 82 01 08 b4"))
        io_.read.assert_called_once_with(FD, 11)
        io_.sleep.assert_called_once_with(0.1)

    def test_run(self):
        out = io.StringIO()
        with fake_i2c(h(EXCHANGES[2][3]), h(EXCHANGES[1][3])) as io_, contextlib.redirect_stdout(out):
            self.assertEqual(pl.Monitor(5).run([(0x07, 0x02), (0x06, 0x01)]), [(7, 2), (7, 8)])
        self.assertEqual([c.args[1] for c in io_.write.call_args_list], [h(EXCHANGES[2][2]), h(EXCHANGES[1][2])])
        self.assertEqual([c.args[0] for c in io_.sleep.call_args_list], [0.8, 0.2, 0.5, 0.2])
        lines = out.getvalue().splitlines()
        self.assertTrue(lines[0].endswith("07 02 -> type=0x07 value=2"), lines)
        self.assertTrue(lines[1].endswith("06 01 -> type=0x07 value=8"), lines)

    def test_run_no_answer(self):
        with fake_i2c(write_error=OSError(errno.ENXIO, "No such device or address")):
            with self.assertRaises(SystemExit) as cm:
                pl.Monitor(5).run([(0x06, 0x01)], quiet=True)
        self.assertIn("06 01: no answer from the monitor (No such device or address)", str(cm.exception))

    def test_read_edid(self):
        with fake_i2c(DASUNG_EDID) as io_:
            self.assertEqual(pl.read_edid(7), DASUNG_EDID)
        io_.open.assert_called_once_with("/dev/i2c-7", os.O_RDWR)
        io_.ioctl.assert_called_once_with(FD, 0x0703, 0x50)
        io_.write.assert_called_once_with(FD, b"\x00")
        io_.read.assert_called_once_with(FD, 128)
        io_.close.assert_called_once_with(FD)

    def test_read_edid_closes_on_error(self):
        with fake_i2c(OSError(errno.EREMOTEIO, "Remote I/O error")) as io_:
            with self.assertRaises(OSError):
                pl.read_edid(7)
        io_.close.assert_called_once_with(FD)


# ---- finding the bus (fake sysfs, mocked EDID reads) ----

OTHER_EDID = make_edid("ABC", "Generic 24")


class FakeSysfs:
    """/sys/class/drm and /sys/bus/i2c/devices in a temp folder, with real symlinks so readlink/realpath work."""

    def __init__(self, root):
        self.root = root
        self.drm = os.path.join(root, "class", "drm")
        self.i2c = os.path.join(root, "bus", "i2c", "devices")
        os.makedirs(self.drm)
        os.makedirs(self.i2c)

    def gpu(self, card, name):
        """card<N>/device -> the GPU's device folder."""
        os.makedirs(os.path.join(self.root, "devices", name), exist_ok=True)
        os.makedirs(os.path.join(self.drm, card))
        os.symlink(os.path.join(self.root, "devices", name), os.path.join(self.drm, card, "device"))

    def bus(self, n, parent):
        """i2c-<n> as a child of a device folder (a GPU, or anything else)."""
        path = os.path.join(self.root, "devices", parent, f"i2c-{n}")
        os.makedirs(path)
        os.symlink(path, os.path.join(self.i2c, f"i2c-{n}"))

    def connector(self, name, edid, ddc=None, status="connected"):
        path = os.path.join(self.drm, name)
        os.makedirs(path)
        with open(os.path.join(path, "status"), "w") as f:
            f.write(status + "\n")
        with open(os.path.join(path, "edid"), "wb") as f:
            f.write(edid)
        if ddc is not None:
            os.symlink(os.path.join(self.i2c, f"i2c-{ddc}"), os.path.join(path, "ddc"))


class SysfsCase(unittest.TestCase):
    """Fake sysfs, a temp state file and a fake read_edid: `self.edids[bus]` is the EDID or the OSError to raise."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.sys = FakeSysfs(os.path.join(tmp.name, "sys"))
        self.edids = {}
        self.patch(pl, "SYS_DRM", self.sys.drm)
        self.patch(pl, "SYS_I2C", self.sys.i2c)
        self.patch(pl, "STATE", os.path.join(tmp.name, "cache", "paperlike", "state.json"))
        self.patch(pl, "read_edid", self.read_edid)

    def patch(self, obj, name, value):
        p = mock.patch.object(obj, name, value)
        p.start()
        self.addCleanup(p.stop)

    def read_edid(self, bus):
        r = self.edids.get(bus, FileNotFoundError(errno.ENOENT, "No such file or directory"))
        if isinstance(r, BaseException):
            raise r
        return r

    def unwritable_state(self):
        blocker = os.path.join(self.tmp, "not-a-folder")
        open(blocker, "w").close()
        self.patch(pl, "STATE", os.path.join(blocker, "state.json"))


SILENT = [errno.EREMOTEIO, errno.ETIMEDOUT, errno.ENXIO, errno.EIO]


class BusWithDdcLinksTest(SysfsCase):
    """i915/amdgpu/nouveau: the Dasung on DP-1 (ddc -> i2c-3), another monitor on HDMI-A-1 (ddc -> i2c-5)."""

    def setUp(self):
        super().setUp()
        self.sys.gpu("card1", "gpu0")
        self.sys.connector("card1-DP-1", DASUNG_EDID, ddc=3)
        self.sys.connector("card1-HDMI-A-1", OTHER_EDID, ddc=5)
        self.sys.connector("card1-HDMI-A-2", b"", ddc=6, status="disconnected")

    def test_dasung_edid(self):
        self.edids[3] = DASUNG_EDID
        self.assertEqual(pl.dasung_on_bus(3), ("DP-1", 3))
        self.assertEqual(pl.load_state(), {"connector": "DP-1", "bus": 3})

    def test_other_edid_refused(self):
        self.edids[5] = OTHER_EDID
        for write in (True, False):
            with self.subTest(write=write), self.assertRaises(SystemExit) as cm:
                pl.dasung_on_bus(5, write=write)
            self.assertIn("isn't a connected Dasung's", str(cm.exception))

    def test_silent_bus_of_another_monitor_refused(self):
        for err in SILENT:
            for write in (True, False):
                self.edids[5] = OSError(err, os.strerror(err))
                with self.subTest(errno=errno.errorcode[err], write=write), self.assertRaises(SystemExit) as cm:
                    pl.dasung_on_bus(5, write=write)
                self.assertIn("DDC bus of HDMI-A-1", str(cm.exception))

    def test_silent_bus_of_disconnected_connector_refused(self):
        self.edids[6] = OSError(errno.ENXIO, "No such device or address")
        with self.assertRaises(SystemExit) as cm:
            pl.dasung_on_bus(6)
        self.assertIn("DDC bus of HDMI-A-2", str(cm.exception))

    def test_silent_bus_unknown_to_sysfs_refused(self):
        # the Dasung's ddc link names bus 3, so bus 7 isn't it
        self.edids[7] = OSError(errno.EREMOTEIO, "Remote I/O error")
        for write in (True, False):
            with self.subTest(write=write), self.assertRaises(SystemExit) as cm:
                pl.dasung_on_bus(7, write=write)
            self.assertIn("puts the Dasung on another bus", str(cm.exception))

    def test_silent_dasung_bus_found_by_ddc_link(self):
        self.edids[3] = OSError(errno.EREMOTEIO, "Remote I/O error")
        self.assertEqual(pl.dasung_on_bus(3), ("DP-1", 3))
        self.assertEqual(pl.dasung_on_bus(3, write=False), ("DP-1", 3))

    def test_kernel_driver_bus_refused(self):
        self.edids[0] = OSError(errno.EBUSY, "Device or resource busy")
        with self.assertRaises(SystemExit) as cm:
            pl.dasung_on_bus(0)
        self.assertIn("isn't a monitor's DDC bus", str(cm.exception))

    def test_find_dasung_uses_ddc_link(self):
        self.assertEqual(pl.find_dasung(), ("DP-1", 3))

    def test_unwritable_cache_is_ignored(self):
        self.unwritable_state()
        self.edids[3] = DASUNG_EDID
        self.assertEqual(pl.dasung_on_bus(3, write=False), ("DP-1", 3))
        pl.save_state(mode=2)
        self.assertEqual(pl.load_state(), {})


class BusWithoutDdcLinksTest(SysfsCase):
    """NVIDIA: no ddc links. The Dasung on HDMI-A-1 of card0, whose GPU has buses 4 and 6; bus 9 is elsewhere."""

    def setUp(self):
        super().setUp()
        self.sys.gpu("card0", "gpu0")
        self.sys.bus(4, "gpu0")
        self.sys.bus(6, "gpu0")
        self.sys.bus(9, "chipset")
        self.sys.connector("card0-HDMI-A-1", DASUNG_EDID)
        self.sys.connector("card0-DP-1", OTHER_EDID)

    def test_find_dasung_matches_edid(self):
        self.edids.update({4: OTHER_EDID, 6: DASUNG_EDID})
        self.assertEqual(pl.find_dasung(), ("HDMI-A-1", 6))
        self.assertEqual(pl.load_state(), {"connector": "HDMI-A-1", "bus": 6})

    def test_find_dasung_with_unwritable_cache(self):
        self.unwritable_state()
        self.edids.update({4: OTHER_EDID, 6: DASUNG_EDID})
        self.assertEqual(pl.find_dasung(), ("HDMI-A-1", 6))

    def test_find_dasung_falls_back_to_cached_silent_bus(self):
        pl.save_state(connector="HDMI-A-1", bus=6)
        self.edids.update({4: OTHER_EDID, 6: OSError(errno.EREMOTEIO, "Remote I/O error")})
        self.assertEqual(pl.find_dasung(), ("HDMI-A-1", 6))

    def test_find_dasung_no_fallback_to_answering_bus(self):
        pl.save_state(connector="HDMI-A-1", bus=4)
        self.edids.update({4: OTHER_EDID, 6: OSError(errno.EREMOTEIO, "Remote I/O error")})
        with self.assertRaises(SystemExit):
            pl.find_dasung()

    def test_dasung_edid(self):
        self.edids[4] = DASUNG_EDID
        self.assertEqual(pl.dasung_on_bus(4), ("HDMI-A-1", 4))

    def test_silent_bus_on_the_gpu(self):
        # a half-booted Dasung: usable for writes, but detect/status can't name it
        self.edids[4] = OSError(errno.EREMOTEIO, "Remote I/O error")
        self.assertEqual(pl.dasung_on_bus(4), ("HDMI-A-1", 4))
        self.assertEqual(pl.dasung_on_bus(4, write=False), ("?", 4))

    def test_silent_bus_off_the_gpu_refused(self):
        self.edids[9] = OSError(errno.ENXIO, "No such device or address")
        with self.assertRaises(SystemExit) as cm:
            pl.dasung_on_bus(9)
        self.assertIn("puts the Dasung on another bus", str(cm.exception))

    def test_detect_reports_unverified_bus(self):
        self.edids[4] = OSError(errno.EREMOTEIO, "Remote I/O error")
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["paperlike", "--bus", "4", "detect"]), contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as cm:
                pl.main()
        self.assertIn("Can't verify /dev/i2c-4", str(cm.exception))
        self.assertEqual(out.getvalue(), "")


class NoDasungTest(SysfsCase):
    def setUp(self):
        super().setUp()
        self.sys.gpu("card0", "gpu0")
        self.sys.bus(4, "gpu0")
        self.sys.connector("card0-DP-1", OTHER_EDID)

    def test_silent_bus(self):
        self.edids[4] = OSError(errno.EREMOTEIO, "Remote I/O error")
        with self.assertRaises(SystemExit) as cm:
            pl.dasung_on_bus(4)
        self.assertIn("No Dasung Paperlike connected", str(cm.exception))
        self.assertEqual(pl.dasung_on_bus(4, write=False), ("?", 4))

    def test_find_dasung(self):
        with self.assertRaises(SystemExit) as cm:
            pl.find_dasung()
        self.assertIn("No Dasung Paperlike connected", str(cm.exception))


# ---- Hyprland instance lookup ----

LIVE_PID = os.getpid()
DEAD_PID = 2 ** 22 + 1  # above Linux's PID limit, so never running


class HyprCase(unittest.TestCase):
    """A temp $XDG_RUNTIME_DIR, a cleared environment, and every desktop tool reported as installed (none runs)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.runtime = tmp.name
        self.hypr = os.path.join(tmp.name, "hypr")
        self.env({})
        p = mock.patch.object(pl, "have", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def env(self, extra):
        p = mock.patch.dict(pl.os.environ, dict(extra, XDG_RUNTIME_DIR=self.runtime), clear=True)
        p.start()
        self.addCleanup(p.stop)

    def instance(self, sig, pid=None, mtime=None):
        """An instance folder; pid=None leaves only the log, like a Hyprland that exited."""
        d = os.path.join(self.hypr, sig)
        os.makedirs(d)
        open(os.path.join(d, "hyprland.log"), "w").close()
        if pid is not None:
            with open(os.path.join(d, "hyprland.lock"), "w") as f:
                f.write(f"{pid}\nwayland-1\n")
        if mtime is not None:
            os.utime(d, (mtime, mtime))

    def sig_of(self, env):
        return None if env is None else env.get("HYPRLAND_INSTANCE_SIGNATURE")


class HyprlandEnvTest(HyprCase):
    def test_no_hyprctl(self):
        self.instance("0123abcd_1700000000_1", LIVE_PID)
        with mock.patch.object(pl, "have", return_value=False):
            self.assertIsNone(pl.hyprland_env())

    def test_no_instances(self):
        self.assertIsNone(pl.hyprland_env())
        os.makedirs(self.hypr)
        self.assertIsNone(pl.hyprland_env())

    def test_exited_instances_are_skipped(self):
        self.instance("0123abcd_1700000000_1")             # lock removed on exit
        self.instance("0123abcd_1700000100_2", DEAD_PID)   # lock left by a crash
        self.assertIsNone(pl.hyprland_env())

    def test_found_without_signature(self):
        self.instance("0123abcd_1700000000_1", LIVE_PID)
        env = pl.hyprland_env()
        self.assertEqual(self.sig_of(env), "0123abcd_1700000000_1")
        self.assertEqual(env["XDG_RUNTIME_DIR"], self.runtime)

    def test_live_signature_is_kept(self):
        self.instance("0123abcd_1700000000_1", LIVE_PID)
        self.instance("0123abcd_1800000000_2", LIVE_PID)
        self.env({"HYPRLAND_INSTANCE_SIGNATURE": "0123abcd_1700000000_1"})
        self.assertEqual(self.sig_of(pl.hyprland_env()), "0123abcd_1700000000_1")

    def test_stale_signature_is_replaced(self):
        # the Hyprland a long-running watch started under has exited; a new one is running
        self.instance("0123abcd_1700000000_1")
        self.instance("4567cdef_1800000000_2", LIVE_PID)
        self.env({"HYPRLAND_INSTANCE_SIGNATURE": "0123abcd_1700000000_1"})
        self.assertEqual(self.sig_of(pl.hyprland_env()), "4567cdef_1800000000_2")

    def test_newest_by_start_time_not_mtime(self):
        self.instance("0123abcd_1800000000_2", LIVE_PID, mtime=1000)
        self.instance("4567cdef_1700000000_1", LIVE_PID, mtime=2000)
        self.instance("89abcdef_1900000000_3", mtime=3000)  # exited
        self.assertEqual(self.sig_of(pl.hyprland_env()), "0123abcd_1800000000_2")

    def test_old_hyprland_signature_trusted(self):
        # older Hyprland keeps its sockets in /tmp/hypr, so there is nothing under $XDG_RUNTIME_DIR to check
        self.env({"HYPRLAND_INSTANCE_SIGNATURE": "0123abcd_1700000000_1"})
        self.assertIs(pl.hyprland_env(), pl.os.environ)

    def test_sway_session(self):
        self.instance("0123abcd_1700000000_1", LIVE_PID)
        sock = os.path.join(self.runtime, "sway-ipc.sock")
        self.env({"SWAYSOCK": sock})
        self.assertEqual(self.sig_of(pl.hyprland_env()), "0123abcd_1700000000_1")  # stale SWAYSOCK: no socket
        open(sock, "w").close()
        self.assertIsNone(pl.hyprland_env())


class RelinkTest(HyprCase):
    def relink(self):
        calls = []
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(pl, "sh", side_effect=lambda *args, env=None: calls.append(args[0])))
            stack.enter_context(mock.patch.object(pl.time, "sleep"))
            run = stack.enter_context(mock.patch.object(pl.subprocess, "run"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            pl.relink("DP-1")
        run.assert_not_called()  # hyprctl monitors / eval
        return calls

    def test_leftover_hyprland_folder_on_another_desktop(self):
        self.instance("0123abcd_1700000000_1")
        self.env({"WAYLAND_DISPLAY": "wayland-1"})
        self.assertEqual(self.relink(), ["wlr-randr", "wlr-randr"])
        sock = os.path.join(self.runtime, "sway-ipc.sock")
        open(sock, "w").close()
        self.env({"WAYLAND_DISPLAY": "wayland-1", "SWAYSOCK": sock})
        self.assertEqual(self.relink(), ["swaymsg", "swaymsg"])


# ---- watch (mocked lookups and clock) ----

class StopWatch(BaseException):
    """Ends the watch loop; a BaseException so the loop's own `except Exception` doesn't swallow it."""


class WatchTest(unittest.TestCase):
    OUTS = {"/sys/class/drm/card0-HDMI-A-1": DASUNG_EDID}

    def watch(self, outputs, lookup, polls):
        clock = [1000.0]
        done = []

        def sleep(seconds):
            clock[0] += seconds
            if seconds == 2:  # one poll
                done.append(seconds)
                if len(done) == polls:
                    raise StopWatch

        out = io.StringIO()
        a = types.SimpleNamespace(bus=None, mode=None, clear_every=0)
        with contextlib.ExitStack() as stack:
            patch = lambda obj, name, **kw: stack.enter_context(mock.patch.object(obj, name, **kw))
            patch(pl, "dasung_outputs", side_effect=outputs)
            find = patch(pl, "find_dasung", side_effect=lookup)
            wake = patch(pl, "wake")
            patch(pl, "load_state", return_value={})
            patch(pl.time, "time", side_effect=lambda: clock[0])
            patch(pl.time, "sleep", side_effect=sleep)
            stack.enter_context(contextlib.redirect_stdout(out))
            with self.assertRaises(StopWatch):
                pl.watch(a, {})
        return find, wake, out.getvalue()

    def test_failed_lookup_retried_every_10s_and_logged_once(self):
        find, wake, out = self.watch(lambda: self.OUTS, SystemExit("not its I2C bus."), polls=12)  # 24 s
        self.assertEqual(find.call_count, 3)  # at 0, 10 and 20 s
        self.assertEqual(out.count("not its I2C bus."), 1, out)
        wake.assert_not_called()

    def test_os_error_logged_once(self):
        find, _, out = self.watch(lambda: self.OUTS, PermissionError(errno.EACCES, "denied"), polls=12)
        self.assertEqual(out.count("denied"), 1, out)
        self.assertNotIn("watch:", out)

    def test_wakes_once_found(self):
        find, wake, _ = self.watch(lambda: self.OUTS, [SystemExit("nope"), ("HDMI-A-1", 6)], polls=8)
        self.assertEqual(find.call_count, 2)
        wake.assert_called_once_with("HDMI-A-1", 6, pl.MODES["a5"])

    def test_unplug_logged_even_if_lookup_failed(self):
        _, _, out = self.watch([self.OUTS, self.OUTS, {}, {}], SystemExit("nope"), polls=4)
        self.assertEqual(out.count("Dasung unplugged"), 1, out)

    def test_replug_looks_up_at_once(self):
        _, wake, out = self.watch([self.OUTS, {}, self.OUTS, self.OUTS], [("HDMI-A-1", 6), ("HDMI-A-1", 6)], polls=4)
        self.assertEqual(wake.call_count, 2)
        self.assertEqual(out.count("Dasung unplugged"), 1, out)


# ---- CLI ----

class CliTest(unittest.TestCase):
    def test_version(self):
        self.assertRegex(pl.__version__, r"^\d+\.\d+\.\d+$")
        r = subprocess.run([sys.executable, "-I", SCRIPT, "--version"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, f"paperlike {pl.__version__}\n")


if __name__ == "__main__":
    unittest.main()
