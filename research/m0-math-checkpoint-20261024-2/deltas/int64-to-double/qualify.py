"""Actual Thumb conversions against independent integer RNE and MPFR."""
from pathlib import Path
from collections import Counter
import ctypes as C
import hashlib
import json
import random
import struct
import sys
import time
sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
Q = ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine, SP
from m0_mpfr_oracle import Oracle, _Number
from oracles import round_ratio
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
ELF=P/'firmware/mk61s-picocalc-pico-h.elf'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
assert sha(ELF)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
assert sha(REF)=='b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
assert sha(ROM)=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
candidate=Machine(W/'candidate.elf',True,stack_bytes=32)
parent=Machine(ELF,True,stack_bytes=4096,bootrom=ROM)
reference=Machine(REF,True,stack_bytes=4096)
operations={'l2d':(64,True,'qfp_int642double'),'ul2d':(64,False,'qfp_uint642double'),
            'i2d':(32,True,'qfp_int2double'),'ui2d':(32,False,'qfp_uint2double')}
MASK=(1<<64)-1
jobs={}
def add(op,value,tag):
    width,signed,_=operations[op]
    if signed and not -(1<<(width-1))<=value<(1<<(width-1)):return
    if not signed and not 0<=value<(1<<width):return
    key=(op,value&((1<<width)-1))
    jobs.setdefault(key,tag)
known=[r for r in json.loads((P/'slower-inputs.json').read_text())['rows'] if r['operation']=='l2d']
assert len(known)==16
for row in known:
    raw=int(row['x'],16)
    add('l2d',raw-(1<<64),'old16_l2d_slower')
for op,(width,signed,_) in operations.items():
    for bit in range(width):
        for delta in (-2,-1,0,1,2):
            for s in (-1,1) if signed else (1,):add(op,s*((1<<bit)+delta),'power_and_sign_boundaries')
if '--all' in sys.argv:
    rng=random.Random(0x12642040)
    for op,(width,signed,_) in operations.items():
        for bits in range(1,width+1):
            for _ in range(96):
                magnitude=(1<<(bits-1))|rng.getrandbits(bits-1)
                for s in (-1,1) if signed else (1,):add(op,s*magnitude,'all_bit_lengths')
        for _ in range(1024):
            raw=rng.getrandbits(width)
            add(op,raw-(1<<width) if signed and raw>>(width-1) else raw,'random_raw_words')
    # Integer values exactly at/beside every possible RNE discarded-bit
    # midpoint, including parity and significand carry into the next binade.
    for op in ('l2d','ul2d'):
        signed=operations[op][1]
        for shift in range(1,12):
            for retained in ((1<<52),(1<<52)+1,(1<<52)+2,(1<<53)-3,(1<<53)-2,(1<<53)-1):
                midpoint=(retained<<shift)+(1<<(shift-1))
                for delta in (-2,-1,0,1,2):
                    for s in (-1,1) if signed else (1,):add(op,s*(midpoint+delta),'RNE_parity_and_carry')
    # The new complemented-high-word decision and its low-word carry.
    for high in (0,1,0x7fffffff,0x80000000,0xfffffffd,0xfffffffe,0xffffffff):
        lows={0,1,2,0x7fffffff,0x80000000,0xfffffffe,0xffffffff}
        for bit in range(32):lows.update(((1<<bit)-1,1<<bit,min((1<<bit)+1,0xffffffff)))
        for low in sorted(lows):
            raw=(high<<32)|low
            add('l2d',raw-(1<<64) if high>>31 else raw,'complement_and_carry')
o=Oracle();lib=o.lib
assert C.sizeof(C.c_long)==C.sizeof(C.c_ulong)==8
lib.mpfr_set_si.argtypes=[C.POINTER(_Number),C.c_long,C.c_int]
lib.mpfr_set_ui.argtypes=[C.POINTER(_Number),C.c_ulong,C.c_int]
n=_Number();lib.mpfr_init2(C.byref(n),64)
states=(bytes(28),struct.pack('<7I',17,3,17,3,5,2,3))
rows=[];start=time.monotonic()
try:
    for index,((op,raw),tag) in enumerate(jobs.items()):
        width,signed,refname=operations[op]
        value=raw-(1<<width) if signed and raw>>(width-1) else raw
        expected=round_ratio(abs(value),1,0,64,value<0)
        (lib.mpfr_set_si if signed else lib.mpfr_set_ui)(C.byref(n),value,0)
        mpfr=struct.unpack('<Q',struct.pack('<d',lib.mpfr_get_d(C.byref(n),0)))[0]
        assert expected==mpfr,(op,hex(raw),hex(expected),hex(mpfr))
        outputs={};counts={}
        for label,machine,name in [('candidate',candidate,'__aeabi_'+op),('parent',parent,'__aeabi_'+op),('Qfplib',reference,refname)]:
            state=states[index%2];machine.uc.mem_write(0xd0000060,state)
            got,_,count=machine.call(name,raw,count=True)
            assert bytes(machine.uc.mem_read(0xd0000060,28))==state
            if label!='Qfplib':assert got==expected,(label,op,hex(raw),hex(got),hex(expected))
            outputs[label]=f'{got:016X}';counts[label]=count
        rows.append(dict(operation=op,x=f'{raw:016X}',group=tag,expected=f'{expected:016X}',outputs=outputs,instructions=counts))
        if len(rows)%4096==0:print('progress',len(rows),'/',len(jobs),flush=True)
finally:lib.mpfr_clear(C.byref(n))
groups=[]
for op in operations:
    selected=[r for r in rows if r['operation']==op]
    both=[r for r in selected if r['outputs']['Qfplib']==r['expected']]
    changes=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in selected)
    groups.append(dict(operation=op,cases=len(selected),candidate_wrong=0,parent_wrong=0,
                       Qfplib_wrong=sum(r['outputs']['Qfplib']!=r['expected'] for r in selected),vs_parent=dict(changes),
                       parent_slower_correct_Qfplib=sum(r['instructions']['parent']>r['instructions']['Qfplib'] for r in both),
                       candidate_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] for r in both),
                       new_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] and r['instructions']['parent']<=r['instructions']['Qfplib'] for r in both)))
old=[r for r in rows if r['group']=='old16_l2d_slower']
report=dict(status='PASS_L2D_ENTRY_EXACT_INTEGER_MPFR_ARM_NOT_PRODUCTION',cases=len(rows),ARM_calls=3*len(rows),groups=groups,
            old16=dict(cases=len(old),candidate_no_slower_correct_Qfplib=sum(r['outputs']['Qfplib']==r['expected'] and r['instructions']['candidate']<=r['instructions']['Qfplib'] for r in old),
                       count_pairs=dict(Counter(f'{r["instructions"]["candidate"]}/{r["instructions"]["parent"]}/{r["instructions"]["Qfplib"]}' for r in old))),
            rows=rows,candidate_ELF_sha256=sha(W/'candidate.elf'),source_sha256=sha(W/'native_eabi_m0_convert.inc'),input_ELF_sha256=sha(ELF),reference_ELF_sha256=sha(REF),
            stack_bytes_written=SP-candidate.stack_lowest,candidate_mapped_firmware_or_ROM=False,MPFR_version=o.version,
            PCS_SP_and_bounded_writes_checked_every_call=True,READY_DIRTY_SIO_preserved_every_call=True,instructions_are_not_cycles=True,
            elapsed_seconds=time.monotonic()-start,canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
assert report['stack_bytes_written']==0
assert all(not g['vs_parent'].get('slower',0) for g in groups)
assert report['old16']['candidate_no_slower_correct_Qfplib']==16
filename='qualification.json' if '--all' in sys.argv else 'smoke.json'
(W/filename).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
