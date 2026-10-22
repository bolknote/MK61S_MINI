#!/usr/bin/env python3
"""Require instruction counts to survive uncounted calls and cached SRAM code."""
import argparse
import hashlib
import json
from pathlib import Path

from native_eabi_m0_arm_self_test import Machine, bits


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--bootrom',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    samples=[('_ZN12compact_math3powEdd',bits(52.5),bits(8.)),
             ('_ZN12compact_math3powEdd',bits(1.3),bits(7.)),
             ('_ZN12compact_math3tanEd',bits(.7),0),
             ('_ZN12compact_math4sqrtEd',bits(2.),0),
             ('__aeabi_dmul',bits(.7),bits(1.3)),
             ('__aeabi_ddiv',bits(.7),bits(1.3)),
             ('__aeabi_f2d',0x3fa00000,0)]
    rows=[]
    for symbol,a,b in samples:
        machine=Machine(args.elf,True,stack_bytes=16384,bootrom=args.bootrom)
        result,_,fresh=machine.call(symbol,a,b,count=True)
        assert fresh>0,(symbol,'fresh count',fresh)
        for _ in range(4):
            assert machine.call(symbol,a,b)[0]==result
        counts=[]
        for _ in range(3):
            got,_,count=machine.call(symbol,a,b,count=True)
            assert got==result
            assert count==fresh,(symbol,'count changed after uncounted execution',fresh,count)
            counts.append(count)
            machine.call(symbol,a,b)
        rows.append(dict(symbol=symbol,a=f'{a:016X}',b=f'{b:016X}',fresh=fresh,mixed=counts))
    report=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
                bootrom_sha256=machine.bootrom_sha256,results=rows,
                scope='Actual ROM/flash/SRAM code; mixed counted and uncounted calls must have the same nonzero instruction count as a fresh machine. This guards emulator instrumentation, not hardware timing.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
