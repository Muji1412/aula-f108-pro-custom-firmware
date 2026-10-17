# AULA F108 Pro custom firmware, OpenRGB support and on-screen light menu

Unofficial. Not affiliated with or endorsed by AULA or Sonix. "AULA" is a trademark of its owner.
Русская версия: [README.ru.md](README.ru.md)

This project patches the firmware of the AULA F108 Pro keyboard (Sonix SN32F290 MCU, 240x135 LCD, rotary knob)
and provides an OpenRGB controller for it.

> **Fork of [Fitertom/aula-f108-pro-custom-firmware](https://github.com/Fitertom/aula-f108-pro-custom-firmware)** that adds
> optional **FN macros**: your own FN combinations that run stock actions, e.g. FN+W to move the keyboard between a wired
> Windows PC and a Mac on the 2.4G dongle. See [docs/09-fn-macros.md](docs/09-fn-macros.md). Without a macros file
> everything below is unchanged.

## What you get

- Battery level on the LED zone above the arrow keys: a red-to-green gradient that blinks below 20 percent.
- New on-screen menu pages, reached by turning the knob:
  - SIDE LIGHT: effect, color, speed and brightness of the two side light strips (four circles on one screen).
  - ARROWS: mode (battery, stock behaviour, solid color, breathing, rainbow, off), color, speed, brightness of the
    zone above the arrow keys.
- In the knob's FN volume mode, pressing the knob sends Play/Pause (it sent Mute before).
- Direct RGB control of all LEDs (keys, arrow zone, both side strips) from the PC, over the USB cable and over the
  2.4G dongle. The colors live in RAM only, so no flash memory is written and nothing wears out.
- An OpenRGB controller that uses this mode (wired and 2.4G).
- Optional FN macros: one FN combination runs a list of stock actions (connection, system mode, lighting), optionally
  depending on the current connection or system mode. Ready-made: FN+W toggles wired + Windows / 2.4G + Mac.

Everything else works as before: the stock effects, FN combinations, the clock, GIFs, the driver software.

## What it needs

- AULA F108 Pro (USB 0C45:800A when wired, dongle 05AC:024F). Other models are not supported.
- The official firmware updater `AULA_F108_Pro_Firmware.exe` from the manufacturer, exactly the version this patch was made
  for (the patcher checks it and refuses anything else). Reference SHA-256 values are in `firmware/patch_data.json`.
- Windows for flashing (the official updater is a Windows program). OpenRGB parts can be built for other systems, see the docs.
- Python 3.8 or newer for the patcher and the Python tools.

## Quick start

1. Download the official `AULA_F108_Pro_Firmware.exe` from the manufacturer.
2. Run `python firmware/apply_patch.py path\to\AULA_F108_Pro_Firmware.exe`. It writes `AULA_F108_Pro_Firmware_CUSTOM.exe` next to it.
3. Connect the keyboard with the USB cable, run the new exe, press Start, wait for "Update successfully".
4. Use the menu, see [docs/02-menu.md](docs/02-menu.md).
5. For OpenRGB see [docs/03-openrgb.md](docs/03-openrgb.md).

Detailed steps: [docs/01-flashing.md](docs/01-flashing.md). How it was made and what was found: [docs/08-research-log.md](docs/08-research-log.md). If something goes wrong: [docs/05-recovery.md](docs/05-recovery.md).

## Contents

| Path | What it is |
|---|---|
| `firmware/apply_patch.py`, `firmware/patch_data.json` | Patcher. Contains only the bytes written by this project, no official code. |
| `firmware/source/` | C and assembly source of the patch and the build script (for developers). |
| `firmware/macros/` | FN macro examples and ready-made patch files for `apply_patch.py --patch`. |
| `openrgb/` | OpenRGB controller source (GPL-2.0-or-later, same as OpenRGB) and install helper scripts. |
| `tools/` | Python tools: direct RGB over cable and dongle, a small RGB studio, battery reader. |
| `dev/` | Firmware emulator (Unicorn) and helper scripts used for testing before flashing. |
| `docs/`, `docs_ru/` | Documentation in English and Russian. |

No official firmware, updater, driver or image is included in this repository, and none should be added.

## Risks

Flashing a keyboard always carries a risk. The author flashed several builds on one unit without trouble, but cannot
test other units. Use a cable, do not unplug during flashing, read [docs/05-recovery.md](docs/05-recovery.md) first.
You may lose your warranty. Everything is provided as is, without warranty of any kind, you use it at your own risk.

## License

Source code of this project: MIT, see `LICENSE`. The OpenRGB controller in `openrgb/Controllers` is GPL-2.0-or-later
to match OpenRGB. The official firmware and software belong to their owners and are not covered by this license.
