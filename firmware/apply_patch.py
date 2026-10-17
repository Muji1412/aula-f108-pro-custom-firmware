"""Apply the custom patch to the official AULA F108 Pro firmware updater.

The official updater (AULA_F108_Pro_Firmware.exe) carries the firmware image as resource
RCDATA/4000. This script reads that image from YOUR copy of the official file, checks that it is
exactly the version this patch was made for, applies the patch and writes a new updater exe
next to it. Nothing is downloaded and no official file is redistributed.

Usage (Windows, Python 3.8+):
    python apply_patch.py path\to\AULA_F108_Pro_Firmware.exe
    python apply_patch.py path\to\AULA_F108_Pro_Firmware.exe -o my_custom_updater.exe
    python apply_patch.py --from-bin stock_image.bin --bin-out patched_image.bin     (raw image, any OS)
    python apply_patch.py path\to\AULA_F108_Pro_Firmware.exe --patch macros\pc-mac-toggle.patch.json
"""
import argparse
import ctypes
import hashlib
import json
import shutil
import sys
from ctypes import wintypes as w
from pathlib import Path

HERE = Path(__file__).parent
RT_RCDATA, RES_ID = 10, 4000


def load_patch(path=None):
    return json.loads(Path(path or HERE / "patch_data.json").read_text(encoding="utf-8"))


def read_resource(exe):
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.LoadLibraryExW.restype = w.HMODULE
    k.LoadLibraryExW.argtypes = [w.LPCWSTR, w.HANDLE, w.DWORD]
    k.FindResourceW.restype = w.HANDLE
    k.FindResourceW.argtypes = [w.HMODULE, ctypes.c_void_p, ctypes.c_void_p]
    k.LoadResource.restype = w.HANDLE
    k.LoadResource.argtypes = [w.HMODULE, w.HANDLE]
    k.LockResource.restype = ctypes.c_void_p
    k.LockResource.argtypes = [w.HANDLE]
    k.SizeofResource.restype = w.DWORD
    k.SizeofResource.argtypes = [w.HMODULE, w.HANDLE]
    k.EnumResourceLanguagesW.argtypes = [w.HMODULE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    h = k.LoadLibraryExW(str(Path(exe).resolve()), None, 0x2)   # LOAD_LIBRARY_AS_DATAFILE
    if not h:
        sys.exit("cannot open %s as a PE file" % exe)
    res = k.FindResourceW(h, ctypes.c_void_p(RES_ID), ctypes.c_void_p(RT_RCDATA))
    if not res:
        sys.exit("resource RCDATA/%d not found: this is not the firmware updater" % RES_ID)
    size = k.SizeofResource(h, res)
    ptr = k.LockResource(k.LoadResource(h, res))
    data = ctypes.string_at(ptr, size)
    langs = []
    cb_t = ctypes.WINFUNCTYPE(w.BOOL, w.HMODULE, ctypes.c_void_p, ctypes.c_void_p, w.WORD, ctypes.c_void_p)
    k.EnumResourceLanguagesW(h, ctypes.c_void_p(RT_RCDATA), ctypes.c_void_p(RES_ID),
                             cb_t(lambda m, t, n, l, p: (langs.append(l), True)[1]), None)
    return data, (langs[0] if langs else 0)


def write_resource(exe, data, lang):
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.BeginUpdateResourceW.restype = w.HANDLE
    k.BeginUpdateResourceW.argtypes = [w.LPCWSTR, w.BOOL]
    k.UpdateResourceW.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, w.WORD, ctypes.c_void_p, w.DWORD]
    k.EndUpdateResourceW.argtypes = [w.HANDLE, w.BOOL]
    buf = ctypes.create_string_buffer(data, len(data))
    u = k.BeginUpdateResourceW(str(Path(exe).resolve()), False)
    if not u:
        sys.exit("cannot open %s for resource update (error %d)" % (exe, ctypes.get_last_error()))
    if not k.UpdateResourceW(u, ctypes.c_void_p(RT_RCDATA), ctypes.c_void_p(RES_ID), lang, buf, len(data)):
        sys.exit("UpdateResource failed (error %d)" % ctypes.get_last_error())
    if not k.EndUpdateResourceW(u, False):
        sys.exit("EndUpdateResource failed (error %d)" % ctypes.get_last_error())


def apply(image, patch):
    sha = hashlib.sha256(image).hexdigest()
    if sha != patch["stock_image_sha256"]:
        sys.exit("This is not the firmware image the patch was made for.\n  expected sha256 %s\n  found    %s\n"
                 "Use the official AULA_F108_Pro_Firmware.exe of the same version (see docs)." % (patch["stock_image_sha256"], sha))
    out = bytearray(image)
    for item in patch["writes"]:
        blob = bytes.fromhex(item["hex"])
        out[item["offset"]:item["offset"] + len(blob)] = blob
    if hashlib.sha256(out).hexdigest() != patch["patched_image_sha256"]:
        sys.exit("internal check failed: patched image hash differs")
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exe", nargs="?", help="official AULA_F108_Pro_Firmware.exe")
    ap.add_argument("-o", "--out", help="output updater exe (default: <name>_CUSTOM.exe next to the input)")
    ap.add_argument("--from-bin", help="read the stock image from a raw .bin instead of an exe")
    ap.add_argument("--bin-out", help="also (or only, with --from-bin) write the patched raw image")
    ap.add_argument("--patch", help="patch file to apply (default: patch_data.json), e.g. one made by build_firmware.py --patch-out")
    a = ap.parse_args()
    patch = load_patch(a.patch)

    if a.from_bin:
        image, lang = Path(a.from_bin).read_bytes(), 0
    elif a.exe:
        image, lang = read_resource(a.exe)
    else:
        ap.error("give the official exe or --from-bin")
    patched = apply(image, patch)
    print("stock image verified (sha256 %s...)" % patch["stock_image_sha256"][:16])

    if a.bin_out:
        Path(a.bin_out).write_bytes(patched)
        print("raw patched image written:", a.bin_out)
    if a.exe:
        out = Path(a.out) if a.out else Path(a.exe).with_name(Path(a.exe).stem + "_CUSTOM.exe")
        shutil.copyfile(a.exe, out)
        write_resource(out, patched, lang)
        check, _ = read_resource(out)
        if check != patched:
            sys.exit("written updater does not contain the patched image")
        print("custom updater written:", out)
        print("Next: connect the keyboard with the USB cable, run this exe and press Start.")


if __name__ == "__main__":
    main()
