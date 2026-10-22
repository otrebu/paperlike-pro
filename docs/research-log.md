# Research log

How the protocol and the black-screen fix were worked out, in October 2026, with one Paperlike Pro on an
Arch Linux (Omarchy, Hyprland) laptop with an NVIDIA GPU.

## 1. The bundled software (static analysis)

The USB stick in the box holds the v1.0.5 apps: Ubuntu 16.04 (.deb), macOS (.pkg) and Windows
(Setup Factory 6 installers), plus manuals. Nothing was executed. The binaries were decompiled with Ghidra.

- **Linux app:** GTK2 + X11, needs root. It captures the raw console keyboard for its hotkeys and runs a bundled
  `xrandr` clone (`ResChange`) for the 800×600 mode. It drives the monitor over `/dev/i2c-*` with
  ddccontrol-style DDC/CI code.
- **Mac app:** a debug build that kept its function names (`SendHeartSignal`, `SendClearMonitor`,
  `SendModeSelect`, `SendMonitorA2Threshold`, …). That made the command numbers easy to read off.
- Both apps send the same packets: Set VCP 0x08 = CMD:ARG (see [protocol.md](protocol.md)).
- The Windows apps 1.0.5–1.0.8 (a June 2018 package still on Dasung's download page) confirm the same table via
  `SetVCPFeature(h, 0x08, …)`. They don't use the serial port, ship no firmware, and have no lock/licence logic.

## 2. Cross-checking

Independent projects for the later Paperlike HD use the same VCP 0x08 scheme (`07` mode, `08` contrast, `06` clear,
plus HD-only `0C`/`0E`/`0F`). An oscilloscope capture of Dasung's client on a Pro shows the heartbeat
`51 84 03 08 01 01 B0` every 300 ms. Source code of an early Linux client, apparently from its developer, is on
GitHub without a licence. Its comments match the command meanings. Nothing from it is used here.

## 3. First connection: picture black, bus silent

- At the first plug-in the screen showed speckled grey noise. Later it showed solid black.
- The kernel read the EDID at hotplug, but afterwards every I²C read on the monitor's bus failed (EIO), even the
  EDID address. Another monitor on the same port worked fine, so the GPU side was healthy.
- The buttons didn't respond. On USB power alone the LED stayed blue, which, as a later manual explains, just means
  "no video signal".

## 4. The hidden serial port

A USB-A to USB-A cable into the small "lamp" socket brought up a PL2303 USB-serial bridge. Gentle probing
(listening, text prompts, bootloader handshakes, DTR/RTS patterns, during restarts) got no answer.
Teardown photos later explained why the reset tricks couldn't work: only TX/RX/GND/5 V reach the main board.
See [hardware.md](hardware.md).

## 5. Control comes back

After several C+M restarts and reconnections, DDC/CI started answering: the heartbeat replied "OK", mode changes
were confirmed in the replies, and the monitor drew its own "A2" mode label and flashed on full clears.
A webcam pointed at the panel confirmed it. But the desktop still showed as solid black in every mode, at
1600×1200 and 800×600, and with a minute of continuous heartbeats. So it wasn't a "locked without
software" behaviour.

## 6. The fix

Turning the computer's output to the monitor off and on (Hyprland `hl.monitor({output=…, disabled=true})`,
4 s, re-enable with `disabled=false`, 8 s), then `07 01`, `08 05`, `06 02`, made the picture appear. A white
test card with a black X and grey bars showed correctly on camera. It was repeated several times through
`paperlike wake` and `paperlike watch` with the same result.

Interpretation: the monitor's HDMI input hadn't locked onto the signal after a bad start-up. Re-sending the
signal once the monitor is fully up re-locks it.

## 7. Tuning

- A light desktop theme (pure white background, black text) makes the biggest difference on e-ink.
- **A5 works at 1600×1200.** The vendor app only offers A5 at 800×600, but the monitor accepts `07 04` at full
  resolution (with `04 01`) and draws normally. In use it felt clearly better than A2, so it's the tool's default.
- Floyd at contrast level 5 renders only the lightest grey shades as light. Use `paperlike contrast` to tune it.

## Open questions

- What does `03 nn` do on the Pro? It's "monitor off" in Dasung's source. Not tested.
- Does the service port answer at all, and to what? It probably needs Dasung's update tool.
- Is there any readback of contrast or mode? None is known.
