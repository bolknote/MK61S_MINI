"""Fresh R47 calls; R45/Qfplib/MPFR data explicitly cached from frozen R46."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,importlib.util,json,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
B=ROOT/'.build/m0-math-unified-ddiv-boundaries-r46-20261026';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(B/'FROZEN.json')=='dc397afb030b14a77db3430e949b64c5c0c19811e6c0690042dd102c19bf3a9f'
frozen=json.loads((B/'FROZEN.json').read_bytes());names=['boundary-grid-records.jsonl.gz','boundary-grid-result.json','boundary-grid-inputs.json']
for n in names:assert sha(B/n)==frozen['files'][n]['sha256']
spec=importlib.util.spec_from_file_location('r47_boundary_harness',W/'harness.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);m=h.machine()
sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023'));from oracles import equal
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3),'PENDING':struct.pack('<7I',0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)}
assert not(W/'boundary-replay-result.json').exists();calls=0;rows=0;pl=set();cl=set();delta=Counter();increases=[];new=[];wrongref=0;cur={};started=time.monotonic()
try:
    with gzip.GzipFile(filename=str(W/'boundary-replay-records.jsonl.gz'),mode='wb',mtime=0)as out:
        for ln in gzip.open(B/'boundary-grid-records.jsonl.gz'):
            r=json.loads(ln);a,b=int(r['a'],16),int(r['b'],16);state=r['SIO'];sb=states[state];cur=dict(a=r['a'],b=r['b'],SIO=state,index=r['index'])
            if rows%3072==0:print('R47 cached-oracle boundary replay',rows,'/',231846,'losses',len(cl),flush=True)
            m.uc.mem_write(0xd0000060,sb);v,_,n=m.call('__aeabi_ddiv',a,b,count=True);calls+=1
            assert equal(v,int(r['expected'],16),64),(cur,f'{v:016X}',r['expected'])
            if state=='READY':assert not struct.unpack('<7I',m.uc.mem_read(0xd0000060,28))[6]&2
            else:assert bytes(m.uc.mem_read(0xd0000060,28))==sb
            oldv,oldn=r['outputs']['candidate'],r['instructions']['candidate'];r['outputs']['unselected_R46']=oldv;r['instructions']['unselected_R46']=oldn;r['correct']['unselected_R46']=r['correct']['candidate']
            r['outputs']['candidate']=f'{v:016X}';r['instructions']['candidate']=n;r['correct']['candidate']=True
            d=n-r['instructions']['parent'];r['parent_instruction_delta']=d;r['unselected_R46_instruction_delta']=n-oldn;r['reference_parent_gold_source']='cached_frozen_R46_parent_is_R45';delta[d]+=1
            if d>0:increases.append(r)
            k=(r['a'],r['b'])
            if r['correct']['Qfplib']:
                if r['instructions']['parent']>r['instructions']['Qfplib']:pl.add(k)
                if n>r['instructions']['Qfplib']:
                    cl.add(k)
                    if r['instructions']['parent']<=r['instructions']['Qfplib']:new.append(r)
            else:wrongref+=1
            out.write((json.dumps(r,separators=(',',':'))+'\n').encode());rows+=1
except Exception as err:
    (W/'boundary-replay-FAILURE.json').write_text(json.dumps(dict(error=repr(err),current=cur,completed_ARM_calls=calls),indent=2)+'\n');raise
result=dict(status='PASS_R47_FRESH_BOUNDARY_REPLAY_WITH_EXPLICIT_CACHED_REFERENCES',input_pairs=77282,state_rows=rows,actual_diagnostic_ARM_calls=calls,actual_directed_MPFR_inputs=0,sNaN_policy_shortcuts=0,all_parent_Qfplib_and_gold_cached_frozen_R46=True,cached_parent_is_selected_R45=True,candidate_wrong=0,parent_losing_pairs=len(pl),candidate_losing_pairs=len(cl),remaining_losing_argument_pairs=sorted(cl),new_correct_Qfp_loss_rows=new,all_parent_instruction_increase_rows=increases,parent_instruction_delta_histogram=dict(delta),wrong_reference_state_variants_retained=wrongref,all_wrong_reference_outputs_costs_retained=True,no_nominal_reference_filter=True,candidate_ELF_sha256=sha(W/'candidate.elf'),R46_diagnostic_FROZEN_sha256=sha(B/'FROZEN.json'),source_records_sha256=sha(B/'boundary-grid-records.jsonl.gz'),records_sha256=sha(W/'boundary-replay-records.jsonl.gz'),observed_stack_bytes=h.SP-m.stack_lowest,all_fresh_calls_public=True,no_new_primitive_controls_in_pool=True,hardware_accessed=False,physical_cycles_measured=False,integration_GO=False,goal_complete=False,elapsed_seconds=time.monotonic()-started)
assert rows==231846
(W/'boundary-replay-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if not isinstance(v,list)},indent=2),flush=True)
