"""Stage F103 RTC second-flag snapshots; no new IRQ or sleep wake source."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"RTC cache source anchor changed: {old!r}")
    return text.replace(old, new, 1)


def stage_rtc_cache(source):
    source = Path(source)
    src, inc = source / "Core/Src", source / "Core/Inc"
    main = (src / "main.c").read_text()
    main = once(main, '#include "rtc.h"', '#include "rtc.h"\n#include "rtc_cache.h"')
    main = once(main, "\treg_init();", "\treg_init();\n\tbios_rtc_cache_init();")
    main = once(main,
        "\t\tHAL_RTC_GetDate(&hrtc, &rtc_date._s, RTC_FORMAT_BIN);\n"
        "\t\tHAL_RTC_GetTime(&hrtc, &rtc_time._s, RTC_FORMAT_BIN);",
        "\t\tbios_rtc_cache_poll();")

    i2cs = (src / "i2cs.c").read_text()
    i2cs = once(i2cs, '#include "rtc.h"', '#include "rtc.h"\n#include "rtc_cache.h"')
    for name in ["Date", "Time"]:
        call = f"HAL_RTC_Set{name}(&hrtc, &rtc_{name.lower()}._s, RTC_FORMAT_BIN);"
        i2cs = once(i2cs, call, call + "\n\t\t\t\t\t\tbios_rtc_cache_changed();")

    rtc = (src / "rtc.c").read_text()
    rtc = once(rtc, '#include "rtc.h"', '#include "rtc.h"\n#include "rtc_cache.h"')
    rtc = once(rtc, "\t\thrtc.DateToUpdate.WeekDay = bckDate._s.WeekDay;",
               "\t\thrtc.DateToUpdate.WeekDay = bckDate._s.WeekDay;\n"
               "\t\tbios_rtc_cache_changed();")
    rtc = once(rtc, "\t\tHAL_RTC_SetDate(&hrtc, &bckDate._s, RTC_FORMAT_BIN);",
               "\t\tHAL_RTC_SetDate(&hrtc, &bckDate._s, RTC_FORMAT_BIN);\n"
               "\t\tbios_rtc_cache_changed();")

    make = (source / "Makefile").read_text()
    make = once(make, "Core/Src/rtc.c \\", "Core/Src/rtc.c \\\nCore/Src/rtc_cache.c \\")
    # Validate all anchors before mutating any staged source.
    for path, text in [(src / "main.c", main), (src / "i2cs.c", i2cs),
                       (src / "rtc.c", rtc), (source / "Makefile", make)]:
        path.write_text(text)
    for name, target in [("rtc_cache.h", inc), ("rtc_cache.c", src)]:
        shutil.copyfile(ROOT / "ports/picocalc/bios" / name, target / name)
    return {"rtc_second_flag_cache": True, "rtc_added_interrupts": 0,
            "rtc_i2c_setters_invalidate": True, "rtc_calendar_restore_invalidates": True}
