# Paperlike Pro DDC/CI protocol

Everything goes over **DDC/CI on the HDMI cable's I²C lines**: slave address 0x37 (write 0x6E, read 0x6F),
host source byte 0x51, XOR checksum. Dasung's apps find the monitor by its EDID: PnP ID `DSC` (product 1,
"DSC0001") and the name descriptors "DASUNG Paper" + "like Pro".

Status: **confirmed** means seen in Dasung's Linux, Mac and Windows apps *and* tested on a real monitor.
Anything else is marked.

## Writing a command

Every command is a **Set VCP Feature on VCP code 0x08** with a 2-byte value: high byte = command, low byte = argument.

```
to 0x37:  51 84 03 08 <CMD> <ARG> <checksum>
          checksum = 0x6E ^ 0x51 ^ 0x84 ^ 0x03 ^ 0x08 ^ CMD ^ ARG
ddcutil:  ddcutil -b <bus> --noverify setvcp 08 x<CMD><ARG>      (untested; ddcutil may not list the monitor)
Windows:  SetVCPFeature(hMonitor, 0x08, CMD << 8 | ARG)           (what Dasung's Windows app does)
```

VCP 0x08 is officially MCCS "Restore color defaults". **Never send these bytes to another monitor.**

## Reading the reply

After a command, wait 0.1–0.8 s (see the timings below) and do a plain 11-byte I²C read with nothing written first:

```
6E 88 02 <rc> 08 <type> <MH> <ML> <SH> <SL> <checksum>     checksum = 0x50 ^ bytes 0..9
```

A standard Get VCP request for 0x08 (`51 82 01 08 b4`) also gets this reply on Dasung firmware: a leaked
vendor test log has thousands of them from a DSC0001 monitor. That's not yet confirmed on our unit.

It has the shape of a Get-VCP reply. The apps use **ML as a packet type** and **SL & 0x0F as the value**:

| ML (type) | SL | Meaning |
|---|---|---|
| `01` | `02` | Heartbeat OK |
| `07` | 1–6 | Current mode (after a mode command, or after the M button). The apps assume 1–3 in 800×600 mode and add 3, but this unit reported 4 directly after `07 04` |
| `07` | `08` | Acknowledges a clear. It repeats for a few seconds afterwards (the vendor apps also read it as "screensaver cancelled") |
| `06` | `04` | Seen once, after `06 03`, which the Pro didn't act on. Possibly "not supported" |

A reply carries the latest event, so the first reply after a button press reports the press and the next
heartbeat reports "OK". **There is no command to read back the current mode, contrast, firmware version or
temperature.**

## Command table

Dasung's own names for the commands come from debug symbol files shipped alongside their 2018 Windows apps.

| CMD | Dasung's name | ARG | What it does | Status |
|---|---|---|---|---|
| `01` | BEAT_SIGNAL | `01` | Heartbeat ("normal"). The apps send it every 200–300 ms | confirmed |
| `02` | SCREENSAVER_SIGNAL | `01` / `00` | Enter / leave the monitor's screensaver. HD tools also use `02 02` | from the apps |
| `03` | TURNOFFMONITOR_SIGNAL | `01` | Monitor off (Dasung source). HD tools: `03 02` = on (needs a clear) | untested, avoid |
| `04` | MONITORRESOLUTION_SIGNAL | `01` / `02` | Resolution mode: normal / 800×600 | confirmed |
| `05` | THRESHOLD_SIGNAL | 0–255 | Generic threshold, sent once on connect by the 2017 Linux app only | from the apps |
| `06` | CLEANMONITOR_SIGNAL | `01` / `02` | Quick ghost clear / full clear (the whole panel flashes). `06 03` (both bits) did nothing on our Pro and got reply type 06/04 | confirmed |
| `07` | DISPALYMODE_SIGNAL (sic) | 1–6 | Image mode, see below | confirmed |
| `08` | THRESHOLD_FLOYD | 1–9 | Floyd contrast level | confirmed |
| `09` | THRESHOLD_A2H | 130–250 | A2 contrast (steps of 5 in the apps) | confirmed |
| `0A` | THRESHOLD_A2L | 130–250 | A2 contrast in 800×600 mode | from the apps |
| `0B` | THRESHOLD_A5L | 80–200 | A5 contrast | confirmed |
| `0C`, `0E`, `0F` | ADVANCED_SPEED, lights | | Paperlike HD only (ink speed, front lights). Not in the Pro app's symbols | don't send to a Pro |
| `0D` | none | | The only number not used in the 4-bit command field | unknown |

## Image modes (`07 nn`)

| nn | Name | Default contrast | Notes |
|---|---|---|---|
| 1 | Floyd | `08 05` | dithered |
| 2 | A2 | `09 BE` (190) | black/white, fast |
| 3 | 16 | none | 16 greys |
| 4 | A5 | `0B A0` (160) | vendor: 800×600 only; **works at 1600×1200 too** (tested) |
| 5 | A2 (800×600) | `0A BE` | |
| 6 | A61 | none | 800×600 |

## What the vendor apps do

- **On connect:** wait ~5–8 s → `07 <mode>` → per-mode contrast → `06 01`. The Linux 1.0.5 app also sends `05 <threshold>`.
- **Loop:** `01 01` → wait 0.1 s → read the reply → sleep 0.2–0.5 s. After 2–5 failed replies they treat the
  monitor as gone and rescan every 1–3 s.
- **Auto clear:** a quick clear on a timer (15–600 s, default 120 s). The Windows app turns every 4th quick clear
  into a full clear.
- **Hotkeys:** Linux Alt+C → `06 01`, Alt+H → `06 02`. Mac Ctrl+Z / Ctrl+X.
- **Screensaver:** after an idle period, `02 01`. On input, `02 00` then `06 01`.
- **800×600 mode:** set the OS resolution to 800×600, then `04 02`. Back: 1600×1200 and `04 01`.

## Timings used by this tool (taken from the apps)

| CMD | Wait before reading the reply |
|---|---|
| `01` | 0.1 s |
| `02`, `04` | 0.6 s |
| `06` | 0.5 s |
| `07` | 0.8 s |
| others | 0.5 s |

## Example exchange (real monitor)

```
heartbeat   51 84 03 08 01 01 b0  →  6e 88 02 00 08 00 00 01 00 02 bf   (type 01, value 2: OK)
quick clear 51 84 03 08 06 01 b7  →  6e 88 02 00 08 00 00 07 00 08 b3   (type 07, value 8)
mode A2     51 84 03 08 07 02 b5  →  6e 88 02 00 08 00 00 07 00 02 b9   (type 07, value 2: now A2)
```

## The monitor's EDID

EDID 1.3, manufacturer `DSC`, product 1, serial 0, "week 45 of 2016". The same date shows up on other units,
so it's probably fixed in firmware. Only two timings are listed: 1600×1200@60 (162 MHz) and 800×600@75.

```
00 ff ff ff ff ff ff 00 12 63 01 00 00 00 00 00 2d 1a 01 03 80 3e 22 78 2a 08 a5 a2 57 4f a2 28
0f 50 54 00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 48 3f 40 30 62 b0 32 40 40 c0
13 00 6d 55 21 00 00 1e 88 13 20 00 31 58 1f 20 10 50 13 00 6d 55 21 00 00 1e 00 00 00 fc 00 44
41 53 55 4e 47 20 50 61 70 65 72 0a 00 00 00 fc 00 6c 69 6b 65 20 50 72 6f 0a 20 20 20 20 00 5f
```
