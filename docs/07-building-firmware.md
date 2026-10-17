# 7. Building the firmware patch from source

You normally do not need this: `firmware/apply_patch.py` applies the ready-made patch. Build from source if you want to
change the patch.

## Tools

- ARM GNU Toolchain (arm-none-eabi-gcc, ld, objcopy, nm), tested with 12.2.
- Python 3.8+.
- The stock firmware image as a file (`stock_image.bin`, 262144 bytes): the RCDATA/4000 resource of the official updater.
  You can save it with any resource extractor, or with a few lines using `read_resource` from `firmware/apply_patch.py`.

## Build

```
set PATH=C:\path\to\arm-gnu-toolchain\bin;%PATH%
python firmware\source\build_firmware.py --stock stock_image.bin --out patched_image.bin
```

The script compiles `custom.c` and `stub.S`, links at 0x1A600 with `link.ld`, writes the code into the free area and patches
the call sites after checking that they contain what is expected. The output must be byte-identical to
what `apply_patch.py` produces (compare the SHA-256 with `patched_image_sha256` in `patch_data.json`).

To make a new `patch_data.json` after you change something, add `--patch-out firmware\patch_data.json`: it diffs the stock
and patched images and writes the changed byte runs as `{"offset": ..., "hex": ...}` records with the two new SHA-256 values,
so only your own bytes end up in it. For the unchanged source it reproduces the committed `patch_data.json` exactly.

With `--macros my_macros.json` the build also compiles `fn_macros.c` with the macro table and hooks 0x333A, see
[09-fn-macros.md](09-fn-macros.md). That code is linked after the rest, so the other functions keep their addresses.

## Test before flashing

`dev/` has a Unicorn based emulator of the SN32F290 (`emu.py`), an LCD model (`lcd.py`), a disassembler helper (`fwdis.py`) and an
example UI test (`ui_test3.py`). They need `pip install unicorn capstone pillow`, and a stock image named `stock_image.bin` in the
working directory. The emulator runs the real image up to the main loop, feeds knob events into the UI queue and saves screenshots
and LED buffers. It is not exact hardware, for example GPIO reads return zeros, so use it to catch crashes and layout errors, not as proof that
everything works.

Rules that cost the author time:

- Cortex-M0 has no divide instruction: avoid `/` and `%` on variables, use shifts and compares.
- Feed the watchdog during long drawing.
- Do not use UI page number 0xE.
- Test every change in the emulator, then on the keyboard.
