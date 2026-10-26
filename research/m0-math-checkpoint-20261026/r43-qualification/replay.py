"""Fresh R43 calls with gold/current R42/all-Qfp explicitly inherited frozen sources."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,importlib.util,json,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
S=ROOT/'.build/m0-math-unified-pow-rsqrt-nativeq8-r43-20261026'
P=ROOT/'.build/m0-math-unified-pow-rsqrt-seedreuse-r42-qualification-20261026'
read=lambda p:json.loads(p.read_bytes())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
phase=sys.argv[1];assert phase in ('full','admission')
assert sha(S/'FROZEN.json')=='170cd77a62244459c526ea2817f964652f4355c31e7824defc7b0195a6a5b22b'
assert sha(P/'FROZEN.json')=='c9e7ebb1dcd34a4536e12fcb77af95ecbfc51f44176fe5b7e57e85b7cbe39515'
inputs=S if phase=='admission'else P
inputname='probe-records.jsonl.gz'if phase=='admission'else'full-records.jsonl.gz'
assert sha(inputs/inputname)==read(inputs/'FROZEN.json')['files'][inputname]['sha256']
assert not(W/(phase+'-result.json')).exists()
spec=importlib.util.spec_from_file_location('r43_'+phase,S/'harness.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);m=h.machine();assert not m.rom_models
from native_eabi_m0_arm_self_test import SP
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3),'PENDING':struct.pack('<7I',0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)}
refs=('qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer')
parentlabel='parent'if phase=='admission'else'candidate'
rows=0;unique=set();pl=set();cl=set();hist=Counter();increases=[];new=[];wrong=0;start=time.monotonic();current={}
try:
    with gzip.open(inputs/inputname,'rt')as stream,gzip.GzipFile(filename=str(W/(phase+'-records.jsonl.gz')),mode='wb',mtime=0)as out:
        for i,line in enumerate(stream):
            if i%8192==0:print('R43',phase,'rows',i,'elapsed',round(time.monotonic()-start,1),'loss',len(cl),'new',len(new),flush=True)
            old=json.loads(line);key=old['x'],old['y'];unique.add(key);state=old['SIO'];sb=states[state]
            current=dict(index=i,x=key[0],y=key[1],SIO=state)
            m.uc.mem_write(0xd0000060,sb)
            got,_,cost=m.call('_ZN12compact_math3powEdd',int(key[0],16),int(key[1],16),count=True);rows+=1
            assert old['correct'][parentlabel]and f'{got:016X}'==old['outputs'][parentlabel],current
            if phase=='admission':assert cost==old['instructions']['candidate']and f'{got:016X}'==old['outputs']['candidate']
            if state=='READY':assert not struct.unpack('<7I',m.uc.mem_read(0xd0000060,28))[6]&2
            else:assert bytes(m.uc.mem_read(0xd0000060,28))==sb
            pc=old['instructions'][parentlabel];hist[cost-pc]+=1;assert cost-pc in (-1,0),(current,cost,pc)
            outputs=dict(candidate=f'{got:016X}',parent=old['outputs'][parentlabel],**{r:old['outputs'][r]for r in refs})
            costs=dict(candidate=cost,parent=pc,**{r:old['instructions'][r]for r in refs})
            correct=dict(candidate=True,parent=True,**{r:old['correct'][r]for r in refs})
            record=dict(operation='pow',index=old.get('index',i),x=key[0],y=key[1],group=old.get('group','old-full140715'),SIO=state,expected=old['expected'],outputs=outputs,instructions=costs,correct=correct)
            if cost>pc:increases.append(record)
            for ref in refs:
                if not correct[ref]:wrong+=1;continue
                qc=costs[ref]
                if pc>qc:pl.add(key)
                if cost>qc:
                    cl.add(key)
                    if pc<=qc:new.append(dict(reference=ref,record=record))
            out.write((json.dumps(record,separators=(',',':'))+'\n').encode())
except Exception as error:
    (W/(phase+'-FAILURE.json')).write_text(json.dumps(dict(error=repr(error),current=current,completed_public_R43_ARM_calls=rows),indent=2)+'\n');raise
assert(rows,len(unique),len(pl))==({'full':(281430,140715,2303),'admission':(50220,16740,2353)}[phase])
result=dict(status='PASS_R43_FRESH_'+phase.upper()+'_CACHED_GOLD_R42_ALL_QFP',source_FROZEN_sha256=sha(S/'FROZEN.json'),parent_R42_qualification_FROZEN_sha256=sha(P/'FROZEN.json'),input_source_FROZEN_sha256=sha(inputs/'FROZEN.json'),input_records_sha256=sha(inputs/inputname),records_sha256=sha(W/(phase+'-records.jsonl.gz')),
    unique_input_pairs=len(unique),state_rows=rows,actual_qualified_public_ARM_calls=rows,actual_fresh_R42_Qfp_MPFR_calls=0,oracles_R42_allQfp_from_frozen_R42_qualification_or_R43_diagnostic_not_fresh=True,
    candidate_wrong=0,all_candidate_bits_exact_frozen_correct_parent=True,parent_losing_pairs=len(pl),candidate_losing_pairs=len(cl),fixed_pairs=[list(k)for k in sorted(pl-cl)],remaining_losing_argument_pairs=[list(k)for k in sorted(cl)],new_losing_pairs=[list(k)for k in sorted(cl-pl)],
    new_correct_reference_loss_rows=new,all_parent_instruction_increase_rows=increases,parent_instruction_delta_histogram=dict(hist),wrong_reference_state_variants_retained=wrong,all3_Qfplib_references_retained_eachinput_eachstate=True,no_nominal_reference_filter=True,
    observed_stack=SP-m.stack_lowest,not_universal_stack_bound=True,diagnostic_source_ARM251100_not_fresh_qualified_pool=True,source_loader_initialization_excluded=True,
    hardware_accessed=False,physical_cycles_measured=False,integration_GO=False,goal_complete=False,elapsed_seconds=time.monotonic()-start)
(W/(phase+'-result.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if not isinstance(v,list)},indent=2),flush=True)
