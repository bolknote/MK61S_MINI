"""Exact integer/MPFR and ARM checks for the private uint32 leaf."""
from pathlib import Path
from collections import Counter
import ctypes as C,hashlib,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,_Number
ELF=P/'firmware/mk61s-picocalc-pico-h.elf'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(ELF)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
m=Machine(ELF,True,stack_bytes=4096,bootrom=ROM);ref=Machine(REF,True,stack_bytes=4096)
c=ElfImage(W/'candidate.elf');m.uc.mem_write(0x10181000,(W/'candidate.bin').read_bytes())
m.elf.symbols['candidate_d2uiz']=c.symbols['candidate_d2uiz']
o=Oracle();lib=o.lib;lib.mpfr_get_ui.argtypes=[C.POINTER(_Number),C.c_int];lib.mpfr_get_ui.restype=C.c_ulong
n=_Number();lib.mpfr_init2(C.byref(n),53)
known=[r for r in json.loads((P/'slower-inputs.json').read_text())['rows'] if r['operation']=='d2uiz']
assert len(known)==256
jobs={int(r['x'],16):'known_slower' for r in known}
fractions=[0,1,(1<<20)-1,1<<20,(1<<31)-1,1<<31,(1<<32)-1,1<<32,1<<51,(1<<52)-1]
for e in range(2048):
    for f in fractions:
        for s in (0,1):jobs.setdefault((s<<63)|(e<<52)|f,'every_exponent_boundary')
for e in range(1023,1055):
    for bit in range(52):
        for f in ((1<<bit)-1,1<<bit,(1<<bit)+1):
            jobs.setdefault((e<<52)|f,'retained_bit_boundaries')
for bit in range(52):
    for sign in (0,1):jobs.setdefault((sign<<63)|(2047<<52)|(1<<bit),'every_NaN_payload_bit')
rng=random.Random(0xD2322040)
for _ in range(2048):jobs.setdefault(rng.getrandbits(64),'random_fields')
def exact(a):
    e=(a>>52)&2047;f=a&((1<<52)-1)
    if a>>63 or e<1023 or (e==2047 and f):return 0
    if e>=1055:return 0xffffffff
    return ((1<<52)|f)>>(1075-e)
def mpfr(a):
    lib.mpfr_set_d(C.byref(n),struct.unpack('<d',struct.pack('<Q',a))[0],0)
    return min(int(lib.mpfr_get_ui(C.byref(n),1)),0xffffffff)  # MPFR_RNDZ
state=struct.pack('<7I',17,3,17,3,5,2,3)
rows=[];summary=Counter();start=time.monotonic()
try:
    for a,group in jobs.items():
        expected=exact(a);other=mpfr(a)
        assert expected==other,('oracle disagreement',hex(a),expected,other)
        count=group=='known_slower' or a in (0,1<<63,0x3ff0000000000000,0x41efffffffe00000,0x41f0000000000000,0x7ff0000000000000,0x7ff8000000000000)
        values={};costs={}
        for label,name,machine in (('candidate','candidate_d2uiz',m),('baseline','__aeabi_d2uiz',m),('Qfplib','qfp_double2uint',ref)):
            machine.uc.mem_write(0xd0000060,state)
            value,_,instructions=machine.call(name,a,count=count);value&=0xffffffff
            assert bytes(machine.uc.mem_read(0xd0000060,28))==state
            values[label]=value;costs[label]=instructions if count else None
            summary[label+'_wrong']+=value!=expected
            if label!='Qfplib' and value!=expected:
                failure=dict(x=f'{a:016X}',expected=expected,label=label,got=value)
                (W/'FAILURE.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
        summary[group]+=1
        rows.append(dict(x=f'{a:016X}',group=group,expected=expected,outputs=values,instructions=costs))
finally:lib.mpfr_clear(C.byref(n))
selected=[r for r in rows if r['group']=='known_slower']
report=dict(status='PASS_EXACT_UINT32_ARM_LEAF_NOT_PRODUCTION',cases=len(rows),ARM_calls=3*len(rows),summary=dict(summary),
    old_slower256=dict(cases=len(selected),candidate_faster_correct_Qfplib=sum(r['instructions']['candidate']<r['instructions']['Qfplib'] for r in selected),
                      count_pairs=dict(Counter(f'{r["instructions"]["candidate"]}/{r["instructions"]["baseline"]}/{r["instructions"]["Qfplib"]}' for r in selected))),
    rows=rows,elapsed_seconds=time.monotonic()-start,MPFR_version=o.version,
    input_ELF_sha256=sha(ELF),reference_ELF_sha256=sha(REF),ROM_sha256=sha(ROM),candidate_ELF_sha256=sha(W/'candidate.elf'),
    PCS_SP_and_bounded_writes_checked=True,READY_DIRTY_SIO_preserved_every_call=True,
    oracle='Independent unbounded integer truncate/saturation and MPFR_set_d exact53 plus MPFR_get_ui RNDZ followed by32-bit saturation; NaN/negative project policy preserved.',
    caveat='Casts truncate toward zero under EABI. Saturation/NaN behavior outside ordinary C range preserves this project policy, not a new C language guarantee. Counts are instructions, not hardware cycles.',
    hardware_accessed=False,canonical_or_frozen_mutated=False,goal_complete=False)
(W/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
