"""Focused bare directional pack/product54 and actual public ARM/MPFR calls."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import ast,hashlib,json,struct,sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
W=ROOT/'.build/m0-ln-near-directional-20261024';P=ROOT/'.build/m0-ln-enclosure-20261024'
V=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
SUP=ROOT/'.build/m0-float-fma-qualification-20261023/support'
sys.path[:0]=[str(SUP),str(SUP.parent),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_CODE
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def get(p):return json.loads(Path(p).read_text())
def put(n,o):
    with (OUT/n).open('x') as f:json.dump(o,f,indent=2);f.write('\n')
tree=ast.parse((ROOT/'.build/m0-ln-enclosure-independent-20261024/static-review.py').read_text())
fns=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('nearest','round64')]
pure={'F':F};exec(compile(ast.Module(body=fns,type_ignores=[]),'<accepted-pure-RNE>','exec'),pure);round64=pure['round64']
proof=get(OUT/'DIRECTIONAL-EXACT-PROOF.json');U=F(proof['upper']);L=F(proof['lower']);argument=F(proof['full_h_bound'])
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
S=1<<70;MASK=(1<<64)-1

unit=Machine(OUT/'pack-unit.elf',True,stack_bytes=128)
accesses=[]
def observe(*args):accesses.append(args)
unit.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,observe,begin=0xd0000060,end=0xd000007b)
jobs=[]
for den in (8065,8066,8192,8193,8319,8320):
    edge=(argument*den).__ceil__()-1
    for distance in (0,1,2,3,4):
        for side in (-1,1):
            for add in (False,True):
                i=len(jobs);beta=(-16,-12,-6,0,6,12,16)[i%7];r=(-edge,0,edge)[i%3]
                jobs.append((den,beta,r,add,False,distance,side,None))
# Exact threshold equalities plus one integer step either side. These are
# valid conservative bias/residual combinations, not fabricated h outputs.
for distance,which,beta,r in ((1,'upper',-6,0),(1,'lower',9,0),(2,'upper',6,0),(2,'lower',-3,0),(3,'upper',12,-4096),(3,'lower',-12,2048)):
    for dr in (-1,0,1):
        for add in (False,True):
            side=1 if (which=='upper')==add else -1
            jobs.append((8192,beta,r+dr,add,False,distance,side,which+'-equality' if not dr else which+'-neighbor'))
for distance in (0,1,2,3,4):
    for side in (-1,1):jobs.append((8065,0,0,True,True,distance,side,'exact-center'))
rows=[];endpoints=0;declined=0
for i,(den,beta,r,add,center,distance,side,label) in enumerate(jobs):
    width=(56,57,58,64,65)[i%5];shift=width-53;half=1<<(shift-1);tail=half+side*distance
    if not 0<=tail<2*half:continue
    retained=(1<<53)-1 if width==56 or i%3==0 else (1<<52)+(i&1)
    q=(retained<<shift)+tail;high=q>>64;low=q&MASK;sign=bool(i&1)
    assert high in (0,1)
    safe=distance>=4
    if not safe and distance:
        safe=center or (den*(12*distance-beta)+12*r>=18*den if (tail>half)==add else den*(12*distance+beta)-12*r>=21*den)
    expected=round64(F(-q if sign else q,S)) if safe else 0x7ff800000000019a
    if safe:
        B=F(beta,12)-F(r,den)
        errors=(-F(1,2),F(1,2)) if center else (B-L,B+U) if add else (-B-U,-B+L)
        for error in errors:
            exact=(F(q)-error)/S
            assert round64(-exact if sign else exact)==expected
            endpoints+=1
    else:declined+=1
    meta=(beta+16)|(int(add)<<6)|(int(center)<<7)|(int(sign)<<8)|(high<<9)|((den-8065)<<10)
    config=meta|((r&0xffffffff)<<32)
    for state_name,state in states.items():
        unit.uc.mem_write(0xd0000060,state);got,_,cost=unit.call('audit_near_pack',low,config,count=True)
        assert got==expected,(den,beta,r,distance,side,label,hex(got),hex(expected))
        assert bytes(unit.uc.mem_read(0xd0000060,28))==state
        rows.append(dict(den=den,bias12=beta,residue=r,distance=distance,side=side,add=add,exact_center=center,sign=sign,width=width,label=label,SIO=state_name,safe=bool(safe),expected=f'{expected:016X}',instructions=cost))
assert not accesses and declined and any(r['safe'] for r in rows)
assert all(not r['safe'] for r in rows if r['distance']==0)
put('BARE-PACKER-ARM.json',dict(status='PASS_BOUNDED_EXACT_INLINE_PACKER_ARM_AND_FRACTION_ENDPOINTS',
 actual_ARM_calls=len(rows),configurations=len(rows)//2,Fraction_endpoint_checks=endpoints,rows=rows,
 SIO_accesses=0,both_caller_states_preserved=True,PCS_SP_bounded_writes_every_call=True,
 stack_bytes_observed=SP-unit.stack_lowest,firmware_or_ROM_loaded=False,
 exact_midpoints_decline=True,threshold_equalities_and_one_step_neighbors_checked=True))

# Execute the unchanged retained product54 capsule against an independent
# full-limb model and exact H, including a=2^48 and all-low-limb endpoints.
resident=ElfImage(V/'firmware/mk61s-picocalc-pico-h.elf');name='mk61_m0_log_product54';address=resident.symbols[name]&~1;size=resident.sizes[name]
s=next(s for s in resident.named_sections.values() if s[2]&2 and s[3]<=address and address+size<=s[3]+s[5])
capsule=resident.bytes_at(s)[address-s[3]:address-s[3]+size]
bare=Machine(OUT/'candidate.elf',True,stack_bytes=128);bare.uc.mem_write(address,capsule);bare.elf.symbols['product54_probe']=address|1
seed_access=[]
def observe_seed(*args):seed_access.append(args)
bare.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,observe_seed,begin=0xd0000060,end=0xd000007b)
candidate=ElfImage(OUT/'candidate.elf');tab=next(n for n in candidate.symbols if 'log_near_table' in n)
t=candidate.symbols[tab];seedrows=[]
for den in (8065,8192,8320):
    R=struct.unpack('<Q',bare.uc.mem_read(t+(den-8065)*16,8))[0]
    for delta in (0,1,65535,(1<<32)-1,(1<<48)-1,1<<48):
        a0=delta&65535;a1=(delta>>16)&65535;b0=R&65535;b1=(R>>16)&65535
        omitted=a0*b0+((a0*b1+a1*b0)<<16);model=(delta*R-omitted+(1<<53))>>54
        H=F(delta<<21,den)
        for state_name,state in states.items():
            bare.uc.mem_write(0xd0000060,state);h,_,cost=bare.call('product54_probe',delta,R,count=True)
            assert h==model and abs(F(h)-H)<argument
            residue=(delta<<21)-h*den
            low32=((delta<<21)-(h&0xffffffff)*den)&0xffffffff
            signed=low32-(1<<32) if low32&(1<<31) else low32
            assert signed==residue and abs(residue)<argument*den
            assert bytes(bare.uc.mem_read(0xd0000060,28))==state
            seedrows.append(dict(den=den,delta=str(delta),h=str(h),residue=residue,error=str(F(h)-H),SIO=state_name,instructions=cost))
assert not seed_access
put('FULL-H-PRODUCT54-ARM.json',dict(status='PASS_FULL_H_BOUND_AND_SIGNED_REMAINDER_ACTUAL_ARM',
 actual_ARM_calls=len(seedrows),rows=seedrows,full_h_bound=str(argument),source_retained_limb_model_exact=True,
 loaded_capsule_bytes=size,capsule_sha256=hashlib.sha256(capsule).hexdigest(),SIO_accesses=0,
 no_firmware_or_ROM_loaded=True,PCS_SP_bounded_writes_every_call=True,stack_bytes_observed=SP-bare.stack_lowest))

# Fresh public boundary controls, including the new gain and worst retained
# cost cases. No full65880-state corpus replay.
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';ELF=V/'firmware/mk61s-picocalc-pico-h.elf';REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
machines={'Qfplib':Machine(REF,True)}
for label,path in (('parent',W/'control.elf'),('candidate',OUT/'candidate.elf')):
    m=Machine(ELF,True,bootrom=ROM);image=ElfImage(path);image.load(m.uc);m.elf.symbols[label+'_ln']=image.symbols['mk61_m0_ln'];m.trace=[]
    for n in ('ln_near_interval','ln_near_one','ln_refine','mk61_m0_cr_ln','mk61_m0_ln_special'):
        at=image.symbols[n]&~1
        def hit(uc,address,size,user,m=m):m.trace.append(user)
        m.uc.hook_add(UC_HOOK_CODE,hit,n,begin=at,end=at)
    machines[label]=m
auth=get(W/'qualification.json');saved={(r['x'],r['SIO']):r for r in auth['rows']}
historical={int(r['x'],16) for r in get(V/'slower-inputs.json')['rows'] if r['operation']=='ln'}
jobs={r:'historical' for r in historical}
def add(raw,group):
    if 0<=raw<(1<<64):jobs.setdefault(raw,group)
for raw in (0,1<<63,1,(1<<52)-1,1<<52,0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff8000000001234,bits(-2.0),bits(1.0),bits(2.0)):
    add(raw,'unaffected_IEEE_subnormal_control')
for raw in (0x3fef800000000000,0x3fef808000000000,0x3ff0400000000000):
    for d in (-1,0,1):add(raw+d,'dispatcher_control')
for n in (1,2,64,127,128):
    for sign in (-1,1):
        for a,b in ((n,8192),(2*n+1,16384)):
            center=bits(1+sign*a/b)
            for d in (-1,0,1):add(center+d,'center_halfcell_neighbor')
oracle=Oracle()
for e in (-15,-14,-13,-7):
    for sign in (-1,1):
        center=oracle.reference('exp',bits(sign*2.0**e))
        for d in (-1,0,1):add(center+d,'log_result_dyadic_edge')
ready=[r for r in auth['rows'] if r['SIO']=='READY']
fast=[r for r in ready if r['correct']['Qfplib'] and r['instructions']['candidate']<r['instructions']['parent']]
slow=[r for r in ready if r['instructions']['candidate']>r['instructions']['parent']]
for r in fast[:6]:add(int(r['x'],16),'sealed_gain_control')
for r in (max(slow,key=lambda r:r['instructions']['candidate']-r['instructions']['parent']),min(slow,key=lambda r:r['instructions']['candidate']-r['instructions']['parent'])):add(int(r['x'],16),'sealed_regression_control')
rows=[];calls=0
for raw,group in sorted(jobs.items()):
    expected=oracle.reference('ln',raw)
    for state_name,state in states.items():
        outputs={};costs={};correct={};trace={}
        for label,m in machines.items():
            m.uc.mem_write(0xd0000060,state)
            if label!='Qfplib':m.trace=[]
            got,_,cost=m.call('qfp_dln' if label=='Qfplib' else label+'_ln',raw,count=True);calls+=1
            outputs[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,expected,64)
            if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected));trace[label]=list(m.trace)
            after=bytes(m.uc.mem_read(0xd0000060,28))
            if state_name=='DIRTY':assert after==state
            else:assert not struct.unpack('<7I',after)[6]&2
        assert outputs['candidate']==outputs['parent']
        old=saved.get((f'{raw:016X}',state_name))
        if old:
            for label in machines:assert outputs[label]==old['outputs'][label] and costs[label]==old['instructions'][label]
        rows.append(dict(x=f'{raw:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=costs,correct=correct,trace=trace,author_record_matched=old is not None))
assert any('ln_near_interval' in r['trace']['candidate'] and 'ln_refine' in r['trace']['candidate'] for r in rows)
assert any(r['instructions']['candidate']<r['instructions']['parent'] for r in rows)
put('SELECTED-PUBLIC-ARM.json',dict(status='PASS_BOUNDED_FRESH_MPFR_DIRECTIONAL_PUBLIC_LN',
 unique_inputs=len(jobs),state_rows=len(rows),actual_ARM_calls=calls,MPFR_version=oracle.version,rows=rows,
 candidate_wrong=0,raw_parent_candidate_NaN_policy_equal=True,actual_decline_to_ln_refine_trace_observed=True,
 candidate_stack_bytes_observed=SP-machines['candidate'].stack_lowest,parent_stack_bytes_observed=SP-machines['parent'].stack_lowest,
 PCS_SP_return_bounded_writes_every_call=True,DIRTY_all28_SIO_bytes_preserved=True,READY_no_DIRTY_left=True,
 author_full_corpus_not_repeated=True,hardware_accessed=False))

# Honest sealed expanded-corpus accounting and inherited parent comparison.
rr=auth['rows'];prev={(r['x'],r['SIO']):r for r in get(P/'qualification.json')['rows']};retained=0
assert len(rr)==65880 and len({r['x'] for r in rr})==32940
for r in rr:
    assert r['correct']['candidate'] and r['outputs']['candidate']==r['outputs']['parent']
    old=prev.get((r['x'],r['SIO']))
    if old:
        retained+=1;assert r['instructions']['parent']==old['instructions']['candidate'] and r['outputs']['parent']==old['outputs']['candidate']
assert retained==39318
groups=[]
for state in states:
    selected=[r for r in rr if r['SIO']==state]
    changes=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in selected)
    before={r['x'] for r in selected if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']}
    after={r['x'] for r in selected if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']}
    assert after<=before
    groups.append(dict(SIO=state,vs_parent=dict(changes),parent_correct_Qfp_losses=len(before),candidate_correct_Qfp_losses=len(after),fixed=len(before-after),Qfplib_wrong=sum(not r['correct']['Qfplib'] for r in selected)))
remaining=[r for r in rr if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']]
regressions=[r for r in rr if r['instructions']['candidate']>r['instructions']['parent']]
assert remaining==get(W/'remaining-slower.json')['rows'] and len(remaining)==96 and len({r['x'] for r in remaining})==51
assert regressions==get(W/'regressions.json')['rows'] and len(regressions)==38174
deltas=[r['instructions']['candidate']-r['instructions']['parent'] for r in regressions]
assert [min(deltas),max(deltas)]==[7,105]
oldloss={r['x'] for r in get(P/'remaining-slower.json')['rows']};newloss={r['x'] for r in remaining}
assert len(oldloss-newloss)==15 and len(historical&{int(r,16) for r in newloss})==4
put('AUTHOR-ACCOUNTING.json',dict(status='PASS_EXPANDED_COUNTS_LOSSES_AND_REGRESSIONS_RETAINED',
 unique_inputs=32940,state_rows=65880,retained_parent_states=retained,groups=groups,
 old34_raw_losses_fixed=15,expanded_raw_losses_fixed=44,remaining_raw_inputs=51,remaining_state_rows=96,
 new_correct_Qfp_deficits=0,historical_ln10_fixed=6,historical_ln10_open=4,
 versus_parent=dict(equal=27402,slower=38174,faster=304),regression_instruction_range=[7,105],
 author_candidate_stack_same_expanded_corpus=640,author_parent_stack_same_expanded_corpus=600,
 code_growth_bytes=248,not_faster_than_parent_overall=True,no_physical_cycles_or_exhaustive_claim=True))
print(json.dumps(dict(status='PASS_BOUNDED_ARM_AND_SEALED_ACCOUNTING',bare_pack_calls=len(get(OUT/'BARE-PACKER-ARM.json')['rows']),product54_calls=len(seedrows),public_calls=calls,public_unique=len(jobs),MPFR=oracle.version)))
