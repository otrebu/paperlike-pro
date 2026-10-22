# paperlike-pro

A small command-line tool to control a **DASUNG Paperlike Pro** (13.3" E Ink monitor, 2016/2017) from Linux,
plus notes on how the monitor talks to the computer. The vendor's own Linux app (2017) is an X11/GTK2 program
that needs root. This tool is a single Python file with no dependencies, and it works on Wayland.

It talks to the monitor over the HDMI cable's DDC/CI channel, the same way Dasung's apps do.

```sh
./paperlike detect           # find the monitor and its I2C bus
./paperlike status           # read-only: is it alive, and what changed last
./paperlike mode a5          # floyd | a2 | 16 | a5 | a2-low | a61
./paperlike contrast 200     # contrast for the current mode
./paperlike clear --full     # clear ghosting (quick without --full)
./paperlike wake             # bring the picture back when the screen stays black
./paperlike watch            # run `wake` automatically whenever the monitor is plugged in
./paperlike raw 07 02 06 02  # send raw command/argument pairs (hex)
```

## The black-screen fix

If the monitor answers commands (`status` says alive, the mode label appears, a full clear flashes the panel)
but the picture stays black, its video input hasn't locked onto the signal. This happens when it starts up late
or badly. `paperlike wake` turns the computer's output to the monitor off for a few seconds and back on,
then sends a mode change and a full clear. That re-locks it.

## Modes

| Mode | Command | Notes |
|---|---|---|
| `floyd` | `07 01` | Dithered greys, good all-round |
| `a2` | `07 02` | Pure black and white, fast, crisp text |
| `16` | `07 03` | 16 greys, slowest, best for photos |
| `a5` | `07 04` | Dasung's fast mode. The vendor app only offers it at 800×600. At 1600×1200 it works but measures the same as A2 |
| `a2-low` / `a61` | `07 05` / `07 06` | The vendor's 800×600 modes |

`a5` is the default for `wake` and `watch`.

## Requirements

- Linux with the `i2c-dev` module and read/write access to the monitor's `/dev/i2c-N`. Many distros give the
  logged-in user access through udev (for example ddcutil's rules); otherwise add yourself to the `i2c` group.
- Python 3.8+.
- For `wake`/`watch`, one of: Hyprland (`hyprctl`), sway (`swaymsg`), another wlroots compositor (`wlr-randr`),
  KDE (`kscreen-doctor`) or X11 (`xrandr`).

Tested on Arch Linux (Omarchy), Hyprland 0.56 and an NVIDIA GPU. The other desktop backends are written but untested.
macOS and Windows aren't supported yet. The protocol is the same there, see [docs/protocol.md](docs/protocol.md).

## Safety

On a normal monitor, VCP code 0x08 (the code Dasung reuses for every command) means **"restore colour defaults"**.
The tool only writes to an I2C bus whose EDID belongs to a DASUNG display, or to the cached bus for that same
connector when a half-started monitor stops answering EDID reads. If you pass `--bus N` by hand, make sure it's
the Dasung.

E Ink panels wear with refreshes. Dasung advises against video and games on this monitor.

## Docs

- [docs/protocol.md](docs/protocol.md): the DDC/CI command set, replies and timings
- [docs/hardware.md](docs/hardware.md): what's inside, the LED colours, the hidden service port
- [docs/troubleshooting.md](docs/troubleshooting.md): black screen, noise, power, NVIDIA
- [docs/research-log.md](docs/research-log.md): how this was worked out
- [docs/experiments.md](docs/experiments.md): measured speed, contrast and grey rendering of every mode

`tools/` holds the research probes used along the way: a read-only DDC/CI probe and three tools for the service
serial port. They aren't needed for normal use.

## Credits and sources

No code from any of these projects is included. They were read as references, and the facts they document
cross-checked our own findings.

- [leoluk/paperlike-go](https://github.com/leoluk/paperlike-go) (Apache-2.0): Go tool for the Paperlike HD with the same VCP 0x08 scheme
- [isotherm/paperlike-controls](https://github.com/isotherm/paperlike-controls) (MIT): Windows command table for the HD
- [dzirtusss/paperlike-mac](https://github.com/dzirtusss/paperlike-mac): macOS IOKit tool and command list for the HD
- [JaydenN117/i2C-HDMI-injector](https://github.com/JaydenN117/i2C-HDMI-injector) (MIT): oscilloscope capture of the Pro's heartbeat
- [sal7g86/eink-dasung-control](https://github.com/sal7g86/eink-dasung-control) (Apache-2.0): notes on the later serial-controlled models
- [kevzettler.com teardown](https://kevzettler.com/2018/02/11/dasung-paperlike-pro-teardown/) and
  [Hackaday](https://hackaday.com/2018/02/14/tearing-down-a-1000-e-ink-display/): hardware photos and discussion
- Dasung's freely distributed Paperlike Pro apps (v1.0.5–1.0.8) and manuals, studied statically for interoperability.
  None of their files are redistributed here.

## License

MIT, see [LICENSE](LICENSE).

DASUNG and Paperlike are trademarks of Beijing Dasung Technology Co., Ltd. This project isn't affiliated with or
endorsed by Dasung. Use it at your own risk.
