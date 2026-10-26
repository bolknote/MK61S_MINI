"""Fresh R47 public pow, directed MPFR, all Qfp compositions and native metadata."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,importlib.util,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-ddiv-cold-overflow-r45-20261026'
Q=ROOT/'.build/m0-math-unified-ddiv-cold-overflow-r45-qualification-20261026'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P/'FROZEN.json')=='dbc455078837507acaeb750df1e3fb6800b923e2a9a880c9c6bcc2150ba3527a'
assert sha(Q/'FROZEN.json')=='e3f2df20d066f085a82722c3f601625e27bf51d070d21659bfeb40fdc270da30'
assert not(W/'probe-result.json').exists()
old={tuple(p)for p in json.loads((Q/'joined-audit.json').read_bytes())['pow_remaining_losing_argument_pairs']};assert len(old)==2047
jobs={p:'current2047-loss'for p in sorted(old)}
for r in json.loads((P/'probe-inputs.json').read_bytes())['groups']:jobs.setdefault((r['x'],r['y']),'inherited-R43-diagnostic-domain')
thin=set()
with gzip.open(Q/'full-records.jsonl.gz','rt')as f:
    for line in f:
        r=json.loads(line)
        if r['y']!='BFE0000000000000':continue
        refs=[v for n,v in r['instructions'].items()if n.startswith('qfp_')and r['correct'][n]]
        if refs and 0<=min(refs)-r['instructions']['candidate']<=2:thin.add(r['x'])
for x in sorted(thin):jobs.setdefault((x,'BFE0000000000000'),'current-thin-correct-reference-margin0..2')
for exp in (1,2,2045,2046):
    for i in range(256):
        for low in (0,1,1<<43,(1<<44)-1):jobs.setdefault((f'{(exp<<52)|(i<<44)|low:016X}','BFE0000000000000'),'all512-cells-near-extreme-normal-exponents')
rng=random.Random(0x614242f)
for i in range(2048):
    x=(rng.randrange(1,2047)<<52)|rng.getrandbits(52);jobs.setdefault((f'{x:016X}','BFE0000000000000'),'random-normal-exponents-and-full-mantissas')
(W/'probe-inputs.json').write_text(json.dumps(dict(status='PREPARED_R47_PUBLIC_DIAGNOSTIC_INPUTS',groups=[dict(x=x,y=y,group=g)for(x,y),g in jobs.items()],known2047=len(old),thin_margin_inputs=len(thin)),indent=2)+'\n')
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023'),str(ROOT/'.build/m0-float-fma-qualification-20261023/support')]
from m0_mpfr_oracle import Oracle
from oracles import equal
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R5,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR
def load(n,p):
    spec=importlib.util.spec_from_file_location(n,p/'harness.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);return h.machine()
machines={'candidate':load('r47_public',W),'parent':load('r45_parent_public',P),'Qfplib':Machine(REF,True)};assert all(not m.rom_models for m in machines.values())
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3),'PENDING':struct.pack('<7I',0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)}
refs=('qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer');hooks=[];metadata={};public_flags=0
for label in ('candidate','parent'):
    m=machines[label]
    for tag,sym in [('entry','mk61_m0_pow_rsqrt_fast'),('point','mk61_m0_pow_rsqrt_point'),('q8_frame','mk61_m0_pow_rsqrt_q8_frame_ready'),('q8_helper','mk61_m0_pow_rsqrt_local_q8_native')]:
        a=m.elf.symbols[sym]&~1
        def observe(uc,a,size,arg):
            label,tag=arg;meta=metadata[label]
            if tag=='entry':meta['native_calls']=meta.get('native_calls',0)+1
            elif tag=='q8_helper':
                high=struct.unpack('<I',uc.mem_read(uc.reg_read(UC_ARM_REG_R0)+28,4))[0];C=(uc.reg_read(UC_ARM_REG_XPSR)>>29)&1
                assert high in(0x7fffffff,0x80000000)and C==int(high==0x80000000)
                meta['q8_calls']=meta.get('q8_calls',0)+1;meta['q8_incoming_C']=C
            else:
                words=list(struct.unpack('<11I',uc.mem_read(uc.reg_read(UC_ARM_REG_SP),44)))
                if tag=='point':
                    meta['point_live_frame']={k:words[k]for k in (0,1,3,4,5,6,7,8)}
                    meta['q']=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);meta['Bh_R5']=uc.reg_read(UC_ARM_REG_R5)
                else:meta['q8_frame']=words;assert words[2]==words[6]*words[6]>>32
        hooks.append((m,m.uc.hook_add(UC_HOOK_CODE,observe,user_data=(label,tag),begin=a,end=a)))
    a=m.elf.symbols['_ZN12compact_math3powEdd']&~1
    def poison_public_flags(uc,a,size,arg):uc.reg_write(UC_ARM_REG_XPSR,(uc.reg_read(UC_ARM_REG_XPSR)&0x0fffffff)|(public_flags<<28))
    hooks.append((m,m.uc.hook_add(UC_HOOK_CODE,poison_public_flags,begin=a,end=a)))
counts=Counter();delta=Counter();pl=set();cl=set();new=[];increases=[];rows=0;snan=0;wrongrefs=0;native=Counter();q8visits=Counter();oracle=Oracle();started=time.monotonic();current={}
try:
    with gzip.GzipFile(filename=str(W/'probe-records.jsonl.gz'),mode='wb',mtime=0)as out:
        for i,((hx,hy),group)in enumerate(jobs.items()):
            if i%512==0:print('R47 public probe',i,'/',len(jobs),'elapsed',round(time.monotonic()-started,1),'loss',len(cl),flush=True)
            public_flags=i%16
            x,y=int(hx,16),int(hy,16);gold=oracle.reference('pow',x,y);snan+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51)for v in (x,y))
            for state,sb in states.items():
                outputs={};costs={};correct={};metadata.clear();metadata.update(candidate={},parent={})
                for label,symbol,m in [('candidate','_ZN12compact_math3powEdd',machines['candidate']),('parent','_ZN12compact_math3powEdd',machines['parent'])]+[(r,r,machines['Qfplib'])for r in refs]:
                    current=dict(index=i,x=hx,y=hy,SIO=state,label=label);m.uc.mem_write(0xd0000060,sb)
                    if label in ('candidate','parent'):m.uc.reg_write(UC_ARM_REG_R12,(0,1,0x80000000,0x55555555,0xffffffff)[i%5])
                    value,_,count=m.call(symbol,x,y,count=True);counts[label]+=1;outputs[label]=f'{value:016X}';costs[label]=count;correct[label]=equal(value,gold,64)
                    if state=='READY':assert not struct.unpack('<7I',m.uc.mem_read(0xd0000060,28))[6]&2
                    else:assert bytes(m.uc.mem_read(0xd0000060,28))==sb
                    if label in ('candidate','parent'):assert correct[label],(current,value,gold)
                assert outputs['candidate']==outputs['parent']and metadata['candidate']==metadata['parent'],(current,metadata)
                n=metadata['candidate'].get('native_calls',0);assert n in (0,1);native[n]+=1
                q8=metadata['candidate'].get('q8_calls',0);assert q8 in(0,1);q8visits[q8]+=1
                d=costs['candidate']-costs['parent'];delta[d]+=1
                record=dict(index=i,x=hx,y=hy,group=group,SIO=state,expected=f'{gold:016X}',outputs=outputs,instructions=costs,correct=correct,actual_native_metadata=metadata['candidate'])
                if d>0:increases.append(record)
                for r in refs:
                    if not correct[r]:wrongrefs+=1;continue
                    if costs['parent']>costs[r]:pl.add((hx,hy))
                    if costs['candidate']>costs[r]:
                        cl.add((hx,hy))
                        if costs['parent']<=costs[r]:new.append(dict(record=record,reference=r))
                out.write((json.dumps(record,separators=(',',':'))+'\n').encode());rows+=1
except Exception as e:
    (W/'probe-FAILURE.json').write_text(json.dumps(dict(error=repr(e),current=current,completed_ARM_calls=dict(counts),completed_rows=rows),indent=2)+'\n');raise
finally:
    for m,h in hooks:m.uc.hook_del(h)
result=dict(status='PASS_R47_FRESH_PUBLIC_DIAGNOSTIC_NOT_FULLQUALIFICATION',input_pairs=len(jobs),state_rows=rows,actual_diagnostic_ARM_calls=sum(counts.values()),completed_ARM_calls=dict(counts),actual_directed_MPFR_inputs=len(jobs)-snan,exact_sNaN_policy_shortcuts=snan,candidate_ELF_sha256=sha(W/'candidate.elf'),parent_FROZEN_sha256=sha(P/'FROZEN.json'),parent_qualification_FROZEN_sha256=sha(Q/'FROZEN.json'),input_sha256=sha(W/'probe-inputs.json'),records_sha256=sha(W/'probe-records.jsonl.gz'),candidate_wrong=0,parent_losing_pairs=len(pl),candidate_losing_pairs=len(cl),fixed_pairs=[list(k)for k in sorted(pl-cl)],new_losing_pairs=[list(k)for k in sorted(cl-pl)],new_correct_reference_loss_rows=new,remaining_losing_argument_pairs=[list(k)for k in sorted(cl)],parent_instruction_delta_histogram=dict(delta),all_parent_instruction_increase_rows=increases,old2047_fixed=len(old-cl),new_parent_preexisting_losing_pairs=[list(k)for k in sorted(pl-old)],all3_Qfplib_compositions_allinputs_allstates=True,no_nominal_reference_filter=True,all_wrong_reference_outputs_and_costs_retained=True,wrong_reference_state_variants=wrongrefs,native_call_state_histogram=dict(native),Q8_call_state_histogram=dict(q8visits),all16_public_incoming_NZCV_and5R12_patterns_checked=True,actual_private_C_contract_asserted_every_Q8_call=True,all_actual_native_q_and_live_frame_and_Bh_R5_exact_parent=True,Q8_source_code_and_runtime_metadata_unchanged_from_R43=True,non_native_public_count_changes_recorded=True,observed_stacks={n:SP-m.stack_lowest for n,m in machines.items()},hardware_accessed=False,physical_cycles_measured=False,integration_GO=False,goal_complete=False,elapsed_seconds=time.monotonic()-started)
(W/'probe-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ('fixed_pairs','new_losing_pairs','new_correct_reference_loss_rows','remaining_losing_argument_pairs','all_parent_instruction_increase_rows','new_parent_preexisting_losing_pairs')},indent=2),flush=True)
