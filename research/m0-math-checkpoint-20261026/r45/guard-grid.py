"""Fresh R45 division values/costs and exact overflow-branch observations."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,importlib.util,json,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-pow-rsqrt-nativeq8-r43-20261026';B=ROOT/'.build/m0-ddiv-recip-overflow-r43-baseline-r2-20261026'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P/'FROZEN.json')=='170cd77a62244459c526ea2817f964652f4355c31e7824defc7b0195a6a5b22b'
assert sha(B/'FROZEN.json')=='06aed184b8178826326a19a26dbb700875e4826c7e0b915f1fb8f52c0625e9da'
assert not(W/'guard-grid-result.json').exists()
jobs={}
mask=(1<<52)-1
for E in range(1,2047):
    for N in (0,1,mask):
        for sign in (0,1):jobs[(E<<52,N|(sign<<63))]='all2046-normal-numerator-exponents'
for E in range(972,1027):
    for F in (0,1,(1<<31)-1,1<<31,(1<<32)-1,1<<32,1<<51,mask):
        k=1025-E;T=(1<<52)|F;T=T>>k if k>=0 else mask;T=min(T,mask)
        for N in set((max(T-1,0),T,min(T+1,mask))):
            for sa in (0,1):
                for sb in (0,1):jobs[((sa<<63)|(E<<52)|F,N|(sb<<63))]='every-k-threshold-neighbour-and-both-signs'
(W/'guard-grid-inputs.json').write_text(json.dumps(dict(groups=[dict(a=f'{a:016X}',b=f'{b:016X}',group=g)for(a,b),g in jobs.items()]),indent=2)+'\n')
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023'),str(ROOT/'.build/m0-float-fma-qualification-20261023/support')]
from m0_mpfr_oracle import Oracle
from oracles import equal
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE
def load(n,p):
    s=importlib.util.spec_from_file_location(n,p/'harness.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h);return h.machine()
machines={'candidate':load('r45_div',W),'parent':load('r43_div',P),'Qfplib':Machine(REF,True)};assert all(not m.rom_models for m in machines.values())
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3),'PENDING':struct.pack('<7I',0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)}
visits=Counter();hooks=[]
for label in('candidate','parent'):
    m=machines[label];a=m.elf.symbols['_ZN7m0_eabi19divide_significandsEyyRy']&~1
    hooks.append((m,m.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,label:visits.update([label]),user_data=label,begin=a,end=a)))
def exact_exponent(a,b):
    def unpack(v):
        E=v>>52&2047;F=v&((1<<52)-1)
        if E==2047 or not(E or F):return None
        return(F|(1<<52),E-1023)if E else(F<<(53-F.bit_length()),F.bit_length()-1075)
    a,b=unpack(a),unpack(b)
    return None if a is None or b is None else a[1]-b[1]-int(a[0]<b[0])
oracle=Oracle();calls=Counter();delta=Counter();pl=set();cl=set();targetpl=set();targetcl=set();new=[];inc=[];rows=0;snan=0;wrongref=0;elig=0;started=time.monotonic();current={}
try:
    with gzip.GzipFile(filename=str(W/'guard-grid-records.jsonl.gz'),mode='wb',mtime=0)as out:
        for i,((a,b),group)in enumerate(jobs.items()):
            if i%512==0:print('R45 all-exponent grid',i,'/',len(jobs),'loss',len(cl),flush=True)
            gold=oracle.reference('ddiv',a,b);snan+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51)for v in(a,b));e=exact_exponent(a,b)
            for state,sb in states.items():
                values={};cost={};correct={};startvis=dict(visits)
                for label,sym in [('candidate','__aeabi_ddiv'),('parent','__aeabi_ddiv'),('Qfplib','qfp_ddiv')]:
                    current=dict(index=i,a=f'{a:016X}',b=f'{b:016X}',SIO=state,label=label);m=machines[label];m.uc.mem_write(0xd0000060,sb);v,_,n=m.call(sym,a,b,count=True);calls[label]+=1;values[label]=f'{v:016X}';cost[label]=n;correct[label]=equal(v,gold,64)
                    if state=='READY':assert not struct.unpack('<7I',m.uc.mem_read(0xd0000060,28))[6]&2
                    else:assert bytes(m.uc.mem_read(0xd0000060,28))==sb
                    if label!='Qfplib':assert correct[label],(current,v,gold)
                assert values['candidate']==values['parent']
                hit={n:visits[n]-startvis.get(n,0)for n in('candidate','parent')}
                if e is not None and e>1023:assert hit=={'candidate':0,'parent':1};elig+=1
                else:assert hit['candidate']==hit['parent']
                d=cost['candidate']-cost['parent'];delta[d]+=1
                rec=dict(operation='ddiv',index=i,a=f'{a:016X}',b=f'{b:016X}',group=group,SIO=state,expected=f'{gold:016X}',outputs=values,instructions=cost,correct=correct,exact_quotient_exponent=e,actual_significand_division_calls=hit,parent_instruction_delta=d)
                if d>0:inc.append(rec)
                if not correct['Qfplib']:wrongref+=1
                else:
                    if cost['parent']>cost['Qfplib']:
                        pl.add((a,b))
                        if group=='known296-pow-reciprocals':targetpl.add((a,b))
                    if cost['candidate']>cost['Qfplib']:
                        cl.add((a,b))
                        if group=='known296-pow-reciprocals':targetcl.add((a,b))
                        if cost['parent']<=cost['Qfplib']:new.append(rec)
                out.write((json.dumps(rec,separators=(',',':'))+'\n').encode());rows+=1
except Exception as error:
    (W/'guard-grid-FAILURE.json').write_text(json.dumps(dict(error=repr(error),current=current,completed_ARM_calls=dict(calls)),indent=2)+'\n');raise
finally:
    for m,h in hooks:m.uc.hook_del(h)
result=dict(status='PASS_R45_FRESH_ALL_EXPONENT_GUARD_GRID',input_pairs=len(jobs),state_rows=rows,actual_diagnostic_ARM_calls=sum(calls.values()),completed_ARM_calls=dict(calls),actual_directed_MPFR_inputs=len(jobs)-snan,sNaN_policy_shortcuts=snan,candidate_wrong=0,parent_losing_pairs=len(pl),candidate_losing_pairs=len(cl),fixed_pairs=[[f'{a:016X}',f'{b:016X}']for a,b in sorted(pl-cl)],remaining_losing_argument_pairs=[[f'{a:016X}',f'{b:016X}']for a,b in sorted(cl)],new_correct_Qfp_loss_rows=new,parent_instruction_delta_histogram=dict(delta),all_parent_instruction_increase_rows=inc,known296_parent_losses=len(targetpl),known296_candidate_losses=len(targetcl),actual_proven_overflow_shortcut_state_rows=elig,all_nonoverflow_significand_division_visit_counts_exact_parent=True,wrong_reference_state_variants_retained=wrongref,all_wrong_reference_outputs_costs_retained=True,no_nominal_reference_filter=True,candidate_ELF_sha256=sha(W/'candidate.elf'),baseline_FROZEN_sha256=sha(B/'FROZEN.json'),records_sha256=sha(W/'guard-grid-records.jsonl.gz'),observed_stack={k:SP-m.stack_lowest for k,m in machines.items()},hardware_accessed=False,physical_cycles_measured=False,integration_GO=False,goal_complete=False,elapsed_seconds=time.monotonic()-started)
(W/'guard-grid-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if not isinstance(v,list)},indent=2),flush=True)
