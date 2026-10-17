"""Build the patched AULA F108 Pro firmware image from source (for developers).

    python build_firmware.py --stock stock_image.bin --out patched_image.bin

stock_image.bin is the RCDATA/4000 resource of the official updater (apply_patch.py can write
the raw patched image with --bin-out; a stock image can be saved with any resource extractor).
The ARM GNU toolchain (arm-none-eabi-gcc, ld, objcopy, nm) must be in PATH, or set ARM_GNU_BIN
to its bin folder. The result is byte-identical to what apply_patch.py produces from patch_data.json.

Patches (addresses come from the analysis of the official image):
  0x6600  FUN_00006600 -> zone_draw     arrow-bar zone: battery / stock / solid / breath / rainbow / off
  0x094C  BL FUN_0000E20C -> tick       1 kHz counter, then the original call
  0x0910  BL FUN_0000DDC2 -> render_all direct RGB mode skips the stock effects (+ NOPs 0x914..0x91B)
  0x091C  BL FUN_00010746 -> ui_tick    SIDE LIGHT / ARROWS menu pages
  0x2E84  knob press in volume mode: Mute -> Play/Pause
  0x4BC0  BL FUN_0000592A -> uart_hook  direct RGB over the 2.4G dongle
  0x1A28  ldr/movs -> BL rx_stub        USB SET_FEATURE hook for direct RGB over the cable

Optional FN macros (docs/09-fn-macros.md), only with --macros FILE:
  0x333A  BL FUN_00002D5C -> fn_hook    FN combinations that run lists of stock FN actions
Without --macros the output is the standard patch. --patch-out writes the result as a patch file for
apply_patch.py --patch (or, for the standard build, a new patch_data.json).
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

here = Path(__file__).parent
BASE = 0x1A600
CPU = ["-mcpu=cortex-m0", "-mthumb"]
CFLAGS = ["-Os", "-ffreestanding", "-nostdlib"]

ap = argparse.ArgumentParser()
ap.add_argument("--stock", required=True, help="stock firmware image (RCDATA/4000), 262144 bytes")
ap.add_argument("--out", default="patched_image.bin")
ap.add_argument("--macros", help="FN macros file (JSON), see docs/09-fn-macros.md")
ap.add_argument("--patch-out", help="also write the result as a patch file (format of patch_data.json)")
args = ap.parse_args()
BIN = os.environ.get("ARM_GNU_BIN", "")
stock = Path(args.stock).read_bytes()
assert len(stock) == 0x40000, "unexpected image size"


def run(exe, *a):
    exe = os.path.join(BIN, exe) if BIN else exe
    return subprocess.check_output([exe, *map(str, a)], text=True)


build = here / "_build"
build.mkdir(exist_ok=True)
sources = [("custom.c", CFLAGS), ("stub.S", [])]
if args.macros:
    sys.path.insert(0, str(here))
    import fn_macros_cfg
    try:
        macros = fn_macros_cfg.load(args.macros, stock)
    except fn_macros_cfg.MacroError as e:
        sys.exit("macros: %s" % e)
    (build / "fn_macros_cfg.h").write_text(fn_macros_cfg.header(macros, args.macros), encoding="utf-8")
    sources.append(("fn_macros.c", CFLAGS + ["-I", build]))
    for m in macros:
        if m["replaces_stock"]:
            print("note: %s replaces the stock action of this combination" % m["name"])
objs = []
for s, flags in sources:
    o = build / (s + ".o")
    run("arm-none-eabi-gcc", *CPU, *flags, "-c", here / s, "-o", o)
    objs.append(o)
run("arm-none-eabi-ld", "-T", here / "link.ld", *objs, "-o", build / "custom.elf")
run("arm-none-eabi-objcopy", "-O", "binary", build / "custom.elf", build / "custom.bin")
sym = {l.split()[2]: int(l.split()[0], 16) for l in run("arm-none-eabi-nm", build / "custom.elf").splitlines()}
code = (build / "custom.bin").read_bytes()

img = bytearray(stock)
assert all(b == 0xFF for b in img[BASE:BASE + len(code)]), "target area is not empty"
img[BASE:BASE + len(code)] = code


def bl(src, dst):  # Thumb-2 BL encoding
    off = dst - (src + 4)
    s = (off >> 24) & 1
    i1 = (off >> 23) & 1
    i2 = (off >> 22) & 1
    j1 = (~(i1 ^ s)) & 1
    j2 = (~(i2 ^ s)) & 1
    hi = 0xF000 | (s << 10) | ((off >> 12) & 0x3FF)
    lo = 0xD000 | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7FF)
    return struct.pack("<HH", hi, lo)


img[0x6600:0x6608] = struct.pack("<HHI", 0x4800, 0x4700, sym["zone_draw"] | 1)
assert img[0x94C:0x950] == bl(0x94C, 0xE20C), "unexpected code at 0x94C"
img[0x94C:0x950] = bl(0x94C, sym["tick"])
assert img[0x910:0x914] == bl(0x910, 0xDDC2) and img[0x914:0x918] == bl(0x914, 0xEA9C) and img[0x918:0x91C] == bl(0x918, 0x6882)
img[0x910:0x914] = bl(0x910, sym["render_all"])
img[0x914:0x91C] = struct.pack("<HHHH", 0xBF00, 0xBF00, 0xBF00, 0xBF00)
assert img[0x91C:0x920] == bl(0x91C, 0x10746), "unexpected code at 0x91C"
img[0x91C:0x920] = bl(0x91C, sym["ui_tick"])
assert img[0x2E84] == 0xE2 and img[0x2E85] == 0x21, "unexpected code at 0x2E84"
img[0x2E84] = 0xCD
assert img[0x4BC0:0x4BC4] == bl(0x4BC0, 0x592A), "unexpected code at 0x4BC0"
img[0x4BC0:0x4BC4] = bl(0x4BC0, sym["uart_hook"])
assert img[0x1A28:0x1A2C].hex() == "34490122", "unexpected code at 0x1A28"
img[0x1A28:0x1A2C] = bl(0x1A28, sym["rx_stub"])
if args.macros:
    assert img[0x333A:0x333E] == bl(0x333A, 0x2D5C), "unexpected code at 0x333A"
    img[0x333A:0x333E] = bl(0x333A, sym["fn_hook"])

Path(args.out).write_bytes(img)
print("OK: %s, code %d bytes%s" % (args.out, len(code), ", %d FN macros" % len(macros) if args.macros else ""))

if args.patch_out:
    ref = json.loads((here.parent / "patch_data.json").read_text(encoding="utf-8"))
    writes, i = [], 0
    while i < len(img):
        if img[i] != stock[i]:
            j = i
            while j < len(img) and img[j] != stock[j]:
                j += 1
            writes.append({"offset": i, "hex": img[i:j].hex()})
            i = j
        else:
            i += 1
    desc = ref["description"]
    if args.macros:
        desc = desc.replace("(RCDATA 4000).", "(RCDATA 4000) with the FN macros of %s." % Path(args.macros).name)
    patch = {"format": 1, "description": desc,
             "stock_image_sha256": hashlib.sha256(stock).hexdigest(), "stock_image_size": len(stock),
             "patched_image_sha256": hashlib.sha256(img).hexdigest(), "stock_exe_sha256": ref["stock_exe_sha256"],
             "writes": writes}
    with open(args.patch_out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(patch, indent=1, ensure_ascii=False))
    print("patch file: %s, %d runs" % (args.patch_out, len(writes)))
