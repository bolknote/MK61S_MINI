#!/usr/bin/env python3
"""Exercise real RP2040 ROM intrinsics and the math emulator's write guards."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

from unicorn import UC_HOOK_CODE
from native_eabi_m0_arm_self_test import Machine, SP


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--bootrom',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    machine=Machine(args.elf,True,stack_bytes=8192,bootrom=args.bootrom)
    assert not machine.rom_models and machine.rom_initializers and machine.calls==0
    trace=Counter()
    def instruction(_uc,address,_size,_user):
        trace['rom' if address<0x4000 else 'sram' if 0x20000000<=address<0x20042000 else 'flash']+=1
    hook=machine.uc.hook_add(UC_HOOK_CODE,instruction)
    results=[]
    rng=random.Random(0xB007C12)
    if '__wrap___clzdi2' in machine.elf.symbols:
        inputs=set([0,(1<<64)-1]+[value for bit in range(64) for value in ((1<<bit)-1,1<<bit)])
        inputs.update(rng.getrandbits(64) for _ in range(128))
        trace.clear()
        for value in sorted(inputs):
            got=machine.call('__wrap___clzdi2',value)[0]&0xffffffff
            assert got==64-value.bit_length(),(hex(value),got)
        assert trace['rom']>0,'CLZ never entered actual ROM'
        results.append(dict(name='__wrap___clzdi2',cases=len(inputs),instruction_regions=dict(trace)))
    sizes=[*range(34),63,64,65,127,128,129,255,256,257,511]
    source,destination=SP-6144,SP-2048
    trace.clear()
    copies=0
    for size in sizes:
        for source_offset in range(4):
            for destination_offset in range(4):
                original=bytes(rng.randrange(256) for _ in range(size+48))
                machine.uc.mem_write(source-16,original)
                machine.uc.mem_write(destination-16,b'\x5a'*(size+48))
                pointer=destination+destination_offset
                got=machine.call('__wrap_memcpy',pointer|((source+source_offset)<<32),size)[0]&0xffffffff
                assert got==pointer,'memcpy return value'
                expected=(b'\x5a'*(16+destination_offset)+
                          original[16+source_offset:16+source_offset+size]+
                          b'\x5a'*(32-destination_offset))
                assert bytes(machine.uc.mem_read(destination-16,size+48))==expected,(size,source_offset,destination_offset)
                assert bytes(machine.uc.mem_read(source-16,size+48))==original,'Source modified'
                copies+=1
    results.append(dict(name='__wrap_memcpy',cases=copies,instruction_regions=dict(trace)))
    trace.clear()
    fills=0
    for size in sizes:
        for offset in range(4):
            for value in (0,0xa5,0x1234,0xffffffff):
                machine.uc.mem_write(destination-16,b'\x5a'*(size+48))
                pointer=destination+offset
                got=machine.call('__wrap_memset',pointer|(value<<32),size)[0]&0xffffffff
                assert got==pointer,'memset return value'
                expected=b'\x5a'*(16+offset)+bytes([value&255])*size+b'\x5a'*(32-offset)
                assert bytes(machine.uc.mem_read(destination-16,size+48))==expected,(size,offset,value)
                fills+=1
    assert trace['rom']>0,'memset never entered actual ROM'
    results.append(dict(name='__wrap_memset',cases=fills,instruction_regions=dict(trace)))
    machine.uc.hook_del(hook)
    assert machine.rom_init_write_ranges==[],'Initializer write permission leaked into ordinary calls'
    table=machine.elf.symbols['aeabi_mem_funcs']
    try:
        machine.call('__wrap_memset',table|(0xa5<<32),4)
    except AssertionError as error:
        assert error.args[0][0]=='non-stack write',error
    else:
        raise AssertionError('An ordinary memory call overwrote the ROM pointer table')
    result=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
                bootrom_sha256=machine.bootrom_sha256,initializers=machine.rom_initializers,
                intrinsic_models=machine.rom_models,results=results,
                ordinary_global_writes_rejected=True,maximum_observed_stack_bytes=SP-machine.stack_lowest,
                scope='Real SDK ROM lookup and bit/memory instructions, pointer alignment, byte canaries, ABI and stack/global write protection. Emulator diagnostics, not hardware cycles.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
