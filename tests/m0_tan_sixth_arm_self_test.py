#!/usr/bin/env python3
"""Check the rare ARM Q70 sixth-term refinement against rational intervals."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from generate_m0_trig_table import interval
from native_eabi_m0_arm_self_test import Machine


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();machine=Machine(args.elf,True)
    # No compiler-specific scalarized clone ABI is assumed by this test.
    assert 'checked_trig_tan_sixth' in machine.elf.symbols
    name=next(n for n in machine.elf.symbols if 'trig_tan_table' in n and machine.elf.sizes.get(n)==806*32)
    table=machine.elf.symbols[name];deltas={0,(1<<59)+128}
    for g in range(0,257,16):
        centers=[g<<51]
        if g<256:centers.append((g<<51)+(1<<50))
        for center in centers:
            deltas.update(v for v in (center-1,center,center+1) if 0<=v<=(1<<59)+128)
    factors={v:F(v**6,1<<350) for v in deltas};largest=F(0);digest=hashlib.sha256()
    def coefficient(t):return (17*t+77*t**3+105*t**5+45*t**7)/45
    for row in range(806):
        sl,sh=interval(F(row,1024),False);cl,ch=interval(F(row,1024),True)
        lower,upper=coefficient(sl/ch),coefficient(sh/cl)
        for delta in sorted(deltas):
            lo,hi=lower*factors[delta],upper*factors[delta]
            for h in ((delta,-delta) if delta else (0,)):
                argument=h&((1<<64)-1)
                got=machine.call('checked_trig_tan_sixth',table+row*32,argument)[0]&0xFFFFFFFF
                error=max(abs(got-lo),abs(got-hi))
                assert error<4,(row,h,got,float(error))
                largest=max(largest,error)
                digest.update(struct.pack('<IQQ',row,argument,got))
    report=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        actual_arm_calls=machine.calls,maximum_observed_absolute_error_q70=float(largest),
        certified_bound_q70=4,sha256=digest.hexdigest(),
        scope='All 806 table cells; both signs, Q8 rounding transitions, zero and maximum residual. Independent rational sin/cos enclosures supply the exact sixth coefficient. Every call verifies R4-R11/SP and bounded writes.')
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
