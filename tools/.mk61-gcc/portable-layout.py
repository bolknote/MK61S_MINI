#!/usr/bin/env python3
"""Export the free SRAM interval without allocating an APP array or section.

Keep the Core's .data/.bss/.noinit/startup layout. APP, staging and newlib
share [_end, stack guard); the existing MPU stack budgets remain unchanged.
"""
import argparse
import re
from pathlib import Path


def transform(source: str) -> str:
    if (source.count("SECTIONS\n{") != 1 or
            not re.search(r'PROVIDE\s*\(\s*_end\s*=\s*\.\s*\)', source) or
            source.count("    *(.bss)\n") != 1):
        raise ValueError("unsupported STM32 startup/heap layout")
    # Preserve generated resources in ELF only, excluded from the MCU image.
    result = source.replace("SECTIONS\n{", "SECTIONS\n{\n  .mk61_help 0 (INFO) : { KEEP(*(.mk61_help)) }")
    return result + '''
__mk61_dynamic_begin = ALIGN(_end, 8);
__mk61_dynamic_end = ORIGIN(RAM) + LENGTH(RAM)
                    - (LENGTH(RAM) == 64K ? 6K : 16K) - 256;
ASSERT(LENGTH(RAM) == 64K || LENGTH(RAM) == 128K,
       "portable APP requires an F401/F411 SRAM profile")
ASSERT(_edata <= _sbss && _ebss <= _end &&
       __mk61_dynamic_begin <= __mk61_dynamic_end,
       "portable APP static data overlaps the stack guard")
ASSERT(!DEFINED(mk61_module_overlay),
       "portable APP must not reserve a fixed SRAM overlay")
'''


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(transform(args.source.read_text()))
