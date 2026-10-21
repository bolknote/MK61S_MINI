#!/usr/bin/env python3
"""Measure complete checked-ln calls and observe actual refinement entries."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from m0_mpfr_oracle import Oracle,bits
from native_eabi_m0_arm_self_test import Machine
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R2


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--qualification',type=Path,required=True)
    p.add_argument('--samples',type=int,default=10000)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args()
    qualified=json.loads(args.qualification.read_text())
    path=args.build/'checked.elf';sha=hashlib.sha256(path.read_bytes()).hexdigest()
    assert qualified['status']=='PASS_RESEARCH_GATES' and qualified['elf_sha256']==sha
    old=Machine(args.build/'original.elf');new=Machine(path);oracle=Oracle()
    rng=random.Random(0x514c4e)
    # Match the deterministic groups in the qualification script.
    for _ in range(args.samples//4):rng.randrange(1,1<<52)
    one=bits(1.)
    groups={
      'normal_exponents':[(rng.randrange(1,2047)<<52)|rng.getrandbits(52) for _ in range(256)],
      'ordinary_half_to_two':[bits(rng.uniform(.5,2.)) for _ in range(256)],
      'near_one_tiny':[one+d for d in [-128,-17,-2,-1,0,1,2,17,128]],
      'near_one_outer':[bits(1+sgn*2.**-i) for i in range(10,37) for sgn in [-1,1]],
      'decimal_powers':[bits(10.**i) for i in range(-300,301,5)],
    }
    if any(n in new.elf.symbols for n in ('qfp_ln_near_seed','qfp_ln_near_seed64','qfp_ln_near_seed66')):
        near_rng=random.Random(0x514e4541)
        groups['near_one_random']=[bits(1+near_rng.uniform(-2.**-12,2.**-12)) for _ in range(512)]
    entries={4:0,8:0}
    def entered(uc,*unused):
        w=uc.reg_read(UC_ARM_REG_R2);assert w in entries,w;entries[w]+=1
    address=new.elf.symbols['refine']&~1
    hook=new.uc.hook_add(UC_HOOK_CODE,entered,begin=address,end=address)
    results={}
    for name,inputs in groups.items():
        before=dict(entries);original=checked=0;maximum=0
        for x in inputs:
            original+=old.call('qfp_dln',x,count=True)[2]
            result=new.call('qfp_dln_checked',x,count=True)
            assert result[0]==oracle.reference('ln',x)
            checked+=result[2];maximum=max(maximum,result[2])
        used={w:entries[w]-before[w] for w in entries}
        results[name]=dict(cases=len(inputs),original_mean=original/len(inputs),
                          checked_mean=checked/len(inputs),checked_over_original=checked/original,
                          checked_max=maximum,refinement_entries=used,
                          refine117_fraction=used[4]/len(inputs))
        print(name,json.dumps(results[name]),flush=True)
    new.uc.hook_del(hook)
    assert sha==hashlib.sha256(path.read_bytes()).hexdigest()
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(dict(status='PASS_PROFILE',elf_sha256=sha,
        qualification=str(args.qualification),qualification_sha256=hashlib.sha256(args.qualification.read_bytes()).hexdigest(),
        groups=results,physical_timing=False,
        scope='Executed ARM instructions for every full call, including refinement. PC hooks observe actual Q117/Q245 entries; no runtime counters or mutable RAM added.'),indent=2)+'\n')


if __name__=='__main__':main()
