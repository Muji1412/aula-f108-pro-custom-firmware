# 9. FN macros: your own FN combinations

An FN macro makes one FN combination run a short list of stock FN actions, optionally chosen by the current connection or
system mode. Typical use: one key to move the keyboard between computers.

```
FN+W   wired -> Mac mode + 2.4G dongle      2.4G or Bluetooth -> Windows mode + wired
```

Macros are optional. Without a macros file the build and `patch_data.json` are exactly the standard patch.

## Ready-made: PC / Mac toggle

For a Windows PC on the cable and a Mac on the 2.4G dongle. No toolchain needed:

```
python firmware\apply_patch.py path\to\AULA_F108_Pro_Firmware.exe --patch firmware\macros\pc-mac-toggle.patch.json
```

Flash the `_CUSTOM.exe` as described in [01-flashing.md](01-flashing.md). It contains the standard patch plus the macro.
The source of that patch file is [firmware/macros/pc-mac-toggle.json](../firmware/macros/pc-mac-toggle.json).

## Stock FN combinations (not in the manual)

The stock firmware already has these, the macros reuse them:

| Keys | Action |
|---|---|
| FN+4 | wired (USB) |
| FN+\` | 2.4G dongle (hold: pair the dongle) |
| FN+1 / FN+2 / FN+3 | Bluetooth 1 / 2 / 3 (hold: pair) |
| FN+W / FN+E / FN+R / FN+Q | system mode Windows / Mac / iOS / Android |
| FN+B | battery level on the LEDs |
| FN+knob press | knob: volume / menu mode |
| FN+RShift, FN+/, FN+RAlt | side light effect, color, brightness |

## Writing a macros file

```json
{
 "macros": [
  {"key": "FN+W", "if": {"connection": "wired"}, "then": ["MAC", "2.4G"], "else": ["WIN", "USB"]},
  {"key": "FN+J", "do": ["WIN", "USB"]},
  {"key": "FN+K", "if": {"system": "mac"}, "then": ["WIN"]}
 ]
}
```

- `key`: the trigger, `FN+<key>`. Letters, digits, `F1`..`F12`, `ESC`, `TAB`, `SPACE`, `ENTER`, `BACKSPACE`, punctuation
  (`` ` - = [ ] \ ; ' , . / ``), `UP` `DOWN` `LEFT` `RIGHT`, `INSERT` `DELETE` `HOME` `END` `PAGEUP` `PAGEDOWN`,
  `PRINTSCREEN` `SCROLLLOCK` `PAUSE`, `NUMLOCK` `KP0`..`KP9` `KP/` `KP*` `KP-` `KP+` `KPENTER` `KP.`, `MENU`,
  `LCTRL` `LSHIFT` `LALT` `LWIN` `RCTRL` `RSHIFT` `RALT` `RWIN`, `KNOB`.
  - A key with a stock FN action (table above) gets the macro instead of that action; the build prints a note.
  - A key without one (FN+J, FN+M, ...) is caught only while FN is held. Its letter is not sent to the computer.
  - Keys whose FN action differs between system modes cannot be triggers (F1..F12, LCtrl, LWin).
- `do` (or `then`): up to 4 actions, run in order.
- `if` (optional): `{"connection": "wired" | "bluetooth" | "2.4g"}` or `{"system": "windows" | "mac" | "ios" | "android"}`.
  `then` runs when it matches, `else` otherwise. An empty or missing `else` keeps the key's stock behaviour in that case.
- Actions:
  - `USB` (or `WIRED`), `2.4G`, `BT1`, `BT2`, `BT3`
  - `WIN` (or `WINDOWS`), `MAC`, `IOS`, `ANDROID`
  - `FN+<key>`: whatever that stock combination does, if it is the same in every system mode (for example `FN+B`,
    `FN+RSHIFT`)
  - a raw stock FN code such as `"0xDB"`, for experiments
- At most one connection action per list, and it must be the last one. Switching to wired finishes later through the
  screen state machine, and anything after it could disturb that. The build refuses files that break a rule.

## Building

```
set ARM_GNU_BIN=C:\path\to\arm-gnu-toolchain\bin
python firmware\source\build_firmware.py --stock stock_image.bin --macros my_macros.json --out patched_image.bin --patch-out my_macros.patch.json
python firmware\apply_patch.py path\to\AULA_F108_Pro_Firmware.exe --patch my_macros.patch.json
```

`--patch-out` writes the same kind of file as `patch_data.json` (only the changed bytes, both SHA-256 values), so
`apply_patch.py --patch` checks the stock image and the result exactly as it does for the standard patch.
See [07-building-firmware.md](07-building-firmware.md) for the toolchain and the stock image.

## Testing in the emulator

```
cd dev
python fn_macros_test.py stock_image.bin patched_image.bin ..\firmware\macros\my_macros.json
```

For every macro and every connection or system mode it depends on, the test presses the trigger once on the patched image
and the real FN combinations of the chosen actions one after another on the stock image. Both go through the stock key
pipeline, and the keyboard state must end up the same: system mode, connection, Bluetooth channel, screen page, key report,
side light settings. It also checks that the trigger's key is not sent and that holding the trigger does not start pairing.
The emulator has no radio or USB host, so try the result on the keyboard as well.

## How it works

- Hook at 0x333A, the only call of `FUN_00002D5C`, the stock handler for FN connection, system mode and knob keys.
  The key event is at 0x20000044: `[5]` key code after the FN layer, `[7]` FN held, `[8]` pressed / released.
- FN layer: one table per system mode at 0x149F8 (Windows), 0x14A44 (Mac), 0x14ADC (iOS), 0x14A90 (Android), 38 entries
  (count at 0x6FFE). Entry *i* is [code without FN, code with FN] for the key that is the first byte of entry *i* in the
  Windows table. Mac and iOS swap the F row, which is why F keys cannot be triggers or actions.
- Each action is put into `[5]` and sent through the same two stock handlers a real key press goes through:
  `FUN_00002D5C`, then `FUN_000028C4` (lighting FN keys) when the first one passes the code on. Saving, LED feedback, the
  screen and the radio are stock code.
- After the actions the trigger's code is written back to `[5]`. The hold timer (0x20000076, checked in the main loop at
  0x6F0) reads that byte when it runs out and starts 2.4G or Bluetooth pairing for those codes.
- Key events arrive only when a key changes (scan loop 0x3838), so holding a trigger runs the macro once.
- Releases go to the stock handler, which also stops the hold timer.
- Useful state: connection mode 0x200000E7 (0 wired, 1 Bluetooth, 2 2.4G), Bluetooth channel mask 0x200000E8, system mode
  0x20000050 (0 Windows, 1 Mac, 2 iOS, 3 Android). The stock settings code (`FUN_0000E13E`) saves all three to flash.

## Limits

- Only stock FN actions. No text or key-sequence macros (the keyboard report is not touched).
- A macro build is tied to the same stock image as the rest of the patch.
- Changing macros needs a rebuild and a flash. There is no runtime configuration.
