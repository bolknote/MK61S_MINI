"""Target the new low-normal/IEEE paths with independent exact references."""
from pathlib import Path
from collections import defaultdict,Counter
import hashlib,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
BASE=ROOT/'.build/m0-mixed-sign-top-normal-20261023'
EARLY=ROOT/'.build/m0-mixed-sign-original-goal-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import integer_binary,equal,is_nan
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE/'result.json')=='6e4e5b7eafeea3a11eebb499860f53d1d51fe892ce47b325ae4e48ae90f7d11d'
ELF=P/'firmware/mk61s-picocalc-pico-h.elf';REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
m=Machine(ELF,True,stack_bytes=4096,bootrom=ROM);ref=Machine(REF,True,stack_bytes=4096)
for folder,base,prefix,entry in ((BASE,0x10182000,'parent_','top_candidate_'),(W,0x10183000,'new_','cold_candidate_')):
    e=ElfImage(folder/'candidate.elf');m.uc.mem_write(base,(folder/'candidate.bin').read_bytes())
    for op in ('dadd','dsub'):m.elf.symbols[prefix+op]=e.symbols[entry+op]
SIGN=1<<63;QUIET=1<<51;jobs={}
def add(op,a,b,tag,profile=False):
    key=(op,a,b)
    if key not in jobs:jobs[key]=(tag,profile)
    elif profile:jobs[key]=(jobs[key][0],True)
def semantic(op,a,b,tag,profile=False):add(op,a,b^(SIGN if op=='dsub' else 0),tag,profile)
old=json.loads((EARLY/'profile.json').read_text())
for r in old['rows']:
    a,b=int(r['x'],16),int(r['y'],16);ea=(a>>52)&2047;eb=(b>>52)&2047
    if min(ea,eb)>0 and max(ea,eb)<55 and r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']:
        add(r['operation'],a,b,'old_low_slower',True)
    if r['group']=='IEEE_fallback':add(r['operation'],a,b,'IEEE_control',True)
for r in json.loads((BASE/'qualification.json').read_text())['rows']:
    if r['group'] in ('prior17_control','overflow_midpoint_edges'):
        add(r['operation'],int(r['x'],16),int(r['y'],16),'prior_fixed_control',True)
if '--all' in sys.argv:
    for E in range(1,55):
        for bit in range(52):
            differences=[1<<bit]
            if E in (1,2,15,16,17,31,32,33,53,54):
                differences += [((1<<bit)-1),((1<<bit)+1)]
            for diff in differences:
                if not 0<diff<(1<<52):continue
                a=(E<<52)|diff;b=E<<52
                for x,y in ((a,b|SIGN),(b|SIGN,a),(a|SIGN,b),(b,a|SIGN)):
                    profile=E in (1,2,16,17,32,33,53,54) and bit in (0,15,16,31,32,51)
                    semantic('dadd',x,y,'all_budgets_widths',profile)
                    if bit%8==0:semantic('dsub',x,y,'all_budgets_widths',profile)
    fractions=(0,1,1<<51,(1<<52)-1)
    for E in range(1,55):
        for gap in (0,1,2,3,15,16,19,20,21,30,31,32,33,51,52,53):
            if E-gap<1:continue
            for f in fractions:
                a=(E<<52)|f;b=((E-gap)<<52)|((1<<52)-1-f)
                for x,y in ((a,b),(b,a),(a|SIGN,b|SIGN),(b|SIGN,a|SIGN),(a,b|SIGN),(b|SIGN,a)):
                    for op in ('dadd','dsub'):
                        semantic(op,x,y,'alignment_and_signs',E in (1,2,3,54) or gap in (0,1,32,53))
    for bit in range(52):
        for sign in (0,SIGN):
            nan=sign|0x7ff0000000000000|(1<<bit)
            for other in (0x3ff0000000000000,0x7ff0000000000000,0x7ff8000000000001):
                for a,b in ((nan,other),(other,nan)):
                    for op in ('dadd','dsub'):add(op,a,b,'NaN_payload_priority',True)
    rng=random.Random(0xADD10C0)
    for _ in range(1024):
        a=(rng.randrange(1,55)<<52)|rng.getrandbits(52)|(rng.getrandbits(1)<<63)
        b=(rng.randrange(1,55)<<52)|rng.getrandbits(52)|(rng.getrandbits(1)<<63)
        for op in ('dadd','dsub'):add(op,a,b,'low_random',False)
if '--controls' in sys.argv:
    jobs.clear()
    for E in (55,56,1023,2045,2046):
        for gap in (0,1,2,20,31,32,33,53,54,55,64):
            if E-gap<1:continue
            for frac in (0,1,(1<<52)-1):
                a=(E<<52)|frac;b=((E-gap)<<52)|((1<<52)-1-frac)
                for x,y in ((a,b),(a|SIGN,b|SIGN),(a,b|SIGN),(a|SIGN,b)):
                    for xx,yy in ((x,y),(y,x)):
                        for op in ('dadd','dsub'):semantic(op,xx,yy,'ordinary_top_unchanged',True)
state=struct.pack('<7I',17,3,17,3,5,2,3);o=Oracle();start=time.monotonic();rows=[];groups=defaultdict(list)
for (op,a,b),(tag,count) in jobs.items():
    sb=b^(SIGN if op=='dsub' else 0)
    expected=integer_binary('add' if op=='dadd' else 'sub',a,b,width=64)
    mpfr=o.reference(op,a,b);assert equal(expected,mpfr,64)
    policy=(a|QUIET) if is_nan(a,64) else (sb|QUIET) if is_nan(sb,64) else expected
    values={};cost={};correct={}
    for label,name,machine in (('candidate','new_'+op,m),('parent','parent_'+op,m),('Qfplib','qfp_'+op,ref)):
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
        means={label:sum(r['instructions'][label] for r in counted)/len(counted) if counted else None for label in ('candidate','parent','Qfplib')}))
report=dict(status='PASS_TARGETED_LOW_NORMAL_AND_NAN_POLICY_NOT_PRODUCTION',cases=len(rows),ARM_calls=3*len(rows),profiled=sum(r['profiled'] for r in rows),groups=summary,rows=rows,
            MPFR_version=o.version,elapsed_seconds=time.monotonic()-start,parent_ELF_sha256=sha(BASE/'candidate.elf'),candidate_ELF_sha256=sha(W/'candidate.elf'),source_sha256=sha(W/'native_eabi_m0_rp2040.S'),
            IEEE_NaN_sign_payload_policy_exactly_matches_parent=True,READY_DIRTY_SIO_preserved_every_call=True,PCS_SP_bounded_writes_checked_every_call=True,
            instruction_counts_are_not_cycles=True,uncounted_rows_not_used_for_speed_claims=True,canonical_or_frozen_changed=False,USB_accessed=False,goal_complete=False)
name='controls.json' if '--controls' in sys.argv else 'qualification.json' if '--all' in sys.argv else 'smoke.json';(W/name).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
