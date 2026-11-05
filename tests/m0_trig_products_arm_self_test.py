#!/usr/bin/env python3
"""Exact public sin/cos checks at the new residual/old cell boundaries only."""
import argparse,gzip,hashlib,json,struct,time
from decimal import Decimal,localcontext
from pathlib import Path
from native_eabi_m0_arm_self_test import Machine,bits,nan
from m0_mpfr_oracle import Oracle
from profile_m0_trig import PI


def pin(p):
    p=Path(p).resolve();b=p.read_bytes()
    return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def inputs():
    values=set()
    def near(x):
        b=bits(x)
        for d in (-1,0,1):
            values.add(b+d);values.add((b+d)|(1<<63))
    for j in range(16,806):
        center=j/1024.
        for offset in (0.,2.**-39,-2.**-39,2.**-38,-2.**-38):near(center+offset)
        near((j+.5)/1024.)
    with localcontext() as c:
        c.prec=100
        for n in (-649,-17,-1,1,2,17,649):
            for j in (16,63,256,512,804):
                for delta in (0,1,-1):
                    near(float(abs(Decimal(n)*PI/2+Decimal(j)/1024+Decimal(delta)*Decimal(2)**-38)))
    return sorted(values)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);values=inputs()
    assert len(values)<=40000
    blob=b''.join(struct.pack('<Q',x) for x in values);q=a.output/'inputs.bin';q.write_bytes(blob)
    prep=dict(ELF=pin(a.elf),operator=pin(__file__),inputs=pin(q),input_cases=len(values),
        ARM_call_cap=2*len(values)+4*((len(values)+126)//127),wall_seconds=300,pow_calls=0)
    (a.output/'PREPARED.json').write_text(json.dumps(prep,indent=2)+'\n')
    m=Machine(a.elf,True);oracle=Oracle();wrong=[];fatal=None;start=time.monotonic();calls=0
    contexts=dict(READY=(0,0,0,0,0,0,1),DIRTY=(17,3,17,3,5,2,3),
                  PENDING=(0x80000001,7,0x80000001,7,0x11223344,0x55667788,2))
    try:
        with gzip.open(a.output/'records.jsonl.gz','xt') as f:
            for i,x in enumerate(values):
                for op in ('sin','cos'):
                    expected=oracle.reference(op,x)
                    for state,words in contexts.items():
                        if state!='READY' and i%127:continue
                        assert time.monotonic()-start<300 and calls<prep['ARM_call_cap']
                        before=struct.pack('<7I',*words);m.uc.mem_write(0xd0000060,before)
                        got=m.call('_ZN12compact_math3'+op+'Ed',x)[0];calls+=1
                        if state!='READY':assert bytes(m.uc.mem_read(0xd0000060,28))==before
                        good=(nan(got) and bool(got&(1<<51))) if nan(expected) else got==expected
                        r=dict(operation=op,input=f'{x:016X}',expected=f'{expected:016X}',
                               result=f'{got:016X}',SIO=state,correct=good)
                        if not good:wrong.append(r)
                        f.write(json.dumps(r,separators=(',',':'))+'\n')
    except Exception as e:fatal=repr(e)
    assert pin(a.elf)==prep['ELF']
    r=dict(status='FAIL' if wrong or fatal else 'PASS_FINITE_PUBLIC_SINCOS_BOUNDARIES',
        prepared=prep,completed_ARM_calls=calls,wrong=wrong,fatal=fatal,
        elapsed_seconds=time.monotonic()-start,MPFR_version=oracle.version,
        DIRTY_PENDING_preserved=True,hardware_IO=0,pow_calls=0,all_input_RNE_proof=False)
    (a.output/'RESULT.json').write_text(json.dumps(r,indent=2)+'\n')
    print(r['status'],'inputs',len(values),'calls',calls,'wrong',len(wrong),'seconds',r['elapsed_seconds'],flush=True)
    if wrong or fatal:raise SystemExit(1)


if __name__=='__main__':main()
