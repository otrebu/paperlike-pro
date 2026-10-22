# Experiments

Measured on one Paperlike Pro with a webcam (30 fps, fixed exposure) pointed at the panel. Each test set the
mode or value, did a full clear, then flipped the whole screen between black and white six times, 1.6 s apart.
"Switch time" runs from the computer showing the new frame to the panel reaching 90% of the change. It includes
the compositor and HDMI path, so compare the numbers with each other, not with panel specs. Run-to-run noise is
about ±30 ms.

## Tier 1: documented commands, new values and combinations (22 Oct 2026)

| Test | Bytes | Switch time | Black→white range* | Greys on the test card |
|---|---|---|---|---|
| A2 | `07 02` `09 be` | 380 ms | 93 | none: greys turn black |
| A5 at 1600×1200 | `07 04` `0b a0` | 378 ms | 94 | none |
| Floyd (contrast 5) | `07 01` `08 05` | 362 ms | 92 | none |
| 16 greys | `07 03` | 864 ms, with a flash | 106 | **yes**: smooth ramp, grey circle, checkerboard |
| A61 at 1600×1200 | `07 06` | 884 ms, with a flash | 106 | **yes**: looks identical to 16 |
| A2-low at 1600×1200 | `07 05` `0a be` | 386 ms | 94 | none |
| A5 + 800×600 flag at 1600×1200 | `04 02` `07 04` | 404 ms | 94 | none |
| A5 at a real 800×600 | `07 04` (output 800×600) | 334 ms | 94 | **yes**: grey circle and checkerboard visible |

\* Camera brightness of the white level minus the black level (0–255 scale). It's only for comparison between rows.

Findings:

- **At 1600×1200, A2, A5, Floyd and A2-low are effectively the same mode**: same speed, same contrast, and they all
  render mid-greys as black. 16 and A61 are the grey-capable modes, at about 2.3× the switch time.
- **A5 earns its name only at 800×600.** There it was the fastest setting measured and still showed grey detail.
- **Floyd contrast is the useful grey knob.** `08 01` shows dithered greys (ramp, grey circle, checkerboard) at
  Floyd's speed. `08 05` to `08 09` push greys to black. `08 0f` (out of range) behaves like `08 09`, so it's clamped.
- **A5 contrast (`0b 30` to `0b f0`, i.e. 48–240, beyond the documented 80–200) made no visible difference at
  1600×1200.** It may only apply in 800×600 mode.
- **Clears:** `06 01` gives a short dark blink (about 0.25 s). `06 02` gives a longer black-and-white flash (about 0.5 s).
- **`06 03` (the Paperlike HD's clear code) does nothing on the Pro**. The monitor answers with a reply type never
  seen before: **type 0x06, value 4**. That looks like a "not supported" answer, which would make it possible to
  map which commands exist without guessing from behaviour. Unconfirmed.
- **`02 01` (screensaver on)** showed no visible change within 6 s.
- **Other resolutions:** Hyprland only offered the two EDID modes (1600×1200@60, 800×600@75) and snapped requests
  for 1200×900, 1024×768 and 1600×1200@30 to those. Testing in-between resolutions needs a custom modeline.

Takeaways:

- Text and terminals: A2 or A5 (identical at full resolution).
- Mixed content with some greys: Floyd with `paperlike contrast 1`.
- Photos: 16.
- Maximum speed with greys: 800×600 + A5, at the cost of resolution.

## Tier 2: status reads, the free command number, running without software (22 Oct 2026)

- **A standard Get VCP 0x08 works.** `51 82 01 08 b4`, then a read 0.1 s later, returns the usual reply
  (`6e 88 02 00 08 00 00 01 00 02 bf`, i.e. "heartbeat OK") without sending any command. `paperlike status` now
  uses this, so checking the monitor is read-only. `ddcutil -b N getvcp 08` still fails ("DDC communication failed").
- **`0D 00`**, the only unused number in the 4-bit command field, did nothing visible. The reply was the normal
  "heartbeat OK". It didn't get the `06/04` reply that `06 03` got, so `06/04` isn't a general "not supported" answer.
- **No heartbeat needed.** With a static test card and no DDC traffic at all for 10 minutes (a webcam still every
  30 s), the picture didn't change: no warning screen, no sleep. A status read afterwards answered "heartbeat OK".
  The Paperlike HD reportedly shows an "install the driver" warning without heartbeats. This Pro doesn't, at least
  over 10 minutes.

Not tested yet: `03 01` (monitor off in Dasung's source, with `03 00` presumably back on).
