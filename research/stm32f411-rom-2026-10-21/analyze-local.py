#!/usr/bin/env python3
"""Check the two local n>=16 candidates before executing them on hardware."""
import hashlib
import argparse
import json
from pathlib import Path
import random
import subprocess
from analyze import Machine, SP, HERE, ROOT
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS

TC = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=('style','edges','loop'))
    args=parser.parse_args()
    report = []
    for suffix, symbol in [('style', 'local_bulk_style'), ('edges', 'local_bulk_edges'), ('loop','local_bulk_edges_loop')]:
        if args.variant and args.variant!=suffix: continue
        build = ROOT / f'.build/stm32f411-rom-20261021/benchmark-local-{suffix}'
        symbols = subprocess.check_output([TC/'arm-none-eabi-nm', '-S', build/'ROMBEN.elf'], text=True)
        row = next(line.split() for line in symbols.splitlines() if line.endswith(' '+symbol))
        address, size = int(row[0], 16), int(row[1], 16)
        raw = (build/'ROMBEN.bin').read_bytes()[address-0x20000000:address-0x20000000+size]
        assert len(raw) == size
        (HERE/f'{symbol}.bin').write_bytes(raw)
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        (HERE/f'{symbol}.S').write_text('\n'.join(
            f'{i.address:08x}: {i.bytes.hex():10s} {i.mnemonic:8s} {i.op_str}'
            for i in md.disasm(raw, address))+'\n')
        m = Machine()
        entry = 0x08001000
        m.uc.mem_write(entry, raw)  # Both candidates contain no PC-relative references.
        rng = random.Random(0x61411)
        cases = [(n,a,v) for n in range(16,257) for a in range(8) for v in (0,1,165,255)]
        cases += [(rng.randrange(16,8193),rng.randrange(32),rng.getrandbits(32)) for _ in range(5000)]
        for n, align, value in cases:
            dest = 0x20004000+align
            m.uc.mem_write(0x20000000, b'\x5A'*0x20000)
            result = m.call(entry, dest, value, n)
            assert result == dest, (symbol,'return',n,align,value)
            expected = bytearray(b'\x5A'*0x20000)
            expected[dest-0x20000000:dest-0x20000000+n] = bytes([value&255])*n
            actual = bytearray(m.uc.mem_read(0x20000000,0x20000))
            expected[SP-0x20000000-8:SP-0x20000000] = actual[SP-0x20000000-8:SP-0x20000000]
            assert actual == expected, (symbol,'bounds/content',n,align,value)
        report.append({'symbol':symbol,'bytes':size,'sha256':hashlib.sha256(raw).hexdigest(),
                       'cases':len(cases),'status':'PASS','contract':'n >= 16, ordinary writable memory',
                       'checks':'whole SRAM except 8 stack bytes; return pointer; callee-saved registers'})
        print(json.dumps(report[-1]),flush=True)
    output=HERE/'local-validation.json'
    if args.variant and output.exists():
        report=[r for r in json.loads(output.read_text()) if r['symbol']!=report[0]['symbol']]+report
    output.write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
