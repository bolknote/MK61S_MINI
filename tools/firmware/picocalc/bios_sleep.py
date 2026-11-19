"""Stage retained-Pico M3 SLEEP: volatile tagged I2C request and bounded lease."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"M3 sleep source anchor changed: {old!r}")
    return text.replace(old, new, 1)

def stage_bios_sleep(source):
    source = Path(source)
    src, inc = source/'Core/Src', source/'Core/Inc'
    main = (src/'main.c').read_text()
    main = once(main, '#include "rtc_cache.h"', '#include "rtc_cache.h"\n#include "bios_sleep.h"')
    anchor = '\t\t}\n\t}\n}\n\n\n\n// Private functions'
    main = once(main, anchor,
        '\t\t}\n\t\tif (bios_sleep_requested())\n'
        '\t\t\tbios_sleep_poll(!pwr_off_active && !stop_mode_active && coproc_storage_idle());\n'
        '\t}\n}\n\n\n\n// Private functions')
    i2cs = (src/'i2cs.c').read_text()
    i2cs = once(i2cs, '#include "rtc_cache.h"', '#include "rtc_cache.h"\n#include "bios_sleep.h"')
    i2cs = once(i2cs, '} else if (reg == REG_ID_POWER_STATUS) {',
        '} else if (reg == BIOS_SLEEP_REG) {\n'
        '\t\t\t\t\tif (is_write) bios_sleep_write(i2cs_r_buff[1]);\n'
        '\t\t\t\t\ti2cs_w_buff[1] = bios_sleep_status();\n'
        '\t\t\t\t} else if (reg == REG_ID_POWER_STATUS) {')
    i2cs = once(i2cs, 'reg == REG_ID_OFF ||', 'reg == REG_ID_OFF ||\n\t\t\t\t\treg == BIOS_SLEEP_REG ||')
    make = once((source/'Makefile').read_text(), 'Core/Src/rtc_cache.c \\\n',
                'Core/Src/rtc_cache.c \\\nCore/Src/bios_sleep.c \\\n')
    for path, text in [(src/'main.c',main), (src/'i2cs.c',i2cs), (source/'Makefile',make)]:
        path.write_text(text)
    for name, target in [('bios_sleep.h',inc),('bios_sleep.c',src)]:
        shutil.copyfile(ROOT/'ports/picocalc/bios'/name,target/name)
    return {'retained_pico_sleep':True,'retained_pico_sleep_register':0x10,
            'retained_pico_sleep_lease_ms':2000,'retained_pico_sleep_mode':'SLEEP_WFI',
            'retained_pico_sleep_stops_pico':False}
