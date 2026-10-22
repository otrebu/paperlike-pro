# Troubleshooting

## The screen stays black, but the monitor answers

Symptoms: `paperlike status` says alive, the monitor's own mode label ("A2" etc.) appears in a corner when you
change mode, and `paperlike clear --full` makes the whole panel flash white. But the desktop never shows up,
whatever the mode or resolution.

Cause: the monitor's video input never locked onto the HDMI signal, typically because the monitor came up late
or in a bad state.

Fix: `paperlike wake`. It turns the output off for 4 s, turns it back on with the same mode, position and scale,
waits 8 s, then sends the resolution mode, image mode, contrast and a full clear. Unplugging and replugging the HDMI
and then running `paperlike clear --full` does the same by hand.

`paperlike watch` runs the same fix automatically whenever the monitor (re)appears, including at start. You can
run it from your session's autostart.

## Nothing answers on the I²C bus (EIO on every read)

If even the EDID address 0x50 returns I/O errors on the monitor's bus, while the same port works with another
monitor, the Dasung's controller is in a bad state. Restart it with **C+M**, make sure it has proper power, and
replug the HDMI. In our case the bus came back after a few restarts and reconnections, and the picture then
needed `paperlike wake`.

## Speckled grey "noise" instead of the picture

Other owners report "black dots noise" with cheap HDMI cables. The Pro needs a proper HDMI 1.4 cable straight
into the computer, without splitters.

## Power

Use a 5 V / 2 A charger or a USB 3 port for the power plug. Laptop USB 2 ports and keyboard hubs may not be
enough. The LED staying **blue** only means "no video signal" (see [hardware.md](hardware.md)).

## NVIDIA

DDC/CI works on NVIDIA's open kernel module here (`/dev/i2c-N` adapters named "NVIDIA i2c adapter …").
NVIDIA doesn't expose a `ddc` link under `/sys/class/drm/*`, so `paperlike` finds the bus by matching EDIDs on
the GPU's adapters. If you hit DDC timeouts on NVIDIA with other monitors too, ddcutil documents
`options nvidia NVreg_RegistryDwords=RMUseSwI2c=0x01;RMI2cSpeed=100` (it needs a reboot). It wasn't needed here.

## Permissions

`paperlike` needs read/write on `/dev/i2c-N`. Check with `ls -l /dev/i2c-*` (a `+` means a udev ACL for the
logged-in user). Otherwise add yourself to the `i2c` group and log in again.
