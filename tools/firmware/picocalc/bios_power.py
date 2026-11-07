"""Add power telemetry to our staged Southbridge BIOS; never opens a device."""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[3]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Southbridge power patch anchor changed: {old!r}")
    return text.replace(old, new, 1)


def stage_power_status(source):
    source = Path(source)
    src, inc = source / "Core/Src", source / "Core/Inc"
    # Validate all anchors before writing anything. Preserve runtime, UART,
    # I2C recovery and the existing PMU protection/settings implementation.
    regs = (inc / "regs.h").read_text()
    regs = replace_once(regs, "\tREG_ID_INT_CFG", "\tREG_ID_POWER_STATUS = 0x0F, // MK61 read-only power ABI1\n\n\tREG_ID_INT_CFG")
    i2c = (src / "i2cs.c").read_text()
    i2c = replace_once(i2c, "} else if (reg == REG_ID_BAT) {",
        "} else if (reg == REG_ID_POWER_STATUS) {\n"
        "\t\t\t\t\ti2cs_w_buff[1] = reg_get_value(REG_ID_POWER_STATUS);\n"
        "\t\t\t\t} else if (reg == REG_ID_BAT) {")
    main = (src / "main.c").read_text()
    main = replace_once(main, '#include "hal_interface.h"', '#include "hal_interface.h"\n#include "power_status.h"')
    main = replace_once(main, "\t// PICO MCU start", "\tbios_power_refresh(pmu_online);\n\n\t// PICO MCU start")
    main = replace_once(main, "\t\tcheck_pmu_int();", "\t\tcheck_pmu_int();\n\t\tbios_power_poll(pmu_online);")
    main = replace_once(main, "\t\tAXP2101_clearIrqStatus();",
        "\t\tAXP2101_clearIrqStatus();\n\t\tbios_power_refresh(pmu_online);")
    make = (source / "Makefile").read_text()
    make = replace_once(make, "Core/Src/main.c \\", "Core/Src/main.c \\\nCore/Src/power_status.c \\")
    for path, text in [(inc / "regs.h", regs), (src / "i2cs.c", i2c),
                       (src / "main.c", main), (source / "Makefile", make)]:
        path.write_text(text)
    for name in ("power_status.h", "power_status.c"):
        shutil.copyfile(ROOT / "ports/picocalc/bios" / name,
                        (inc if name.endswith(".h") else src) / name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="Fresh source staged by the Southbridge runtime builder")
    stage_power_status(parser.parse_args().source.resolve())
