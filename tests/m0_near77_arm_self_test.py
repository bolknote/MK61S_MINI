#!/usr/bin/env python3
"""Check near-one log table boundaries and rounding in all SIO contexts."""
import argparse,gzip,hashlib,json,random,struct,sys,time
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from m0_mpfr_oracle import Oracle,bits
from native_eabi_m0_arm_self_test import Machine,SP

def pin(p):
    p=Path(p).resolve();b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--elf',type=Path,required=True);p.add_argument('--bootrom',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--samples',type=int,default=5000);a=p.parse_args()
    assert 0<=a.samples<=5000
    a.output_dir.mkdir(exist_ok=False)
    values=set()
    for j in range(257):
        for x in [(8064+j)/8192.,(16129+2*j)/16384.]:
            b=bits(x);values.update(range(b-3,b+4))
    for b in [0x3FF01E2A43FC46C8,0x3FEFE71BC4A8909F]:values.update(range(b-128,b+129))
    rng=random.Random(0x77C0FFEE)
    values.update(rng.randrange(0x3FEF800000000000,0x3FF0400000000001) for _ in range(a.samples))
    values=sorted(values)
    input_path=a.output_dir/'inputs.bin';input_path.write_bytes(b''.join(struct.pack('<Q',b) for b in values))
    oracle=Oracle();m=Machine(a.elf,True,bootrom=a.bootrom)
    states={'READY':(0,0,0,0,0,0,1),'DIRTY':(17,3,17,3,5,2,3),'PENDING':(0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)}
    prepared=dict(ELF=pin(a.elf),bootrom=pin(a.bootrom),operator=pin(__file__),inputs=pin(input_path),MPFR_version=oracle.version,
                  machine=pin(Path(__file__).with_name('native_eabi_m0_arm_self_test.py')),oracle=pin(Path(__file__).with_name('m0_mpfr_oracle.py')),
                  input_cases=len(values),math_call_cap=6*len(values),wall_seconds=600,pow_calls=0)
    (a.output_dir/'PREPARED.json').write_text(json.dumps(prepared,indent=2)+'\n')
    counts=Counter();wrong=[];fatal=None;start=time.monotonic()
    try:
        with gzip.open(a.output_dir/'records.jsonl.gz','xt') as output:
            for name in ['ln','log10']:
                symbol='_ZN12compact_math'+str(len(name))+name+'Ed'
                for b in values:
                    expected=oracle.reference(name,b)
                    for state,words in states.items():
                        assert m.calls<prepared['math_call_cap'] and time.monotonic()-start<=600
                        before=struct.pack('<7I',*words);m.uc.mem_write(0xd0000060,before)
                        actual,_,cost=m.call(symbol,b,count=True)
                        after=bytes(m.uc.mem_read(0xd0000060,28))
                        if state!='READY':assert after==before,(name,hex(b),state,'SIO')
                        row=dict(operation=name,input=f'{b:016X}',SIO=state,result=f'{actual:016X}',expected=f'{expected:016X}',instructions=cost,
                                 correct=actual==expected,SIO_preserved=after==before)
                        output.write(json.dumps(row,separators=(',',':'))+'\n');counts[name+':'+state]+=1
                        if actual!=expected:wrong.append(row)
                print(name,len(values),'inputs in3 SIO states; wrong',len(wrong),flush=True)
    except Exception as e:fatal=dict(type=type(e).__name__,message=str(e))
    result=dict(status='PASS_FINITE_NEAR_LOG_BOUNDARIES' if not wrong and fatal is None else 'FAIL',prepared=prepared,actual_ARM_calls=m.calls,
                counts=counts,wrong_rounding=len(wrong),examples=wrong[:20],fatal=fatal,maximum_observed_stack_bytes=SP-m.stack_lowest,
                elapsed_seconds=time.monotonic()-start,ABI='R4-R11/SP and bounded writes on every call',SIO='DIRTY/PENDING preserve all7words; READY is scratch by the existing runtime contract',
                pow_calls=0,device_IO=0,scope='Finite actual ARM boundary, neighbour and random checks against directed MPFR; not an all-input proof or physical timing.')
    (a.output_dir/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');(a.output_dir/'WRONG.json').write_text(json.dumps(wrong,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='prepared'}),flush=True)
    if result['status'].startswith('FAIL'):raise SystemExit(1)
if __name__=='__main__':main()
