"""Stage the async PMU owner on an already patched, archived Southbridge tree."""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[3]


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Async PMU source anchor changed: {old!r}")
    return text.replace(old, new, 1)


def stage_async_pmu(source):
    source = Path(source)
    src, inc = source / "Core/Src", source / "Core/Inc"
    main = (src / "main.c").read_text()
    main = once(main, '#include "power_status.h"', '#include "power_status.h"\n#include "pmu_async.h"')
    main = once(main, "\t\tcheck_pmu_int();\n\t\tbios_power_poll(pmu_online);",
        "\t\tbios_power_poll(pmu_online);\n\t\tif (bios_pmu_legacy_ready()) {\n"
        "\t\t\tcheck_pmu_int();\n\t\t\tbios_pmu_legacy_complete();\n\t\t}")
    main, count = re.subn(r"reg_set_value\(REG_ID_BAT,\s*", "bios_power_legacy_battery(", main)
    if count != 6:
        raise ValueError(f"Expected six legacy battery publishers, got {count}")
    # USB-only/absent batteries must not leave pcnt uninitialized. Keep IRQ,
    # low-battery protection and button handling in the original functions.
    main = main.replace("\tuint8_t pcnt;", "\tuint8_t pcnt = 0xFF;")
    main = once(main, "\t// Backlights shut-off", "\tbios_pmu_quiesce();\n\n\t// Backlights shut-off")
    main = once(main, "__STATIC_INLINE void sys_wake_sleep(void) {",
                "__STATIC_INLINE void sys_wake_sleep(void) {\n\tbios_pmu_resume();")
    axp = (src / "axp2101.c").read_text()
    axp = once(axp, '#include "axp2101.h"', '#include "axp2101.h"\n#include "pmu_async.h"')
    reads, writes = axp.count("HAL_I2C_Mem_Read("), axp.count("HAL_I2C_Mem_Write(")
    if reads < 10 or writes < 10:
        raise ValueError("Missing legacy AXP HAL call sites")
    axp = axp.replace("HAL_I2C_Mem_Read(", "bios_pmu_mem_read(")
    axp = axp.replace("HAL_I2C_Mem_Write(", "bios_pmu_mem_write(")
    axp += '\nvoid bios_pmu_sync_irq_masks(void) {\n' \
           '\tfor (unsigned i=0;i<3;++i)\n' \
           '\t\t(void)bios_pmu_mem_read(&hi2c2,0x68,(uint16_t)(0x40+i),1,&intRegister[i],1,0);\n' \
           '}\n'
    # All anchors were checked before mutating the staged tree.
    (src / "main.c").write_text(main)
    (src / "axp2101.c").write_text(axp)
    shutil.copyfile(ROOT / "ports/picocalc/bios/pmu_async.c", src / "power_status.c")
    shutil.copyfile(ROOT / "ports/picocalc/bios/pmu_async.h", inc / "pmu_async.h")
    return {"legacy_read_sites": reads, "legacy_write_sites": writes, "legacy_publishers": count}
