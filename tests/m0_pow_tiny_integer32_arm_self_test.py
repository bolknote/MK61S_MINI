#!/usr/bin/env python3
"""Compare the bounded32-bit tiny integer helper with its qualified parent."""
import argparse
import hashlib,json,math,random,struct
from pathlib import Path
from native_eabi_m0_arm_self_test import Machine,SP,bits,real
from m0_mpfr_oracle import Oracle

ONE=0x3FF0000000000000


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--baseline-elf',type=Path,required=True)
    p.add_argument('--bootrom',type=Path,required=True)
    p.add_argument('--samples',type=int,default=4000)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();rng=random.Random(0x940032);oracle=Oracle()
    machines={label:Machine(elf,True,stack_bytes=16384,instruction_budget=200000000,bootrom=args.bootrom)
              for label,elf in dict(baseline=args.baseline_elf,current=args.elf).items()}
    cases=set()
    ns={0,1,2,3,65535,65536,65537,131071,131072}
    for bit in range(17):ns.update((max(0,(1<<bit)-1),1<<bit,(1<<bit)+1))
    for below,maximum,limit in ((False,1<<20,1<<24),(True,1<<21,1<<25)):
        for n in sorted(ns):
            for delta in {0,1,2,maximum,maximum-1,min(maximum,limit//max(1,n)),min(maximum,limit//max(1,n)+1)}:
                for sign in (1,-1):cases.add((ONE-delta if below else ONE+delta,bits(float(sign*n))))
    for _ in range(args.samples):
        below=bool(rng.getrandbits(1));maximum=1<<(21 if below else 20)
        delta=rng.randrange(maximum+1);n=rng.randrange(1,131073)
        if rng.getrandbits(1):delta=rng.randrange(min(maximum,(1<<(25 if below else 24))//n)+1)
        cases.add((ONE-delta if below else ONE+delta,bits(float(n if rng.getrandbits(1) else -n))))
    for y in (bits(.5),bits(1.5),bits(65536.5),bits(1.)+1,bits(-1.)+1,
              0x7FF0000000000000,0x7FF0000000000001,0x7FF8000000000000):
        for x in (ONE-1,ONE+1):cases.add((x,y))
    output=SP-15000;canary=bytes.fromhex('83F79A15C02D6E4B')
    accepted=declined=public=0;counts=[];digest=hashlib.sha256()
    for index,(x,y) in enumerate(sorted(cases)):
        values={}
        for label,m in machines.items():
            m.uc.mem_write(output,canary)
            ok=m.call('pow_tiny_integer',x,y,c=output)[0]&255
            out=bytes(m.uc.mem_read(output,8));values[label]=(ok,out)
            if not ok:assert out==canary
        assert values['baseline']==values['current'],(hex(x),hex(y),values)
        ok,out=values['current']
        if ok:
            got=struct.unpack('<Q',out)[0];expected=oracle.reference('pow',x,y)
            assert got==expected,(hex(x),hex(y),hex(got),hex(expected))
            accepted+=1;digest.update(struct.pack('<3Q',x,y,got))
        else:declined+=1
        if index%53==0:
            row={}
            for label,m in machines.items():row[label]=m.call('pow_tiny_integer',x,y,c=output,count=True)[2]
            counts.append(row)
        if index%43==0 and math.isfinite(real(y)):
            actual=machines['current'].call('_ZN12compact_math3powEdd',x,y)[0]
            assert actual==oracle.reference('pow',x,y),(hex(x),hex(y),'public')
            public+=1
    assert accepted>1000 and declined>1000 and public>50
    result=dict(status='PASS',cases=len(cases),accepted=accepted,declined=declined,public_mpfr=public,
        baseline_bitwise_identical=True,wrong_rounding=0,result_sha256=digest.hexdigest(),
        counted_samples=len(counts),mean_instructions={label:sum(v[label] for v in counts)/len(counts) for label in machines},
        elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),baseline_elf_sha256=hashlib.sha256(args.baseline_elf.read_bytes()).hexdigest(),
        bootrom_sha256=machines['current'].bootrom_sha256,test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Actual compiled tiny-integer helper against the qualified parent, including exact canary preservation on declines. All accepted results independently match directed MPFR. Integer/exponent/caller-distance boundaries, threshold crossings, both signs and fractional/NaN/infinite declines are included. Public integration calls verify returned RNE values. This is finite coverage supplementing the bit-mask equivalence proof, not hardware-cycle or general-totality evidence.')
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',len(cases),'parent-identical cases;',accepted,'accepted;',declined,'declined;',public,'public MPFR;',result['mean_instructions'])


if __name__=='__main__':main()
