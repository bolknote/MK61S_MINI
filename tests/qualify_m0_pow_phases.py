#!/usr/bin/env python3
"""Exercise the otherwise almost unreachable 128/256-bit ARM pow paths.

Only a test copy changes its branch choices. exact_pow keeps its original
precondition: it is called only when the original 128-bit rounding test was
ambiguous. For resolved cases we force the 256-bit calculation directly.
No production approximation, coefficient or final interval test is changed.
"""
import argparse
import hashlib
import json
import math
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
from unicorn import UC_HOOK_CODE


def build(snapshot,out):
    stage=out/'source';stage.mkdir(parents=True,exist_ok=True)
    for directory in ('code','third_party/core_math'):
        shutil.copytree(snapshot/directory,stage/directory,dirs_exist_ok=True)
    (stage/'tests/fixtures').mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'tests/fixtures/m0_cr_memory.c',stage/'tests/fixtures/m0_cr_memory.c')
    path=stage/'third_party/core_math/pow/pow.c';original=path.read_bytes();source=original.decode()
    patches={
      'if (__builtin_expect (res_min == res_max, 1)) {':'if (false && __builtin_expect (res_min == res_max, 1)) {',
      'if (rd)\n    // dint_tod':'if (rd && R.ex > 1023)\n    // dint_tod',
      'if (exact_pow (&e, x0, y, &R, exact))':'if (!rd && exact_pow (&e, x0, y, &R, exact))',
      '  dint64_t X, Y;':'  __asm__ volatile(".global mk61_pow_test_stage2\\nmk61_pow_test_stage2:" ::: "memory");\n  dint64_t X, Y;',
      '  qint64_t qX, qY;':'  __asm__ volatile(".global mk61_pow_test_stage3\\nmk61_pow_test_stage3:" ::: "memory");\n  qint64_t qX, qY;'
    }
    for old,new in patches.items():
        assert source.count(old)==1,('Upstream layout changed; inspect the intended test patch',old)
        source=source.replace(old,new)
    path.write_text(source)
    arm.ROOT=stage.resolve();elf=arm.build(compiler_bin(None),(out/'arm').resolve(),True)
    return elf,dict(original_pow_sha256=hashlib.sha256(original).hexdigest(),test_pow_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),patches=patches)


def corpus(samples):
    rng=random.Random(0xC064256)
    pairs=[(arm.bits(rng.uniform(.01,10)),arm.bits(rng.uniform(-100,100))) for _ in range(samples)]
    for _ in range(samples//2):
        x=arm.bits(1.)+rng.choice((-1,1))*rng.randrange(1,2048)
        y=rng.uniform(-700,700)/math.log(arm.real(x))
        pairs.append((x,arm.bits(y)))
    for x in (1,2,3,0xFFFFFFFFFFFFF,0x10000000000000,0x3FEFFFFFFFFFFFFF,0x3FF0000000000001,0x7FEFFFFFFFFFFFFF):
        for y in (1./3.,.125,.25,.375,.75,1.5,3.,-3.,17.,33.):pairs.append((x,arm.bits(y)))
    for x in (2.,3.,5.,9.,81.,.0625):
        for y in (.25,.5,1.,2.,3.,4.,7.,17.,33.,-.5,-3.):pairs.append((arm.bits(x),arm.bits(y)))
    return list(dict.fromkeys(pairs))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--snapshot',type=Path)
    source.add_argument('--elf',type=Path,help='An existing instrumented test ELF containing both stage markers')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--samples',type=int,default=2000)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);assert a.samples>=0
    elf,patch=(build(a.snapshot.resolve(),a.output.resolve()) if a.snapshot else (a.elf,{}))
    sha=hashlib.sha256(elf.read_bytes()).hexdigest();machine=arm.Machine(elf,True);oracle=Oracle()
    counts={'stage2':0,'stage3':0}
    for key in counts:
        address=machine.elf.symbols['mk61_pow_test_'+key]&~1
        def entered(uc,address,size,stage):counts[stage]+=1
        machine.uc.hook_add(UC_HOOK_CODE,entered,key,begin=address,end=address)
    pairs=corpus(a.samples);digest=hashlib.sha256()
    for i,(x,y) in enumerate(pairs):
        expected=oracle.reference('pow',x,y)
        actual=machine.call('_ZN12compact_math3powEdd',x,y)[0]
        assert actual==expected,(hex(x),hex(y),hex(actual),hex(expected),counts)
        digest.update(struct.pack('<4Q',x,y,expected,actual))
        if (i+1)%250==0:print(i+1,'/',len(pairs),counts,flush=True)
    assert all(counts.values()) and sha==hashlib.sha256(elf.read_bytes()).hexdigest()
    result=dict(status='PASS',cases=len(pairs),wrong_rounding=0,mpfr=oracle.version,stage_entry_counts=counts,
        sha256=digest.hexdigest(),elf_sha256=sha,source_patch=patch,
        scope='Test-only forced refinement; original exact-case precondition, overflow/underflow domains and final 256-bit interval check are retained. Finite corpus; not a universal pow proof.')
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result,flush=True)

if __name__=='__main__':main()
