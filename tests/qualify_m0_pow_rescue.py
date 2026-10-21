#!/usr/bin/env python3
"""Exercise the owned pow rescue from an actual forced ARM caller."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tests')]
from build_picocalc import compiler_bin
import native_eabi_m0_arm_self_test as arm
from m0_mpfr_oracle import Oracle


def build(snapshot,output,force1024):
    stage=output/'source';stage.mkdir(parents=True,exist_ok=True)
    for directory in ('code','third_party/core_math'):
        shutil.copytree(snapshot/directory,stage/directory,dirs_exist_ok=True)
    (stage/'tests/fixtures').mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'tests/fixtures/m0_cr_memory.c',stage/'tests/fixtures/m0_cr_memory.c')
    path=stage/'third_party/core_math/pow/pow.c';source=path.read_text()
    patches={
        'if (__builtin_expect (res_min == res_max, 1)) {':'if (false && __builtin_expect (res_min == res_max, 1)) {',
        'if (rd)\n    // dint_tod':'if (rd && R.ex > 1023)\n    // dint_tod',
        'if (exact_pow (&e, x0, y, &R, exact))':'if (false && exact_pow (&e, x0, y, &R, exact))',
        '  if (rd)\n  {\n    qZ.sgn':'  if (false && rd)\n  {\n    qZ.sgn',
    }
    for old,new in patches.items():
        assert source.count(old)==1,('Inspect upstream before changing test-only patches',old)
        source=source.replace(old,new)
    path.write_text(source)
    if force1024:
        path=stage/'code/native_eabi_m0_cr.cpp';source=path.read_text()
        old='m0_pow_interval::Fixed<512>::evaluate(a,b,result)';assert source.count(old)==1
        path.write_text(source.replace(old,'(false && '+old+')'))
    arm.ROOT=stage.resolve()
    elf=arm.build(compiler_bin(None),(output/'arm').resolve(),True)
    return elf,dict(patches=patches,force1024=force1024)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--snapshot',type=Path)
    source.add_argument('--elf',type=Path,help='Previously built test-only forced-rescue ELF')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--samples',type=int,default=16)
    p.add_argument('--force-1024',action='store_true')
    a=p.parse_args();assert a.samples>=0;a.output.mkdir(parents=True,exist_ok=True)
    elf,patch=build(a.snapshot.resolve(),a.output.resolve(),a.force_1024) if a.snapshot else (a.elf,{})
    sha=hashlib.sha256(elf.read_bytes()).hexdigest()
    machine=arm.Machine(elf,True,stack_bytes=16384,instruction_budget=200000000);oracle=Oracle()
    address=machine.elf.symbols['mk61_m0_pow_rescue']&~1;hits=[0]
    def entered(*unused):hits[0]+=1
    machine.uc.hook_add(arm.UC_HOOK_CODE,entered,begin=address,end=address)
    rng=random.Random(0xF0512)
    pairs=[(rng.uniform(.05,10),rng.uniform(-30,30)) for _ in range(a.samples)]
    pairs += [(x,y) for x in (-1.25,-2.,-9.) for y in (3.,-3.,17.,33.)]
    pairs += [(9.,17.),(81.,.75),(2.,-1074.),(-2.,-1073.),(-2.,-1075.),
              (float.fromhex('0x1p-1074'),.25),(1.-2.**-53,2.**60)]
    digest=hashlib.sha256()
    for i,(x,y) in enumerate(pairs):
        a_bits,b_bits=arm.bits(x),arm.bits(y);expected=oracle.reference('pow',a_bits,b_bits)
        actual=machine.call('_ZN12compact_math3powEdd',a_bits,b_bits)[0]
        assert actual==expected,(i,x,y,hex(actual),hex(expected))
        digest.update(struct.pack('<4Q',a_bits,b_bits,actual,expected))
        print('PASS',i+1,'/',len(pairs),'rescue calls',hits[0],flush=True)
    assert hits[0]>=max(1,a.samples),hits
    assert sha==hashlib.sha256(elf.read_bytes()).hexdigest()
    report=dict(status='PASS_TEST_ONLY',cases=len(pairs),wrong_rounding=0,rescue_calls=hits[0],
        force1024=a.force_1024,maximum_stack_bytes=arm.SP-machine.stack_lowest,
        allowed_stack_bytes=machine.stack_bytes,instruction_budget_per_call=machine.instruction_budget,
        elf_sha256=sha,sha256=digest.hexdigest(),source_patch=patch,mpfr=oracle.version,
        scope='Private copy forces all three rounding tests to fail and bypasses exact_pow. Checks real ARM call/return, result sign, exact midpoints, subnormals and bounded caller stack. Not an all-input totality proof.')
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
