#!/usr/bin/env python3
"""Extract C5 help resources from non-allocating resident ELF metadata."""
import argparse
import json
import struct
from pathlib import Path


def build(elf, output):
    data = elf.read_bytes()
    header = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    if header[0][:6] != b'\x7fELF\x01\x01' or header[2] != 40:
        raise ValueError('expected ARM ELF32')
    sections = [struct.unpack_from('<10I', data, header[6] + i * header[11])
                for i in range(header[12])]
    strings = sections[header[13]]
    names = data[strings[4]:strings[4] + strings[5]]
    matches = [s for s in sections if names[s[0]:names.index(0, s[0])] == b'.mk61_help']
    if len(matches) != 1 or matches[0][2] & 2:
        raise ValueError('missing non-allocating .mk61_help metadata; regenerate the portable linker script')
    section = matches[0]
    content = data[section[4]:section[4] + section[5]]
    if not content.endswith(b'\0') or b'\0' in content[:-1]:
        raise ValueError('invalid help metadata')
    content = content[:-1]
    content.decode('utf-8')
    if len(content) > 2800:
        raise ValueError('help exceeds two pages')
    checksum = 2166136261
    for byte in content:
        checksum = ((checksum ^ byte) * 16777619) & 0xffffffff
    tag = f'{checksum:08x}\n'.encode('ascii')
    split = min(1400, len(content))
    while split < len(content) and content[split] & 0xc0 == 0x80:
        split -= 1
    output.mkdir(parents=True, exist_ok=True)
    for page, part in enumerate((content[:split], content[split:])):
        (output / f'HELP{page}.TXT').write_bytes(tag + part)
    return {'bytes': len(content), 'tag': tag.decode().strip()}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.resident_elf, args.output_dir)))
