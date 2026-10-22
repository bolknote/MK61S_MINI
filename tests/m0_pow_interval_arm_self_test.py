#!/usr/bin/env python3
"""Call production 512/1024-bit pow intervals with real memory and ROM code."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import struct

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from native_eabi_m0_arm_self_test import Machine, SP, bits
from m0_mpfr_oracle import Oracle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--bootrom',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=8)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    assert args.samples>=0
    machine=Machine(args.elf,True,stack_bytes=16384,instruction_budget=200000000,bootrom=args.bootrom)
    oracle=Oracle()
    rng=random.Random(0xF0512)
    pairs=[(rng.uniform(.05,10),rng.uniform(-30,30)) for _ in range(args.samples)]
    pairs += [(1.25,31./32),(1.25,-31./32),(float.fromhex('0x1p-1074'),.25),
              (2.,-1074.),(2.,-1075.),(1.-2.**-53,2.**60),(1.+2.**-52,2.**60),
              (81.,.75),(9.,17.),(float.fromhex('0x1.fffffffffffffp1023'),1.),
              (float.fromhex('0x1p-1022'),1.5),(2.**-215,5.)]
    pointer=SP-15000
    frame_lowest=[SP]
    def written(_uc,_access,address,size,_value,_user):
        if pointer<=address and address+size<=pointer+8:return
        if SP-machine.stack_bytes<=address<SP:frame_lowest[0]=min(frame_lowest[0],address)
    machine.uc.hook_add(UC_HOOK_MEM_WRITE,written)
    calls=Counter()
    def entered(_uc,_address,_size,name):calls[name]+=1
    for name in ('__wrap_memcpy','__wrap_memset','__wrap___clzdi2'):
        if name not in machine.elf.symbols:continue
        address=machine.elf.symbols[name]&~1
        machine.uc.hook_add(UC_HOOK_CODE,entered,name,begin=address,end=address)
    rows=[]
    for precision in (512,1024):
        symbol=f'_ZN15m0_pow_interval5FixedILj{precision}EE8evaluateEyyRy'
        assert symbol in machine.elf.symbols,symbol
        digest=hashlib.sha256()
        frame_lowest[0]=SP
        calls.clear()
        for x,y in pairs:
            a,b=bits(x),bits(y)
            expected=oracle.reference('pow',a,b)
            machine.uc.mem_write(pointer,struct.pack('<Q',0xBAD0BAD0BAD0BAD0))
            accepted=machine.call(symbol,a,b,c=pointer)[0]&255
            result=struct.unpack('<Q',machine.uc.mem_read(pointer,8))[0]
            assert accepted and result==expected,(precision,hex(a),hex(b),accepted,hex(result),hex(expected))
            digest.update(struct.pack('<4Q',a,b,result,expected))
        assert calls['__wrap_memcpy']+calls['__wrap_memset']>0,'Interval corpus never called linked memory code'
        row=dict(precision=precision,cases=len(pairs),wrong_rounding=0,
                 maximum_callee_frame_bytes=SP-frame_lowest[0],memory_and_bit_calls=dict(calls),
                 result_sha256=digest.hexdigest())
        rows.append(row)
        print('PASS',precision,'bits:',row,flush=True)
    assert rows[0]['result_sha256']==rows[1]['result_sha256']
    result=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
                bootrom_sha256=machine.bootrom_sha256,intrinsic_models=machine.rom_models,
                rows=rows,mpfr=oracle.version,
                scope='Direct calls to both unmodified production interval functions. Real linked memory wrappers and captured ROM execute; saved registers, SP and bounded writes are checked. Caller-owned output is excluded from callee-frame depth. Finite directed-MPFR RNE corpus, not a pow totality proof or a speed comparison.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
