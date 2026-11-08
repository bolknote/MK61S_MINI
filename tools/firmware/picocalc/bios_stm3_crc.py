"""Stage F103 hardware CRC32 and a matching host byte-table implementation."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[3]


def stage_stm3_crc(source):
    path = Path(source) / "Core/Src/stm3_runtime.c"
    text = path.read_text()
    old = "uint32_t stm3_crc32(const void*data,size_t n){const uint8_t*p=(const uint8_t*)data;uint32_t v=~0u;while(n--){v^=*p++;for(unsigned i=0;i<8;++i)v=(v>>1)^(0xedb88320u&(0u-(v&1)));}return ~v;}"
    table = []
    for byte in range(256):
        value = byte
        for _ in range(8):
            value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
        table.append(f"0x{value:08x}u")
    rows = [" " + ",".join(table[at:at+8]) for at in range(0,256,8)]
    software = ("uint32_t stm3_crc32(const void*data,size_t n){\n"
           " static uint32_t table[256]={\n" + ",\n".join(rows) + "\n };\n"
           " const uint8_t*p=(const uint8_t*)data;uint32_t v=~0u;\n"
           " while(n--)v=(v>>8)^table[(v^*p++)&255u];return ~v;\n}")
    new = ('#if defined(STM32F103xB)\n#include "stm3_crc_f103.h"\n'
           'uint32_t stm3_crc32(const void*data,size_t n){return stm3_f103_crc32(data,n);}\n'
           '#else\n'+software+'\n#endif')
    if text.count(old) != 1:
        raise ValueError("STM3 CRC source anchor changed")
    path.write_text(text.replace(old,new,1))
    # The staged Core tree is archived by the release builder as usual.
    header=Path(source)/'Core/Inc/stm3_crc_f103.h';header.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/'ports/picocalc/bios/stm3_crc_f103.h',header)
    return {"hardware_crc32": True, "hardware_crc_word_bytes": 4,
            "software_tail_max_bytes": 3,"host_byte_table_crc32": True}
