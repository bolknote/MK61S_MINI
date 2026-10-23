"""Independent bare-ELF add/sub checks, especially every E0 boundary class."""
from pathlib import Path
from collections import defaultdict,Counter
import hashlib,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
BASE=ROOT/'.build/m0-add-cold-normal-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import integer_binary,equal,is_nan
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE/'result.json')=='70014f74e93ddf39ff37a1001a56601c85e16dcd89a22b3e0dbbce1f3f5a5bdb'
ELF=P/'firmware/mk61s-picocalc-pico-h.elf';REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
# The new candidate has no mapped firmware or ROM, and only32 bytes of allowed
# stack writes. A hidden dependency or deeper scratch frame cannot be reused.
candidate=Machine(W/'candidate.elf',True,stack_bytes=32)
parent=Machine(ELF,True,stack_bytes=4096,bootrom=ROM);reference=Machine(REF,True,stack_bytes=4096)
e=ElfImage(BASE/'candidate.elf');parent.uc.mem_write(0x10183000,(BASE/'candidate.bin').read_bytes())
for op in ('dadd','dsub'):parent.elf.symbols['parent_'+op]=e.symbols['cold_candidate_'+op]
SIGN=1<<63;QUIET=1<<51;H=1<<52;jobs={}
def add(op,a,b,tag,profile=False):
    k=(op,a,b)
    if k not in jobs:jobs[k]=(tag,profile)
    elif profile:jobs[k]=(jobs[k][0],True)
def semantic(op,a,b,tag,profile=False):add(op,a,b^(SIGN if op=='dsub' else 0),tag,profile)
previous=json.loads((BASE/'qualification.json').read_text())
for r in previous['rows']:
    if r['profiled'] and r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']:
        add(r['operation'],int(r['x'],16),int(r['y'],16),'old18_subnormal_slower',True)
edges=[0,SIGN,1,2,3,H-2,H-1,H,H+1,(2*H)-1,2*H,(2*H)+1,3*H,
       54<<52,55<<52,0x3ff0000000000000,0x7fefffffffffffff,0x7ff0000000000000,
       0xfff0000000000000,0x7ff0000000000001,0xfff8000000000001]
for a in edges:
    for b in edges:
        for op in ('dadd','dsub'):add(op,a,b,'IEEE_and_E0_edges',True)
if '--all' in sys.argv:
    coeffs={1,2,3,H-1,H-2}
    for bit in range(52):
        coeffs.update(v for v in ((1<<bit)-1,1<<bit,(1<<bit)+1) if 0<v<H)
    for sub in sorted(coeffs):
        bit=sub.bit_length()-1
        fields=sorted({1,2,3,31,32,33,53,54,55,56,1023,2046,2047,*[v for v in (bit+1,bit+2,bit+3,bit+4) if 1<=v<2047]})
        for E in fields:
            for frac in (0,1,H-1):
                other=(E<<52)|frac
                for a,b in ((sub,other),(other,sub),(sub|SIGN,other),(other,sub|SIGN)):
                    profile=bit in (0,15,16,31,32,50,51) and sub==(1<<bit)
                    semantic('dadd',a,b,'E0_normal_cell_boundaries',profile)
                    if bit%8==0:semantic('dsub',a,b,'E0_normal_cell_boundaries',profile)
        # Around the raw-coefficient sum2^53, and the difference2^52.
        for delta in (-3,-2,-1,0,1,2,3):
            for frac in (H-sub+delta,sub+delta):
                if not 0<=frac<H:continue
                other=H|frac
                for a,b in ((sub,other),(other,sub),(sub|SIGN,other),(other,sub|SIGN),(sub|SIGN,other|SIGN)):
                    for op in ('dadd','dsub'):semantic(op,a,b,'raw_small_rounding_boundaries',sub in (1,H-1,H-2))
        for other in (0,1,H-1,sub):
            for a,b in ((sub,other),(other,sub),(sub|SIGN,other),(other,sub|SIGN),(sub|SIGN,other|SIGN)):
                for op in ('dadd','dsub'):semantic(op,a,b,'both_subnormal_coefficients',sub in (1,H-1,H-2))
    rng=random.Random(0xADD5AB00)
    for _ in range(2048):
        sub=rng.randrange(H)|(rng.getrandbits(1)<<63)
        E=rng.choice((0,1,2,3,rng.randrange(1,2047)))
        other=(E<<52)|rng.getrandbits(52)|(rng.getrandbits(1)<<63)
        for a,b in ((sub,other),(other,sub)):
            for op in ('dadd','dsub'):add(op,a,b,'E0_random',False)
if '--controls' in sys.argv:
    jobs.clear()
    for E in (1,2,54,55,1023,2045,2046,2047):
        for gap in (0,1,2,20,31,32,33,53,54,55):
            if E-gap<1:continue
            for frac in (0,1,H-1):
                a=(E<<52)|frac;b=((E-gap)<<52)|(H-1-frac)
                for x,y in ((a,b),(b,a),(a|SIGN,b|SIGN),(a,b|SIGN),(b|SIGN,a)):
                    for op in ('dadd','dsub'):semantic(op,x,y,'unchanged_normal_controls',True)
state=struct.pack('<7I',17,3,17,3,5,2,3);o=Oracle();start=time.monotonic();rows=[];groups=defaultdict(list)
for (op,a,b),(tag,count) in jobs.items():
    sb=b^(SIGN if op=='dsub' else 0)
    expected=integer_binary('add' if op=='dadd' else 'sub',a,b,width=64)
    assert equal(expected,o.reference(op,a,b),64)
    policy=(a|QUIET) if is_nan(a,64) else (sb|QUIET) if is_nan(sb,64) else expected
    values={};cost={};correct={}
    for label,name,machine in (('candidate','sub_candidate_'+op,candidate),('parent','parent_'+op,parent),('Qfplib','qfp_'+op,reference)):
        machine.uc.mem_write(0xd0000060,state)
        got,_,n=machine.call(name,a,b,count=count)
        assert bytes(machine.uc.mem_read(0xd0000060,28))==state
        values[label]=f'{got:016X}';cost[label]=n if count else None;correct[label]=equal(got,expected,64)
        if label!='Qfplib' and (not correct[label] or got!=policy):
            failure=dict(operation=op,x=f'{a:016X}',y=f'{b:016X}',group=tag,label=label,got=f'{got:016X}',expected=f'{expected:016X}',policy=f'{policy:016X}')
            (W/'FAILURE.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    r=dict(operation=op,x=f'{a:016X}',y=f'{b:016X}',group=tag,expected=f'{expected:016X}',policy=f'{policy:016X}',outputs=values,instructions=cost,correct=correct,profiled=count)
    rows.append(r);groups[tag].append(r)
    if len(rows)%4096==0:print('progress',len(rows),'/',len(jobs),flush=True)
summary=[]
for tag,rs in sorted(groups.items()):
    counted=[r for r in rs if r['profiled']];both=[r for r in counted if r['correct']['Qfplib']]
    summary.append(dict(group=tag,cases=len(rs),profiled=len(counted),candidate_wrong=sum(not r['correct']['candidate'] for r in rs),Qfplib_wrong=sum(not r['correct']['Qfplib'] for r in rs),
       vs_parent=dict(Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'slower' if r['instructions']['candidate']>r['instructions']['parent'] else 'equal' for r in counted)),
       parent_slower_correct_Qfplib=sum(r['instructions']['parent']>r['instructions']['Qfplib'] for r in both),candidate_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] for r in both),
       new_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] and r['instructions']['parent']<=r['instructions']['Qfplib'] for r in both),
       means={k:sum(r['instructions'][k] for r in counted)/len(counted) if counted else None for k in ('candidate','parent','Qfplib')}))
assert SP-candidate.stack_lowest==20
report=dict(status='PASS_BARE_ELF_E0_ADD_SUB_NO_CPP_FALLBACK_NOT_PRODUCTION',cases=len(rows),ARM_calls=3*len(rows),profiled=sum(r['profiled'] for r in rows),groups=summary,rows=rows,
    candidate_mapped_firmware_or_ROM=False,candidate_stack_write_allowance=32,candidate_observed_written_stack_bytes=SP-candidate.stack_lowest,
    parent_ELF_sha256=sha(BASE/'candidate.elf'),candidate_ELF_sha256=sha(W/'candidate.elf'),source_sha256=sha(W/'native_eabi_m0_rp2040.S'),MPFR_version=o.version,elapsed_seconds=time.monotonic()-start,
    NaN_sign_payload_parent_exact=True,READY_DIRTY_SIO_preserved_every_call=True,PCS_SP_bounded_writes_checked_every_call=True,instructions_are_not_cycles=True,
    unprofiled_rows_not_used_for_speed_claims=True,canonical_or_frozen_changed=False,USB_accessed=False,goal_complete=False)
name='controls.json' if '--controls' in sys.argv else 'qualification.json' if '--all' in sys.argv else 'smoke.json'
(W/name).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
