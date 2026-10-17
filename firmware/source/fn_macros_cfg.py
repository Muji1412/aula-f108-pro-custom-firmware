"""FN macros: read a macros JSON file and generate the C table for fn_macros.c.

Used by build_firmware.py (--macros) and dev/fn_macros_test.py. Format and action names: docs/09-fn-macros.md.

    {
      "macros": [
        {"key": "FN+W", "if": {"connection": "wired"}, "then": ["MAC", "2.4G"], "else": ["WIN", "USB"]},
        {"key": "FN+M", "do": ["MAC", "BT1"]}
      ]
    }

Key names are resolved with the stock FN layer tables of the image, so "FN+<key>" means exactly what the keyboard does
for that combination.
"""
import json
import struct
from pathlib import Path

MAX_ACTIONS = 4                                     # FN_MACRO_LEN in fn_macros.c
# FN layer, one table per system mode (Windows, Mac, iOS, Android). Entry i is [code without FN, code with FN] for the key
# whose code is the first byte of entry i in the Windows table (FUN_000031B8 searches that one). Mac and iOS swap the F row.
FN_TABLES = (0x149F8, 0x14A44, 0x14ADC, 0x14A90)
FN_COUNT_AT = 0x6FFE                                # number of entries in each table (halfword)

ACTIONS = {
    "USB": 0xF4, "WIRED": 0xF4, "2.4G": 0xF6, "BT1": 0xEA, "BT2": 0xEB, "BT3": 0xEC,
    "WIN": 0xDD, "WINDOWS": 0xDD, "MAC": 0xDF, "IOS": 0xDE, "ANDROID": 0xDC,
}
CONNECTION_CODES = {0xF4, 0xF6, 0xEA, 0xEB, 0xEC}
CONDITIONS = {
    "connection": (1, {"wired": 0, "usb": 0, "bluetooth": 1, "bt": 1, "2.4g": 2}),
    "system": (2, {"windows": 0, "win": 0, "mac": 1, "ios": 2, "android": 3}),
}


def _hid_names():
    names = {}
    for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        names[c] = 0x04 + i
    for i, c in enumerate("1234567890"):
        names[c] = 0x1E + i
    for i in range(12):
        names["F%d" % (i + 1)] = 0x3A + i
    names.update({
        "ENTER": 0x28, "ESC": 0x29, "BACKSPACE": 0x2A, "TAB": 0x2B, "SPACE": 0x2C,
        "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31, ";": 0x33, "'": 0x34, "`": 0x35, "GRAVE": 0x35,
        ",": 0x36, ".": 0x37, "/": 0x38, "CAPSLOCK": 0x39,
        "PRINTSCREEN": 0x46, "SCROLLLOCK": 0x47, "PAUSE": 0x48, "INSERT": 0x49, "HOME": 0x4A, "PAGEUP": 0x4B,
        "DELETE": 0x4C, "END": 0x4D, "PAGEDOWN": 0x4E, "RIGHT": 0x4F, "LEFT": 0x50, "DOWN": 0x51, "UP": 0x52,
        "NUMLOCK": 0x53, "KP/": 0x54, "KP*": 0x55, "KP-": 0x56, "KP+": 0x57, "KPENTER": 0x58, "KP.": 0x63,
        "MENU": 0x65,
        "LCTRL": 0xE0, "LSHIFT": 0xE1, "LALT": 0xE2, "LWIN": 0xE3, "RCTRL": 0xE4, "RSHIFT": 0xE5, "RALT": 0xE6,
        "RWIN": 0xE7,
        "KNOB": 0x98,                               # knob press (vendor code)
    })
    for i in range(1, 10):
        names["KP%d" % i] = 0x58 + i
    names["KP0"] = 0x62
    return names


HID = _hid_names()


class MacroError(Exception):
    pass


def fn_layer(image):
    """{HID usage: code sent with FN held}; None for a key whose FN code differs between system modes"""
    n = struct.unpack_from("<H", image, FN_COUNT_AT)[0]
    layer = {}
    for i in range(n):
        codes = {image[t + 2 * i + 1] for t in FN_TABLES}
        layer[image[FN_TABLES[0] + 2 * i]] = codes.pop() if len(codes) == 1 else None
    return layer


def _usage(name, where):
    s = str(name).strip()
    if not s.upper().startswith("FN+"):
        raise MacroError("%s: %r must look like FN+<key>" % (where, name))
    k = s[3:].strip()
    usage = HID.get(k.upper(), HID.get(k))
    if usage is None:
        raise MacroError("%s: unknown key %r (see docs/09-fn-macros.md)" % (where, k))
    return usage


def _action(name, layer, where):
    s = str(name).strip()
    if s.upper() in ACTIONS:
        return ACTIONS[s.upper()]
    if s.lower().startswith("0x"):
        code = int(s, 16)
        if not 0 < code < 0x100:
            raise MacroError("%s: action code %s out of range" % (where, s))
        return code
    usage = _usage(s, where)
    code = layer.get(usage)
    if code is None:
        raise MacroError("%s: %s has no stock FN action that is the same in every system mode" % (where, s))
    return code


def _actions(items, layer, where):
    if items is None:
        return []
    if not isinstance(items, list):
        raise MacroError("%s: expected a list of actions" % where)
    codes = [_action(x, layer, where) for x in items]
    if len(codes) > MAX_ACTIONS:
        raise MacroError("%s: at most %d actions" % (where, MAX_ACTIONS))
    conn = [i for i, c in enumerate(codes) if c in CONNECTION_CODES]
    if len(conn) > 1 or (conn and conn[0] != len(codes) - 1):
        # wired switching finishes later through the screen state machine (page 8), anything after it could disturb that
        raise MacroError("%s: only one connection action, and it must be the last one" % where)
    return codes


def load(path, image):
    """parse a macros file against a stock image -> list of macros (dicts)"""
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise MacroError("%s: %s" % (path, e))
    items = cfg.get("macros") if isinstance(cfg, dict) else None
    if not items:
        raise MacroError("%s: no \"macros\" list" % path)
    layer = fn_layer(image)
    out, seen = [], set()
    for n, m in enumerate(items, 1):
        where = "macro %d (%s)" % (n, m.get("key", "?"))
        usage = _usage(m.get("key", ""), where)
        if usage in layer and layer[usage] is None:
            raise MacroError("%s: this key's FN action differs between system modes, it cannot be a trigger" % where)
        key, need_fn = (layer[usage], 0) if usage in layer else (usage, 1)
        if (key, need_fn) in seen:
            raise MacroError("%s: key used twice" % where)
        seen.add((key, need_fn))

        cond, value = 0, 0
        if m.get("if"):
            if not isinstance(m["if"], dict) or len(m["if"]) != 1:
                raise MacroError("%s: \"if\" takes one of %s" % (where, ", ".join(CONDITIONS)))
            (what, val), = m["if"].items()
            if what not in CONDITIONS or str(val).lower() not in CONDITIONS[what][1]:
                raise MacroError("%s: bad condition %s=%r" % (where, what, val))
            cond, value = CONDITIONS[what][0], CONDITIONS[what][1][str(val).lower()]
        then = _actions(m.get("then", m.get("do")), layer, where)
        other = _actions(m.get("else"), layer, where)
        if not then and not other:
            raise MacroError("%s: no actions" % where)
        if not cond and other:
            raise MacroError("%s: \"else\" needs \"if\"" % where)
        out.append(dict(name=str(m["key"]).strip(), usage=usage, key=key, need_fn=need_fn, cond=cond, value=value,
                        then=then, other=other, replaces_stock=usage in layer))
    return out


def header(macros, source):
    """C table for fn_macros.c"""
    pad = lambda a: ", ".join("0x%02X" % c for c in a + [0] * (MAX_ACTIONS - len(a)))
    lines = ["/* generated by build_firmware.py from %s, do not edit */" % Path(source).name,
             "#define N_FN_MACROS %d" % len(macros),
             "static const struct fn_macro fn_macros[N_FN_MACROS] = {"]
    for m in macros:
        lines.append("    { 0x%02X, %d, %d, %d, { %s }, { %s } },   /* %s */"
                     % (m["key"], m["need_fn"], m["cond"], m["value"], pad(m["then"]), pad(m["other"]), m["name"]))
    lines.append("};")
    return "\n".join(lines) + "\n"
