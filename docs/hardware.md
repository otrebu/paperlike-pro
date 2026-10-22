# Paperlike Pro hardware notes

## Connections

- **The 3-ended cable:** mini-HDMI into the monitor, HDMI into the computer, and a USB plug for **power**
  (5 V / 2 A, or a USB 3 port). Picture and control both use the HDMI part. The USB plug carries no data.
- **The small USB-A socket** on the monitor's edge: the manual calls it an outlet for a reading lamp. Inside, it's
  wired to a **Prolific PL2303 USB-serial bridge** (`067b:2303`). Dasung's 2018 quick-start sheet describes the
  USB-A to USB-A cable in the box as being "for firmware upgrade in some emergency (non standard)". This socket
  also **powers** the monitor, so the monitor stays on when only this cable is connected.
- Buttons: **C** full clear, **M** cycle mode (Floyd → A2 → 16; at 800×600 A5 → A2 → A61), **Power**,
  **C+M** restart.

## LED

The March 2018 manual edition gives the clearest meanings:

| Colour | Meaning |
|---|---|
| Off | no power |
| **Blue** | **no video signal**. Normal on USB power alone |
| White | start-up failure |
| Green | running with a signal |

The 2017 manual instead describes "white/blue = starting up", which is misleading. A blue light on USB power
alone is not a fault.

## Inside (from public teardown photos)

The chip markings are scrubbed, so these identifications come from package and layout and aren't certain.

- **Sub-board** behind the USB-A socket: an SSOP-28 chip (the PL2303) and a 12 MHz crystal. A 4-wire ribbon
  (TX, RX, GND, 5 V) runs to a main-board header labelled `P_USART`. There are no modem-control lines, so DTR/RTS
  can't reset the main controller.
- **Main board:** an LQFP-100 microcontroller (probably STM32/GD32 class), a BGA FPGA with an SOIC-8 config
  flash, DRAM, an LQFP-64 HDMI receiver (the ADV7611 matches the package), an E Ink bias PMIC, and a 15-pin
  `P_TEST` header.
- **Panel:** E Ink ED133UT2, 13.3" Carta, 1600×1200.

Sources: [Kev Zettler's teardown](https://kevzettler.com/2018/02/11/dasung-paperlike-pro-teardown/),
[Hackaday discussion](https://hackaday.com/2018/02/14/tearing-down-a-1000-e-ink-display/).

## The service serial port

Probed with the tools in `tools/`. All of them only listen or send handshake bytes, never write or erase.
Nothing answered:

- passive listening at 4800–921600 baud, idle and through C+M restarts
- CR/LF, `?`, `help`, `AT` at 8 baud rates (8N1)
- the STM32/GD32 ROM bootloader sync `0x7F` (8E1)
- continuous `0x7F` (STC-style ISP handshake) at 2400 8N1/8E1, 9600 and 115200 during restarts
- DTR/RTS reset and BOOT0 patterns, which can't work anyway with the 4-wire harness

Most likely it only responds to Dasung's own (unpublished) update tool or to a specific trigger. None of the
Windows apps (1.0.5–1.0.8) use a serial port. No firmware image for the Pro is publicly available. Dasung
support handled firmware privately or by swapping the main board.

A search of about 40 Dasung releases (2015–2026, live and archived) found no Pro firmware image, MCU hex, FPGA
bitstream, waveform file or update tool. Without one, writing anything to the board is likely to brick it.
The realistic options are asking Dasung support, or a read-only backup of the board's SOIC-8 flash with a clip and
a programmer, which means opening the case.

Later Dasung models (HD Revolutionary, 253, 13K, 103) use a different scheme: a CH340 serial control port with
ASCII-hex frames `5FF5 … A0FA` at 115200 8N1, and firmware updates via `ch341prog`. See
[sal7g86/eink-dasung-control](https://github.com/sal7g86/eink-dasung-control). That isn't how the Pro works.
