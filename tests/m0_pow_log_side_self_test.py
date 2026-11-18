#!/usr/bin/env python3
"""Check the 16384-bit logarithm comparison against directed MPFR."""
import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import random
import shlex
import subprocess
import sys

from m0_mpfr_oracle import Oracle, bits, real

ROOT = Path(__file__).resolve().parents[1]
ONE, INF = bits(1.), bits(math.inf)
DIRECT = 'm0_pow_log_side12_GLOBAL__N_1L4sideEyyy'
POWER = 'PowerBoundsILj512EE4sideE'
FINAL = 'mk61_m0_pow_round_final'
STREAM = 'm0_pow_stream12_GLOBAL__N_14sideEyyy'
TIE = (bits(2.), bits(-1075.), 0)


def cases(oracle, random_count):
    chosen = (
        (0x3ff2345678abcdef,bits(.5)),
        (1,bits(-.36)),
        (3,bits(.99999)),
        (0x7fefffffffffffff,bits(1.0000000000000002)),
        (ONE-(1<<26),bits(.271827291)),
        (ONE+(1<<25),bits(-.499999996)),
        (0x000fffffffffffff,0x3bffffffffffffff),
        (0x7fefffffffffffff,0xbbffffffffffffff),
    )
    rng = random.Random(0x8c0da)
    for i in range(random_count):
        x = rng.randrange(1, INF) if i%4 else ONE+rng.randrange(-(1<<26),1<<25)
        y = bits(rng.uniform(-1.5, 1.5)) if i%3 else (
            rng.getrandbits(52) | ((1023-rng.randrange(1,65))<<52) | (rng.getrandbits(1)<<63))
        chosen += ((x,y),)
    for x,y in chosen:
        rounded = oracle.reference('pow',x,y)
        for lower in (rounded-1, rounded):
            if 0 <= lower < INF:
                yield x,y,lower,(-1 if rounded<=lower else 1)


def host(args, oracle):
    args.output.mkdir(parents=True,exist_ok=True)
    library = args.output/('log_side.dylib' if sys.platform=='darwin' else 'log_side.so')
    deps = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','mpfr','gmp'],text=True))
    subprocess.run([args.cxx,'-O3','-std=c++17','-fPIC','-Wall','-Wextra','-Wno-unused-function',
                    '-dynamiclib' if sys.platform=='darwin' else '-shared','-I'+str(ROOT/'code'),
                    str(ROOT/'tests/fixtures/m0_pow_log_side_host.cpp'),*deps,'-o',str(library)],check=True)
    lib = ctypes.CDLL(str(library.resolve()))
    lib.log_side.argtypes = [ctypes.c_uint64]*3
    lib.log_side.restype = ctypes.c_int
    lib.logarithm_error.argtypes = [ctypes.c_uint64,ctypes.c_int]
    lib.logarithm_error.restype = ctypes.c_uint

    rng = random.Random(0x1483)
    logs = [(1,0),(1,-1075),(1,1023),((1<<54)-1,970),((1<<53)-1,-53),
            ((1<<52)+1,-52),((1<<53)-1,-1075),((1<<52)+1,-1075),(3,-1075)]
    for i in range(512):
        width = rng.randrange(1,55) if i%2 else 54
        normalized_exponent = (-1,0,rng.randrange(-1022,1024))[i%3]
        logs.append(((1 << (width-1)) | rng.getrandbits(width-1),normalized_exponent-width+1))
    maximum = max(lib.logarithm_error(a,e) for a,e in logs)
    assert maximum < 364835, maximum
    total = 0
    for x,y,lower,expected in cases(oracle,512):
        got = lib.log_side(x,y,lower)
        assert got==expected,(hex(x),hex(y),hex(lower),got,expected)
        total += 1
    assert lib.log_side(*TIE)==0
    assert lib.log_side(bits(float(3**32)),bits(17/16),bits(float(3**34-1)))==0
    assert not lib.log_side(0,ONE,ONE) and not lib.log_side(ONE,INF,ONE)
    return dict(status='PASS',mpfr=oracle.version,directed_log_enclosures=len(logs),
                maximum_log_error_units=maximum,non_tie_comparisons=total,exact_ties=2)


def arm_tests(args, oracle):
    from native_eabi_m0_arm_self_test import Machine, SP, signed
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0

    arm = Machine(args.elf,True,bootrom=args.bootrom,stack_bytes=22000,instruction_budget=300_000_000)
    def symbol(fragment):
        name, = (name for name in arm.elf.symbols if fragment in name)
        return name

    entries = {}
    def count(_uc, _pc, _size, name):
        entries[name] = entries.get(name,0)+1

    def return_now(uc, _pc, _size, _name):
        count(uc,0,0,'watchdog')
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))

    for name, fragment, callback in (
            ('log',DIRECT,count),('stream',STREAM,count),
            ('watchdog','diagnostics13feed_watchdogEv',return_now)):
        address = arm.elf.symbols[symbol(fragment)] & ~1
        arm.uc.hook_add(UC_HOOK_CODE,callback,name,begin=address,end=address)
    arm.uc.ctl_flush_tb()
    report = []
    for i,(x,y,lower,expected) in enumerate(cases(oracle,0)):
        if i%2 or len(report)>=5:
            continue
        entries.clear()
        arm.stack_lowest = SP
        got,_,_ = arm.call(symbol(DIRECT),x,y,c=lower)
        assert signed(got&0xffffffff,32)==expected and entries.get('log')==1
        report.append(dict(x=f'{x:016x}',y=f'{y:016x}',lower=f'{lower:016x}',
                           expected=expected,stack_bytes=SP-arm.stack_lowest,stages=entries.copy()))
        print('PASS direct',report[-1],flush=True)

    def force_overlap(uc, _pc, _size, _name):
        count(uc,0,0,'forced_8192')
        uc.reg_write(UC_ARM_REG_R0,0)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))

    address = arm.elf.symbols[symbol(POWER)] & ~1
    arm.uc.hook_add(UC_HOOK_CODE,force_overlap,begin=address,end=address)
    arm.uc.ctl_flush_tb()
    routes = []
    first = report[0]
    for x,y,lower in (tuple(int(first[key],16) for key in ('x','y','lower')),TIE):
        entries.clear()
        arm.stack_lowest = SP
        rounded = oracle.reference('pow',x,y)
        assert arm.call(FINAL,x,y,c=lower)[0]==rounded
        assert entries['forced_8192']==entries['log']==1
        assert entries.get('stream',0)==int((x,y,lower)==TIE)
        routes.append(dict(x=f'{x:016x}',y=f'{y:016x}',lower=f'{lower:016x}',
                           rounded=f'{rounded:016x}',stages=entries.copy(),stack_bytes=SP-arm.stack_lowest))
        print('PASS route',routes[-1],flush=True)
    return dict(status='PASS',mpfr=oracle.version,bootrom_sha256=arm.bootrom_sha256,
                elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),direct=report,
                forced_routes=routes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cxx',default='c++')
    parser.add_argument('--elf',type=Path)
    parser.add_argument('--bootrom',type=Path)
    args = parser.parse_args()
    if bool(args.elf)!=bool(args.bootrom):
        parser.error('--elf and --bootrom are required together')
    oracle = Oracle()
    data = arm_tests(args,oracle) if args.elf else host(args,oracle)
    file = args.output/('arm.json' if args.elf else 'host.json')
    file.write_text(json.dumps(data,indent=2)+'\n')
    print(data)


if __name__ == '__main__':
    main()
