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


def build(snapshot,output,force1024,force_exact_small=False,interval_hint=False):
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
    if force1024 or force_exact_small:
        path=stage/'code/native_eabi_m0_cr.cpp';source=path.read_text()
        old='m0_pow_interval::Fixed<512>::evaluate(a,b,result)';assert source.count(old)==1
        source=source.replace(old,'(false && '+old+')')
        if force_exact_small and not interval_hint:
            old='m0_pow_interval::Fixed<1024>::evaluate(a,b,result)';assert source.count(old)==1
            source=source.replace(old,'(false && '+old+')')
        path.write_text(source)
    interval_patches={}
    if interval_hint:
        assert force_exact_small
        path=stage/'code/native_eabi_m0_pow_interval.inc';source=path.read_text()
        for old,new in [
            ('if(exact_boundary(x,y,result)) return true;',
             'if(P!=1024 && exact_boundary(x,y,result)) return true;'),
            ('if(lower!=upper) {','if(lower!=upper || P==1024) {'),
        ]:
            assert source.count(old)==1,old
            source=source.replace(old,new)
            interval_patches[old]=new
        path.write_text(source)
    arm.ROOT=stage.resolve()
    elf=arm.build(compiler_bin(None),(output/'arm').resolve(),True)
    return elf,dict(patches=patches,force1024=force1024,force_exact_small=force_exact_small,
                    interval_hint=interval_hint,interval_patches=interval_patches)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--snapshot',type=Path)
    source.add_argument('--elf',type=Path,help='Previously built test-only forced-rescue ELF')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--samples',type=int,default=16)
    p.add_argument('--force-1024',action='store_true')
    p.add_argument('--force-exact-small',action='store_true',
                   help='Disable both interval stages and qualify the bounded exact integer stage')
    p.add_argument('--interval-hint',action='store_true',
                   help='With --force-exact-small, compute the final interval but force its undecided branch')
    a=p.parse_args();assert a.samples>=0;a.output.mkdir(parents=True,exist_ok=True)
    assert not (a.force_1024 and a.force_exact_small)
    assert not a.interval_hint or a.force_exact_small
    elf,patch=build(a.snapshot.resolve(),a.output.resolve(),a.force_1024,a.force_exact_small,a.interval_hint) if a.snapshot else (a.elf,{})
    sha=hashlib.sha256(elf.read_bytes()).hexdigest()
    machine=arm.Machine(elf,True,stack_bytes=16384,instruction_budget=200000000);oracle=Oracle()
    address=machine.elf.symbols['mk61_m0_pow_rescue']&~1;hits=[0]
    def entered(*unused):hits[0]+=1
    machine.uc.hook_add(arm.UC_HOOK_CODE,entered,begin=address,end=address)
    exact_hits=[0];hint_distances=[];expected_magnitude=[0];comparisons=[0]
    if a.force_exact_small:
        exact_address=machine.elf.symbols['mk61_m0_pow_exact_small']&~1
        def exact_entered(uc,*unused):
            exact_hits[0]+=1
            if a.interval_hint:
                sp=uc.reg_read(arm.UC_ARM_REG_SP)
                pointer=struct.unpack('<I',uc.mem_read(sp,4))[0]
                hint=struct.unpack('<Q',uc.mem_read(pointer,8))[0]
                distance=expected_magnitude[0]-hint
                assert 0<=distance<=1,('interval hint',hex(hint),hex(expected_magnitude[0]))
                hint_distances.append(distance)
        machine.uc.hook_add(arm.UC_HOOK_CODE,exact_entered,begin=exact_address,end=exact_address)
        if a.interval_hint:
            addresses={v&~1 for n,v in machine.elf.symbols.items() if 'm0_pow_exact' in n and 'relation' in n}
            assert addresses
            def compared(*unused):comparisons[0]+=1
            for address in addresses:
                machine.uc.hook_add(arm.UC_HOOK_CODE,compared,begin=address,end=address)
    rng=random.Random(0xF0512)
    if a.force_exact_small:
        pairs=[(rng.uniform(.5,2),rng.choice((-31./32,31./32,-3.,3.,17.))) for _ in range(a.samples)]
        pairs += [(x,y) for x in (-1.25,-2.,-9.) for y in (3.,-3.,17.,31.)]
        pairs += [(9.,17.),(81.,.75),(float.fromhex('0x1p-1074'),.25),
                  (1.25,31./32),(1.25,-31./32),(7.,19.),(2.**-215,5.)]
    else:
        pairs=[(rng.uniform(.05,10),rng.uniform(-30,30)) for _ in range(a.samples)]
        pairs += [(x,y) for x in (-1.25,-2.,-9.) for y in (3.,-3.,17.,33.)]
        pairs += [(9.,17.),(81.,.75),(2.,-1074.),(-2.,-1073.),(-2.,-1075.),
                  (float.fromhex('0x1p-1074'),.25),(1.-2.**-53,2.**60)]
    digest=hashlib.sha256()
    maximum_hint_comparisons=0
    for i,(x,y) in enumerate(pairs):
        a_bits,b_bits=arm.bits(x),arm.bits(y);expected=oracle.reference('pow',a_bits,b_bits)
        expected_magnitude[0]=expected&0x7FFFFFFFFFFFFFFF
        before_comparisons,before_hits=comparisons[0],exact_hits[0]
        entry='mk61_m0_cr_pow' if a.force_exact_small else '_ZN12compact_math3powEdd'
        actual=machine.call(entry,a_bits,b_bits)[0]
        assert actual==expected,(i,x,y,hex(actual),hex(expected))
        if a.interval_hint:
            used=comparisons[0]-before_comparisons;entered=exact_hits[0]-before_hits
            assert entered<=used<=2*entered,(i,entered,used)
            maximum_hint_comparisons=max(maximum_hint_comparisons,used)
        digest.update(struct.pack('<4Q',a_bits,b_bits,actual,expected))
        print('PASS',i+1,'/',len(pairs),'rescue calls',hits[0],flush=True)
    assert hits[0]>=max(1,a.samples),hits
    if a.force_exact_small:assert exact_hits[0]>=max(1,a.samples),exact_hits
    assert sha==hashlib.sha256(elf.read_bytes()).hexdigest()
    report=dict(status='PASS_TEST_ONLY',cases=len(pairs),wrong_rounding=0,rescue_calls=hits[0],
        force1024=a.force_1024,force_exact_small=a.force_exact_small,exact_stage_calls=exact_hits[0],
        interval_hint=a.interval_hint,checked_hint_calls=len(hint_distances),
        maximum_hint_distance=max(hint_distances,default=None),
        maximum_hint_comparisons=maximum_hint_comparisons,
        maximum_stack_bytes=arm.SP-machine.stack_lowest,
        allowed_stack_bytes=machine.stack_bytes,instruction_budget_per_call=machine.instruction_budget,
        elf_sha256=sha,sha256=digest.hexdigest(),source_patch=patch,mpfr=oracle.version,
        scope=('Private copy forces all three rounding tests to fail and bypasses exact_pow. '
               + ('Hint mode computes the real1024-bit endpoints and forces their undecided branch; '
                  'the test-only exact-boundary shortcut is bypassed. '
                  if a.interval_hint else
                  'Exact-small mode disables both interval passes. ' if a.force_exact_small else '') +
               'Exact-small modes enter the CORE-MATH wrapper directly. '
               'Checks real ARM call/return, result sign, exact midpoints, subnormals and bounded caller stack. '
               'Not an all-input totality proof.'))
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
