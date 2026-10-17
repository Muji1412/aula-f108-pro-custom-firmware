"""Emulator test for FN macros (docs/09-fn-macros.md).

    python fn_macros_test.py stock_image.bin patched_image.bin ../firmware/macros/pc-mac-toggle.json

For every macro and every connection / system mode it depends on, the patched image gets one press of the trigger, and
the stock image gets the real FN combinations of the chosen actions, one after another. Both go through the stock key
pipeline FUN_0000331A (the hook sits inside it), then the main loop runs. The keyboard state must end up the same.
It also checks that a macro's key is not sent to the host and that holding it does not start pairing.
Needs pip install unicorn capstone. The emulator has no radio or USB host, so it compares firmware state, not links.
"""
import sys
from pathlib import Path

here = Path(__file__).parent
sys.path.insert(0, str(here))
sys.path.insert(0, str(here.parent / "firmware" / "source"))
from emu import Emu                 # noqa: E402
import fn_macros_cfg as cfg         # noqa: E402

KEY, PIPELINE = 0x20000044, 0x331A
SYS, CONN, BT, WINLOCK, PAGE = 0x20000050, 0x200000E7, 0x200000E8, 0x20000053, 0x2000022E
REPORT, REPORT_LEN = 0x200000A1, 10     # keyboard report (key codes from 0x200000A3)
HOLD, PAIRING = 0x20000076, 0x20000107  # hold timer; 0x51 there = pairing started
SNAP = ((0x20000000, 0x10000), (0x40000000, 0x100000), (0xE0000000, 0x100000))
SYS_NAMES, CONN_NAMES = ("WIN", "MAC", "iOS", "Android"), ("wired", "BT", "2.4G")


class Keyboard:
    def __init__(self, image):
        e = Emu(image)
        e.reset()
        e.run(30_000_000)
        self.systick = int.from_bytes(e.image[15 * 4:16 * 4], "little") & ~1
        e.run_slices(300, 20000, systick=self.systick)
        self.e = e
        self.mem = [bytes(e.uc.mem_read(a, n)) for a, n in SNAP]
        self.ctx = e.uc.context_save()

    def rd(self, a, n=1):
        return int.from_bytes(self.e.uc.mem_read(a, n), "little")

    def wr(self, a, v):
        self.e.uc.mem_write(a, bytes([v]))

    def start(self, sys_mode, conn):
        for (a, _), data in zip(SNAP, self.mem):
            self.e.uc.mem_write(a, data)
        self.e.uc.context_restore(self.ctx)
        self.e._pending = None
        self.wr(SYS, sys_mode); self.wr(CONN, conn); self.wr(WINLOCK, 0x0F); self.wr(PAIRING, 0); self.wr(PAGE, 1)
        self.slices(50)

    def slices(self, n):
        self.e.run_slices(n, 20000, systick=self.systick)

    def key(self, usage, pressed, slices=150):
        self.wr(KEY + 5, usage); self.wr(KEY + 7, 1); self.wr(KEY + 8, pressed)   # FN held
        self.e.call_irq(PIPELINE, 2_000_000)
        self.slices(slices)

    def tap(self, usage):
        self.key(usage, 1)
        self.key(usage, 0)

    def report(self):
        return bytes(self.e.uc.mem_read(REPORT, REPORT_LEN))

    def state(self):
        return dict(system=self.rd(SYS), conn=self.rd(CONN), bt=self.rd(BT), winlock=self.rd(WINLOCK),
                    page=self.rd(PAGE), ff=self.rd(0x200000FF), e9=self.rd(0x200000E9), report=self.report().hex(),
                    side_light=bytes(self.e.uc.mem_read(0x20000192, 7)).hex())


def scenarios(m):
    if m["cond"] == 1:
        return [(s, c) for c in range(3) for s in (0, 1)]
    if m["cond"] == 2:
        return [(s, c) for s in range(4) for c in (0, 2)]
    return [(0, 0), (1, 2)]


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    stock_path, patched_path, macros_path = sys.argv[1:]
    image = Path(stock_path).read_bytes()
    macros = cfg.load(macros_path, image)
    by_code = {}
    for usage, code in sorted(cfg.fn_layer(image).items()):
        if code is not None:
            by_code.setdefault(code, usage)
    print("booting stock and patched images...")
    stock, patched = Keyboard(stock_path), Keyboard(patched_path)
    failed = 0
    for m in macros:
        print("\n%s" % m["name"])
        for n, (s, c) in enumerate(scenarios(m)):
            actions = m["then"] if not m["cond"] or (s if m["cond"] == 2 else c) == m["value"] else m["other"]
            label = "%-7s %-5s -> %s" % (SYS_NAMES[s], CONN_NAMES[c],
                                          " + ".join("%#04x" % a for a in actions) or "stock behaviour")
            keys = [by_code.get(a) for a in actions] if actions else [m["usage"]]
            if None in keys:
                print("  %s: skipped, an action has no FN key to replay on the stock image" % label)
                continue
            stock.start(s, c)
            for k in keys:
                stock.tap(k)
            patched.start(s, c)
            patched.key(m["usage"], 1)
            sent = actions and m["usage"] in patched.report()[2:]
            patched.key(m["usage"], 0)
            a, b = stock.state(), patched.state()
            ok = a == b and not sent
            print("  %s: %s" % (label, "same as stock" if ok else "DIFFERENT"))
            if not ok:
                failed += 1
                print("    stock   %s\n    patched %s%s" % (a, b, "\n    key was sent to the host" if sent else ""))
            if n == 0 and actions:
                patched.start(s, c)
                patched.key(m["usage"], 1, slices=10)
                after_press = patched.rd(CONN)
                for _ in range(60):
                    patched.slices(200)
                    if patched.rd(HOLD, 2) == 0:
                        break
                held_ok = patched.rd(HOLD, 2) == 0 and patched.rd(PAIRING) != 0x51 and patched.rd(CONN) == after_press
                print("  held down: %s" % ("no pairing, connection kept" if held_ok else "PROBLEM"))
                failed += not held_ok
    print("\n%s" % ("all checks passed" if not failed else "%d check(s) failed" % failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
