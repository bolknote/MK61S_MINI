#!/usr/bin/env python3
"""Pin the existing APP arena without holes or a second zero-init pass.

The pinned STM32 script normally places .data before .bss. Put .bss first,
with the overlay first inside it, then .noinit (inserted by the Core), .data
and the heap/stack reserve. The original startup still clears all BSS and
copies .data correctly. Fail closed if the upstream script changes shape.
"""
import argparse
import re
from pathlib import Path


def transform(source: str) -> str:
    match = re.search(r"  /\* Uninitialized data section.*?\n  \} >RAM\n",
                      source, re.S)
    if match is None or source.count("    *(.bss)\n") != 1:
        raise ValueError("unsupported STM32 BSS layout")
    bss = match.group().replace("  .bss :", "  .bss 0x20000000 (NOLOAD) :")
    bss = bss.replace("    *(.bss)\n",
                      "    KEEP(*(.bss.mk61_module_overlay))\n    *(.bss)\n")
    result = source[:match.start()] + source[match.end():]
    marker = '  /* Initialized data sections into "RAM" Ram type memory */'
    if result.count(marker) != 1:
        raise ValueError("unsupported STM32 data layout")
    result = result.replace(marker, bss + "\n" + marker)
    # Preserve generated resources in ELF only, excluded from the MCU image.
    result = result.replace("SECTIONS\n{", "SECTIONS\n{\n  .mk61_help 0 (INFO) : { KEEP(*(.mk61_help)) }")
    return result + '''
ASSERT(mk61_module_overlay == 0x20000000,
       "portable APP overlay address mismatch")
ASSERT(_sbss <= mk61_module_overlay && _ebss >= mk61_module_overlay + 20K,
       "portable APP overlay must be zeroed by startup")
ASSERT(_sdata >= _ebss && _edata <= _end && _end <= _estack,
       "portable APP startup/heap layout overlaps")
'''


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(transform(args.source.read_text()))
