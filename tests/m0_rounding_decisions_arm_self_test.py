#!/usr/bin/env python3
"""Check signed atan division and the linked exp rounding guard."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import random
import struct
import time
from native_eabi_m0_arm_self_test import Machine, ROOT, UC_HOOK_MEM_READ

MASK=(1<<32)-1

def decision(base,fraction,n,magnitude,cell):
    # Unbounded exact sum and the previous full guard expression. No ADC
    # decomposition, short-circuit threshold or emulator result is reused.
    al,ah=base&MASK,base>>32;bl,bh=magnitude&MASK,magnitude>>32
    cross=(al*bh&MASK)+(ah*bl&MASK)+(al>>16)*(bl>>16)
    adjustment=((cross+(1<<31))>>32)-1
    if cell&2048:adjustment=-adjustment
    guard=3
    if n:
        distance=min(fraction,(-fraction)&MASK)
        reduction=n*0xD5E4F1DA&MASK
        uncertainty=(reduction+1)//2+(n+3)//4+2
        if uncertainty<(27<<27)-distance:guard=2
    if cell&1024:adjustment*=2;guard=2*guard+1
    distance=(cell&1023)+adjustment-512
    return 2 if distance>guard else 1 if distance<-guard else 0


def check_legacy_exp(m,samples,digest):
    def address(name):
        return next(v for k,v in m.elf.symbols.items() if k==name or name+'E' in k and (name.startswith('refine_') or 'refine' not in k))
    bases=struct.unpack('<512Q',m.uc.mem_read(address('exp_table'),4096))
    fractions=[struct.unpack('<I',m.uc.mem_read(address('refine_exp_table')+12*i,4))[0] for i in range(512)]
    rng=random.Random(0xEADCA221);vectors=[];tails=[0,1,502,503,505,507,508,509,510,511,512,513,514,515,516,517,519,521,522,1022,1023]
    bounds=[0,1,2,3,(1<<20)-1,1<<20]
    magnitudes=[0,1,65535,65536,MASK,1<<32,(1<<32)+1,(1<<54)-1,(1<<64)-1]
    threshold=0xAFF7FFFC
    nearby=sorted(range(1,(1<<20)+1),key=lambda n:abs((n*0xD5E4F1DA&MASK)-threshold))[:8]
    for i in range(512):
        for j in range(24):
            n=(bounds+nearby)[j%14];mag=magnitudes[j%len(magnitudes)]
            vectors.append((i,n,mag,tails[(i+j)%len(tails)]|((j&3)<<10)))
        al,ah=bases[i]&MASK,bases[i]>>32
        if al&1:
            inverse=pow(al,-1,1<<32)
            for bl in [0,1,MASK,rng.getrandbits(32)]:
                for target in [0,0x7FFFFFFE,0x7FFFFFFF,0x80000000,0x80000001,0xFFFFFFFE,MASK]:
                    bh=((target-ah*bl-(al>>16)*(bl>>16))*inverse)&MASK
                    vectors.append((i,rng.choice(bounds+nearby),bl|(bh<<32),rng.choice(tails)|(rng.randrange(4)<<10)))
    vectors += [(rng.randrange(512),rng.randrange((1<<20)+1),rng.getrandbits(64),rng.choice(tails)|(rng.randrange(4)<<10)) for _ in range(samples)]
    # The optimized caller passes error4/9 shifted by10, whose unused
    # bits12/13 must not affect the tail, sign or normalization fields.
    vectors=[(i,n,mag,cell|((1+(j&1))<<12)) for j,(i,n,mag,cell) in enumerate(vectors)]
    start=time.monotonic()
    for i,n,mag,cell in vectors:
        assert time.monotonic()-start<300
        expected=decision(bases[i],fractions[i],n,mag,cell)
        got=m.call('exp_round_decide',i|(n<<32),mag,c=cell)[0]&MASK
        assert got==expected,('exp decision',i,n,hex(mag),cell,got,expected)
        digest.update(struct.pack('<IIQII',i,n,mag,cell,got))
    return len(vectors)


def check_exp_scale_guard(machine):
    # The three widened-guard inputs need one missing scale word each.
    # Falling straight through to full refinement regresses these cases.
    reads_wanted = {20: 0, 28: 1, 34: 1, 35: 1}
    table = '_ZN7m0_eabiL16refine_exp_tableE'
    start = machine.elf.symbols[table]
    end = start + machine.elf.sizes[table]
    reads = []

    def read_scale_word(_uc, _access, address, size, _value, _user):
        reads.append((address-start, size))

    hook = machine.uc.hook_add(UC_HOOK_MEM_READ, read_scale_word, begin=start, end=end-1)
    checked = set()
    try:
        records = ROOT/'doc/measurements/m0-exp-q70-20261106/records.jsonl.gz'
        with gzip.open(records, 'rt') as source:
            for line in source:
                row = json.loads(line)
                group = row['index']
                if row['run'] != 'CURRENT' or row['operation'] != 'exp' or group not in reads_wanted:
                    continue
                packet = base64.b64decode(row['input_base64'], validate=True)
                assert hashlib.sha256(packet).hexdigest() == row['input_sha256'] and len(packet) == 56
                x, _, expected = struct.unpack_from('<3Q', packet, 32)
                reads.clear()
                actual = machine.call('_ZN12compact_math3expEd', x)[0]
                assert actual == expected, (group, hex(actual), hex(expected))
                assert len(reads) == reads_wanted[group], (group, reads)
                assert all(offset % 12 == 0 and size == 4 for offset, size in reads), (group, reads)
                checked.add(group)
    finally:
        machine.uc.hook_del(hook)
    assert checked == set(reads_wanted)
    return len(checked)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True);p.add_argument('--samples',type=int,default=10000)
    p.add_argument('--json',type=Path,required=True);a=p.parse_args();assert 0<=a.samples<=50000
    m=Machine(a.elf,True,stack_bytes=16384,instruction_budget=20000000)
    digest=hashlib.sha256();contexts=0
    if any('exp_round_decide' in name for name in m.elf.symbols):
        exp_decisions=check_legacy_exp(m,a.samples,digest)
        exp_scope='Historical exp carry chain and midpoint guard checked against unbounded integers.'
    else:
        assert '_ZL10exp_center' in m.elf.symbols,'Unrecognized RP2040 exp implementation'
        exp_decisions=0
        exp_scope='Current exp uses dyadic centers; see certify_m0_exp_center.py and qualify_m0_rounding.py.'
    exp_scale_cases = check_exp_scale_guard(m) if '_ZL16exp_center_scale' in m.elf.symbols else 0
    signed_calls=0
    states=[(0,0,0,0,0,0,1),(17,3,17,3,5,2,3),(0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)]
    heads=[0,1,-1,32,-32,(1<<18)-1,1<<18,-(1<<18),(1<<24)-1,-((1<<24)-1),33*(1<<24),-33*(1<<24)]
    denominators=[1<<18,(1<<18)+1,(1<<20)-1,1<<20,(1<<24)-2,(1<<24)-1]
    for head in heads:
        for denominator in denominators:
            expected=abs(head)//denominator
            if head<0:expected=-expected
            for words in states:
                before=struct.pack('<7I',*words);m.uc.mem_write(0xD0000060,before)
                got=m.call('mk61_m0_math_sdiv32',head&MASK,denominator,width=32)[0]&MASK
                assert got==expected&MASK,('signed quotient',head,denominator,got,expected)
                if words[-1]&2:
                    assert bytes(m.uc.mem_read(0xD0000060,28))==before;contexts+=1
                digest.update(struct.pack('<4I',head&MASK,denominator,words[-1],got));signed_calls+=1
    result=dict(status='PASS_INTEGER_EXP_DECISIONS_SIGNED_ATAN_DIVISION' if exp_decisions else 'PASS_SIGNED_ATAN_DIVISION',
        exp_decisions=exp_decisions,exp_scope=exp_scope,exp_scale_guard_cases=exp_scale_cases,signed_divisions=signed_calls,
        DIRTY_PENDING_checks=contexts,wrong=0,records_sha256=digest.hexdigest(),elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),hardware_IO=0,pow_calls=0,
        scope='Signed SIO quotient vs exact truncation in clean, dirty and pending contexts; Machine checks divider latency and preserved ABI/stack.')
    a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
