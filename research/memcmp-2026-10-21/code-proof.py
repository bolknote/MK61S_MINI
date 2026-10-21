#!/usr/bin/env python3
"""Compare measured memcmp bodies with full resident links and runtime slot 25."""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / '.build/memcmp-20261021')
    parser.add_argument('--m4-app', type=Path, required=True)
    parser.add_argument('--m4-flash', type=Path, required=True)
    parser.add_argument('--m0-app', type=Path)
    parser.add_argument('--m0-flash', type=Path)
    parser.add_argument('--m0-shared', type=Path)
    parser.add_argument('--m0-shared-body', default='own64')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    assert args.m0_app or not (args.m0_flash or args.m0_shared)
    items = [('m4_flash', args.m4_flash, 'memcmp'),
             ('m4_sram_candidate', args.m4_flash, 'own_low64'),
             ('m4_app', args.m4_app, 'memcmp'),
             ('f411', args.work / 'classic-build/resident.elf', 'memcmp'),
             ('f401', args.work / 'f401-build/resident.elf', 'memcmp')]
    if args.m0_app:
        items += [('pico', args.work / 'pico-build/mk61s-picocalc-pico-h.elf', '__wrap_memcmp'),
                  ('m0_app', args.m0_app, 'memcmp')]
    if args.m0_shared:
        items.append(('m0_shared_target', args.m0_shared, args.m0_shared_body))
    if args.m0_flash:
        items.append(('m0_flash', args.m0_flash, 'memcmp'))
    proof = {}
    baseline_proof = {row['cpu']: row for row in
                      json.loads((args.work / 'baseline-proof/result.json').read_text())}
    for tag, path, name in items:
        image = ElfImage(path)
        raw = path.read_bytes()

        def read(address, size):
            section = next(s for s in image.sections if s[1] != 8 and
                           s[3] <= address and address + size <= s[3] + s[5])
            offset = section[4] + address - section[3]
            return raw[offset:offset + size]

        address, size = image.symbols[name] & ~1, image.sizes[name]
        proof[tag] = dict(address=hex(address | 1), bytes=size,
                          code_sha256=hashlib.sha256(read(address, size)).hexdigest(),
                          elf_sha256=hashlib.sha256(raw).hexdigest())
        if tag in ('m4_app', 'm0_app'):
            baseline = read(image.symbols['baseline'] & ~1, image.sizes['baseline'])
            digest = hashlib.sha256(baseline).hexdigest()
            cpu = 'cortex-m4' if tag == 'm4_app' else 'cortex-m0plus'
            assert digest == baseline_proof[cpu]['code_sha256'], (tag, 'baseline differs')
            proof[tag]['baseline_code_sha256'] = digest
        if tag in ('f411', 'f401', 'pico'):
            runtime = ('_ZN8picocalc14native_runtimeE' if tag == 'pico' else
                       '_ZN15loadable_module12_GLOBAL__N_1L7runtimeE')
            pointer = struct.unpack('<I', read(image.symbols[runtime] + 25 * 4, 4))[0]
            assert pointer == address | 1, (tag, hex(pointer), hex(address))
            proof[tag]['runtime_slot_25'] = hex(pointer)
    families = [('m4_flash', 'f411', 'f401'), ('m4_app', 'm4_sram_candidate')]
    if args.m0_app:
        families.append(('pico', 'm0_app'))
    if args.m0_shared:
        families[2] += ('m0_shared_target',)
    if args.m0_flash:
        families[2] += ('m0_flash',)
    for family in families:
        assert len({proof[tag]['code_sha256'] for tag in family}) == 1, family
    sources = ['code/memory_compare_arm.h', 'code/memcmp_m4.inc', 'code/memcmp_m4_flash.inc',
               'sdk/portable/memory.c', 'code/system_memory.c']
    if args.m0_app:
        sources += ['code/memcmp_m0.inc', 'ports/picocalc/memory.c']
    proof['sources'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    proof['status'] = 'PASS'
    (args.output or args.work / 'code-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    print('Measured and resident bodies identical in each selected family; runtime slot 25 PASS')


if __name__ == '__main__':
    main()
