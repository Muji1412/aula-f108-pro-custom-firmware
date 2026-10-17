# 6. Technical notes: hardware, firmware patch and protocols

For people who want to write their own software or understand what the patch does. Everything here was found by
analysing the official firmware image and by experiments on the author's unit. No official source code is included.

## Hardware

- MCU Sonix SN32F290 (Cortex-M0, no hardware divide, 256 KB flash image, RAM at 0x20000000).
- LCD 240x135 (ST7789 class) on SPI0, external SPI flash on SPI1 holding GIFs and menu images.
- Wired: USB 0C45:800A. 2.4G dongle: USB 05AC:024F.
- 147 LED slots. Three 16-bit planes (R, G, B) in RAM at 0x20001842, 0x20001968, 0x20001A8E; the stock renderers fill them, the LED
  driver reads them. Direct mode writes these planes.

## Firmware patch (all addresses are in the official image)

| Address | Original | Patched |
|---|---|---|
| 0x6600 | `FUN_00006600` zone renderer | jumps to `zone_draw` (battery, stock, solid, breath, rainbow, off) |
| 0x094C | `BL FUN_0000E20C` | `BL tick`, a 1 kHz tick counter, then the original |
| 0x0910 | `BL FUN_0000DDC2` (+0x914, 0x918 other renderers) | `BL render_all`: skips the stock renderers while direct mode is active |
| 0x091C | `BL FUN_00010746` (UI event processing) | `BL ui_tick`: handles the custom menu page, otherwise calls the original |
| 0x2E84 | `movs r1,#0xE2` (Mute) | `movs r1,#0xCD` (Play/Pause) |
| 0x4BC0 | `BL FUN_0000592A` (UART command dispatcher) | `BL uart_hook` (direct RGB over the dongle) |
| 0x1A28 | `ldr r1,=0x20000040; movs r2,#1` in the USB handler | `BL rx_stub` (direct RGB over the cable) |
| 0x333A | `BL FUN_00002D5C` (FN connection / system mode / knob keys) | only with FN macros: `BL fn_hook`, see [09-fn-macros.md](09-fn-macros.md) |
| 0x1A600+ | free space (0xFF) | the new code, about 4.5 KB |

RAM used by the patch: 0x200001F8..0x200001FD, 0x200001FE, 0x20000202, 0x20000203 (direct-mode flag, stamp, tick, menu state, ARROWS
settings). They were unused in all tested paths.

The stock firmware feeds the watchdog (write 0x5AFA55AA to 0x4001000C) once per main loop pass; the menu drawing code feeds it
itself because drawing takes long.

## Menu pages

The UI is a state machine: page number in 0x2000022E, event queue at 0x20002129 (events 8 and 9 are knob turns, 0xC is a press).
The patch uses page 0x20 for both custom pages. Page 0xE must not be used: the stock main loop treats it as a key matrix test.

## Wired direct RGB protocol

HID feature report on interface 3 (usage page 0xFF13), report id 0, 64 bytes payload. Packet:

```
b[0..3] = 'R','G','B','D'
b[4]    = first LED index
b[5]    = LED count (max 18)
b[6]    = flags (0x80 = release direct mode)
b[8..]  = R,G,B for each LED
```

A frame is 147 LEDs = 9 packets. The keyboard stays in direct mode while packets keep arriving; after about 1.3 s of silence it
returns to stock lighting. The arrow zone has red and green swapped.

## Dongle direct RGB protocol

HID output report (65 bytes with report id 0) to the vendor interface 3 (usage page 0xFF60), checksum in byte 32:

```
b[1] = 0x40
b[2] = first LED index
b[3] = LED count (max 8)
b[4] = flags (0x80 = release)
b[7..] = R,G,B per LED
b[32] = (sum of all other bytes) & 0xFF
```

The dongle forwards the packet over the radio link as a UART frame to the keyboard MCU. Measured throughput: about 100 to 125 packets per
second without loss, round trip about 14 ms.

## Stock vendor protocol (partially known)

Same transport as above, 33 useful bytes, byte 1 is the command, byte 32 the checksum. Known: 0x20 reads the battery (2.4G),
0x0C time sync, 0x07 settings, 0x03/0x0D/0x05 lighting modes, 0x10/0x12 per-key colors. Command 0x1F makes the keyboard reboot into
the bootloader and must never be sent by accident.
