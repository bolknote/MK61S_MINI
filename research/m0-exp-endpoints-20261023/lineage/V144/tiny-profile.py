"""Audit the proven tiny-y domain on private V144 and the frozen Qfplib reference."""
import hashlib
import json
from pathlib import Path
import struct
import sys
ROOT=Path.cwd();WORK=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
from native_eabi_m0_arm_self_test import Machine,bits
from m0_mpfr_oracle import Oracle
elf=ROOT/'.build/m0-pow-small-y-stable-v144-20261023/firmware/mk61s-picocalc-pico-h.elf'
reference=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
m=Machine(elf,True,stack_bytes=16384,instruction_budget=200000000,
          bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
ref=ElfImage(reference);ref.load(m.uc);m.elf.symbols.update({n:a for n,a in ref.symbols.items() if n.startswith('qfp_')})
oracle=Oracle();rows=[]
bases=[1,0x000fffffffffffff,bits(2.**-1022),bits(1e-200),bits(.125),bits(.75),bits(1.)-1,
       bits(1.)+1,bits(1.5),bits(2.),bits(3.),bits(23.),bits(1e200),0x7fefffffffffffff]
exponents=[1,0x000fffffffffffff,bits(1e-200),bits(2.**-100),bits(2.**-66),bits(2.**-65)-1,bits(2.**-65)]
for x in bases:
    for magnitude in exponents:
        for sign in (0,1<<63):
            y=magnitude|sign;want=oracle.reference('pow',x,y);assert want==bits(1.)
            own,_,oc=m.call('_ZN12compact_math3powEdd',x,y,count=True)
            qfp,_,qc=m.call('qfp_composed_pow',x,y,count=True)
            assert own==want,(hex(x),hex(y),hex(own),hex(want))
            rows.append(dict(x=f'{x:016X}',y=f'{y:016X}',expected=f'{want:016X}',own=f'{own:016X}',
                qfplib=f'{qfp:016X}',own_instructions=oc,qfplib_instructions=qc,
                positive_normal_base=x>=1<<52,qfplib_wrong=qfp!=want))
eligible=[r for r in rows if r['positive_normal_base']]
record=dict(status='PASS_TINY_Y_AUDIT_FINITE_INSTRUCTION_COUNTS',cases=len(rows),normal_base_cases=len(eligible),
    own_mean_instructions=sum(r['own_instructions'] for r in eligible)/len(eligible),
    qfplib_mean_instructions=sum(r['qfplib_instructions'] for r in eligible)/len(eligible),
    own_slower_normal_cases=sum(r['own_instructions']>r['qfplib_instructions'] for r in eligible),
    qfplib_wrong=sum(r['qfplib_wrong'] for r in rows),cases_data=rows,
    elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),reference_elf_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),mpfr=oracle.version,
    scope='New finite domain audit, outside the frozen117-group HIL matrix. Actual ARM instructions with captured ROM; not physical cycles or a universal speed claim. Reference is Qfplib exp(mul(y,ln(x))).',
    candidate_changed=False,hardware_accessed=False)
(WORK/'tiny-profile.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k!='cases_data'},indent=2),flush=True)
