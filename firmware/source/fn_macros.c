/* FN macros (optional, built only with build_firmware.py --macros FILE, see docs/09-fn-macros.md).
 *
 * A macro is an FN combination that runs a short list of stock FN actions, optionally chosen by the current connection or
 * system mode. Example: FN+W -> when wired: Mac mode + 2.4G, otherwise: Windows mode + wired.
 *
 * Hook: 0x333A, the only call of FUN_00002D5C (stock FN special keys: connection, system mode, knob mode).
 * Key event at 0x20000044: [5] key code after the FN layer (tables 0x149F8..), [7] FN held, [8] 1 pressed / 0 released.
 * An action is a stock FN code. It goes through the same handlers as a real key press does at 0x333A..0x3346:
 * FUN_00002D5C, then FUN_000028C4 when the first one passes the code on. Saving, LED feedback, the screen and the radio
 * are therefore handled by stock code exactly as for the real combinations.
 * When the hold timer (0x20000076, main loop 0x6F0) runs out it reads the key code again and starts 2.4G or Bluetooth
 * pairing for those codes, so the trigger's own code is put back after the actions.
 */
#define U8(a)  (*(volatile unsigned char *)(a))
#define U16(a) (*(volatile unsigned short *)(a))

#define KEY          0x20000044
#define CONN_MODE    0x200000E7             /* 0 wired, 1 Bluetooth, 2 2.4G */
#define SYS_MODE     0x20000050             /* 0 Windows, 1 Mac, 2 iOS, 3 Android */
#define FN_MACRO_LEN 4

#define fn_special() ((int (*)(void))0x2D5D)()      /* FUN_00002D5C */
#define fn_other()   ((void (*)(void))0x28C5)()     /* FUN_000028C4 */

struct fn_macro {
    unsigned char key;                      /* code as it reaches FUN_00002D5C */
    unsigned char need_fn;                  /* key without a stock FN code: match only while FN is held */
    unsigned char cond;                     /* 0 none, 1 connection mode == value, 2 system mode == value */
    unsigned char value;
    unsigned char then_[FN_MACRO_LEN];      /* 0-terminated; an empty list keeps the stock behaviour */
    unsigned char else_[FN_MACRO_LEN];
};

#include "fn_macros_cfg.h"                  /* generated: fn_macros[], N_FN_MACROS */

static void run(unsigned code)
{
    U8(KEY + 5) = code;
    if (fn_special()) {
        U16(KEY + 0x32) = 0;
        fn_other();
    }
}

int fn_hook(void)
{
    unsigned code = U8(KEY + 5);
    const struct fn_macro *m = fn_macros;
    const unsigned char *a;

    for (unsigned i = 0; i < N_FN_MACROS; i++, m++) {
        if (m->key != code || (m->need_fn && !U8(KEY + 7)))
            continue;
        if (!U8(KEY + 8))
            break;                          /* release: stock handling, it also stops the hold timer */
        a = m->then_;
        if (m->cond && U8(m->cond == 1 ? CONN_MODE : SYS_MODE) != m->value)
            a = m->else_;
        if (!a[0])
            break;
        for (unsigned k = 0; k < FN_MACRO_LEN && a[k]; k++)
            run(a[k]);
        U8(KEY + 5) = code;
        return 0;                           /* consumed: the key is not sent to the host */
    }
    return fn_special();
}
